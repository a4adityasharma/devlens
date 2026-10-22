from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import ChatMessage, ChatSession, Finding, GeneratedArtifact, Repository, RepositoryAnalysis
from app.schemas.repository import (
    RepositoryCreate, RepositoryCreateResponse, RepositoryOut, AnalysisOut,
    SearchQuery, SearchResultOut, ChatRequest, ChatResponse,
    FindingOut, SecurityScanResponse, ArtifactOut,
    UntestedSymbolOut, GenerateTestRequest, GenerateTestResponse,
    GenerateDocRequest, GenerateDocResponse,
)
from app.services.analysis_service import run_code_intelligence
from app.services.architecture_agent_service import run_architecture_analysis
from app.services.performance_agent_service import run_performance_analysis
from app.services.chat_service import ChatSkipped, answer_question
from app.services.embedding_service import EmbeddingSkipped, run_embedding, search_repository
from app.services.graph_service import GraphBuildSkipped, run_graph_build
from app.services.repository_service import (
    validate_github_url, ingest_repository, InvalidRepositoryURLError,
)
from app.services.security_agent_service import SecurityScanSkipped, run_security_scan
from app.agents.test_generator import TestGenerationSkipped
from app.services.testing_agent_service import SymbolNotFound, list_untested_symbols, run_test_generation
from app.agents.doc_generator import DocGenerationSkipped
from app.services.documentation_agent_service import run_documentation_generation

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryCreateResponse, status_code=202)
def create_repository(
    payload: RepositoryCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        parts = validate_github_url(payload.url)
    except InvalidRepositoryURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repository = Repository(
        name=parts["repo"],
        url=payload.url,
        owner=parts["owner"],
        status="queued",
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)

    # MVP: run inline via BackgroundTasks so the demo works without Celery.
    # Swap this line for a `.delay()` Celery call once the worker is wired up
    # (see app/workers/repository_worker.py) for large repos / production.
    background_tasks.add_task(_run_ingestion, repository.id)

    return RepositoryCreateResponse(repository_id=repository.id, status=repository.status)


def _run_ingestion(repository_id: str):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        repo = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repo:
            return
        ingest_repository(db, repo)
        # Phase 3: once the repo is cloned + scanned successfully, chain
        # straight into Tree-sitter code intelligence so a single
        # POST /repositories triggers the full pipeline built so far.
        if repo.status == "ready":
            analysis = run_code_intelligence(db, repo)
            # Phase 4: build the Neo4j graph from the symbols just
            # extracted. Best-effort — if Neo4j isn't running (e.g. local
            # dev without `docker compose up`), the repo + its parsed
            # symbols are still fully usable; the graph is just absent
            # until Neo4j is available and analysis re-run.
            if analysis.status == "completed":
                try:
                    run_graph_build(db, analysis)
                except GraphBuildSkipped:
                    pass
                # Phase 5: chunk + embed + upsert into Qdrant, so semantic
                # search is available right after analysis. Also
                # best-effort — if Qdrant isn't running, the repo/symbols/
                # graph (if built) remain usable; search just returns
                # nothing until Qdrant is available and analysis re-run.
                try:
                    run_embedding(db, repo, analysis)
                except EmbeddingSkipped:
                    pass
                # Phase 7 (Architecture Agent): pure in-memory computation
                # over symbols already in hand, benchmarked at ~3ms even
                # for a 6,000+-symbol repo — unlike the other three
                # best-effort steps above, this one is chained because
                # it's cheap enough that there's no real reason to make it
                # on-demand (see architecture_agent_service.py's module
                # docstring for the actual measurement, not just an
                # assumption). No try/except*Skipped needed — there's no
                # external service to be unreachable.
                run_architecture_analysis(db, analysis)
                # Phase 7 (Performance Agent): also chained, same
                # reasoning as the Architecture Agent above — measured
                # (not assumed) at ~126ms against a real 6,000+-symbol
                # repo (see performance_agent_service.py's module
                # docstring), negligible next to everything already in
                # this chain. No LLM, no subprocess, no soft-fail path.
                run_performance_analysis(db, repo, analysis)
    finally:
        db.close()


@router.get("", response_model=list[RepositoryOut])
def list_repositories(db: Session = Depends(get_db)):
    return db.query(Repository).order_by(Repository.created_at.desc()).all()


@router.get("/{repository_id}", response_model=RepositoryOut)
def get_repository(repository_id: str, db: Session = Depends(get_db)):
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.delete("/{repository_id}", status_code=204)
def delete_repository(repository_id: str, db: Session = Depends(get_db)):
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    db.delete(repo)
    db.commit()


@router.get("/{repository_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(repository_id: str, db: Session = Depends(get_db)):
    return (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository_id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .all()
    )


@router.get("/{repository_id}/analyses/latest", response_model=AnalysisOut)
def get_latest_analysis(repository_id: str, db: Session = Depends(get_db)):
    analysis = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository_id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found for this repository yet")
    return analysis


@router.post("/{repository_id}/search", response_model=list[SearchResultOut])
def search(repository_id: str, payload: SearchQuery, db: Session = Depends(get_db)):
    """Standalone semantic search over a repository's chunked symbols
    (Phase 5). Independently testable ahead of Phase 6 (RAG chat), which
    will wrap an LLM + Neo4j graph context around this same retrieval
    call. Returns [] rather than an error if nothing has been embedded yet
    (e.g. Qdrant wasn't running when this repo was analyzed) — the caller
    can distinguish "no results" from "not analyzed yet" via
    GET /{id}/analyses/latest's stats.embedding field."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    try:
        return search_repository(repository_id, payload.query, limit=payload.limit)
    except EmbeddingSkipped:
        return []


@router.post("/{repository_id}/chat", response_model=ChatResponse)
def chat(repository_id: str, payload: ChatRequest, db: Session = Depends(get_db)):
    """RAG chat over a repository (Phase 6). Creates a new ChatSession if
    `session_id` is omitted, otherwise continues an existing one — every
    user message and the resulting assistant answer (with its *validated*
    sources, see chat_service.py's citation-grounding logic) are persisted
    so a session has a real transcript, not just the latest exchange.

    Returns 404 if the repository doesn't exist, 503 if no LLM is
    configured (ANTHROPIC_API_KEY unset) — this is a synchronous,
    user-initiated request, unlike the best-effort background pipeline
    steps, so an explicit error is more honest here than silently
    returning an empty answer."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    if payload.session_id:
        session = db.query(ChatSession).filter(
            ChatSession.id == payload.session_id, ChatSession.repository_id == repository_id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found for this repository")
    else:
        session = ChatSession(repository_id=repository_id)
        db.add(session)
        db.commit()
        db.refresh(session)

    db.add(ChatMessage(session_id=session.id, role="user", content=payload.message))
    db.commit()

    try:
        from app.knowledge.neo4j_client import get_neo4j_client
        result = answer_question(repository_id, payload.message, neo4j_client=get_neo4j_client())
    except ChatSkipped as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    sources_payload = [s for s in result["sources"]]
    db.add(ChatMessage(
        session_id=session.id, role="assistant", content=result["answer"], sources=sources_payload,
    ))
    db.commit()

    return ChatResponse(
        session_id=session.id,
        answer=result["answer"],
        sources=sources_payload,
        graph_available=result["graph_available"],
        hit_count=result["hit_count"],
    )


@router.post("/{repository_id}/analyze/security", response_model=SecurityScanResponse)
def analyze_security(repository_id: str, db: Session = Depends(get_db)):
    """Runs the Security Agent (Phase 7) against a repository's latest
    analysis. Deliberately an on-demand endpoint, not chained onto
    POST /repositories — a Semgrep scan is heavier/slower than parsing,
    graph-building, or embedding, so it's user-triggered rather than
    running automatically on every ingestion (see
    app/services/security_agent_service.py's module docstring for the
    reasoning). Returns 404 if the repository or its analysis doesn't
    exist yet, 503 if semgrep isn't installed/reachable."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    analysis = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository_id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found for this repository yet")

    try:
        summary = run_security_scan(db, repo, analysis)
    except SecurityScanSkipped as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    findings = db.query(Finding).filter(Finding.analysis_id == analysis.id).all()
    return SecurityScanResponse(**summary, findings=findings)


@router.get("/{repository_id}/findings", response_model=list[FindingOut])
def list_findings(repository_id: str, db: Session = Depends(get_db)):
    """All findings across every analysis of this repository, most recent
    first — not scoped to a single analysis run, so a repeated scan's
    history is visible rather than just the latest result."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    return (
        db.query(Finding)
        .join(RepositoryAnalysis, Finding.analysis_id == RepositoryAnalysis.id)
        .filter(RepositoryAnalysis.repository_id == repository_id)
        .order_by(Finding.created_at.desc())
        .all()
    )


@router.get("/{repository_id}/architecture", response_model=ArtifactOut)
def get_architecture_diagram(repository_id: str, db: Session = Depends(get_db)):
    """Latest Architecture Agent output (Mermaid diagram + layer/edge
    data) for this repository. Unlike the Security Agent, this runs
    automatically as part of ingestion (see repositories.py's
    _run_ingestion — it's cheap enough to chain, see
    architecture_agent_service.py's module docstring), so this endpoint
    just reads the most recent result rather than triggering a fresh run."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    artifact = (
        db.query(GeneratedArtifact)
        .join(RepositoryAnalysis, GeneratedArtifact.analysis_id == RepositoryAnalysis.id)
        .filter(RepositoryAnalysis.repository_id == repository_id, GeneratedArtifact.agent == "architecture")
        .order_by(GeneratedArtifact.created_at.desc())
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="No architecture diagram generated for this repository yet")
    return artifact


def _latest_analysis_or_404(db: Session, repository_id: str) -> RepositoryAnalysis:
    analysis = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository_id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found for this repository yet")
    return analysis


@router.get("/{repository_id}/untested", response_model=list[UntestedSymbolOut])
def get_untested_symbols(repository_id: str, db: Session = Depends(get_db)):
    """Functions/methods with no detected test coverage (Phase 7 Testing
    Agent, step 1 — pure, deterministic, no LLM involved). Use this to
    pick a `file`/`symbol_name` pair to pass to
    POST /{id}/generate-test."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    analysis = _latest_analysis_or_404(db, repository_id)
    return list_untested_symbols(analysis)


@router.post("/{repository_id}/generate-test", response_model=GenerateTestResponse)
def generate_test_for_symbol(repository_id: str, payload: GenerateTestRequest, db: Session = Depends(get_db)):
    """Generates a test for ONE specific function/method (Phase 7 Testing
    Agent). Deliberately scoped to a single symbol per request, not "all
    untested functions" — see testing_agent_service.py's module docstring
    for why. The generated code is Stage-A-validated (syntax, references
    the right symbol, looks like a test) before being persisted — an
    invalid result is still returned (so the caller can see what went
    wrong) but with `persisted: false`.

    **The returned code has NOT been executed.** See
    app/agents/test_validator.py's module docstring for exactly what
    validation does and does not guarantee.

    404 if the repository/analysis/symbol doesn't exist, 503 if no LLM is
    configured."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    analysis = _latest_analysis_or_404(db, repository_id)

    try:
        result = run_test_generation(db, repo, analysis, file=payload.file, symbol_name=payload.symbol_name)
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TestGenerationSkipped as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return GenerateTestResponse(**result)


@router.post("/{repository_id}/generate-doc", response_model=GenerateDocResponse)
def generate_documentation_for_repo(repository_id: str, payload: GenerateDocRequest, db: Session = Depends(get_db)):
    """Generates one document (Phase 7 Documentation Agent) — deliberately
    one `doc_type` per request (readme | architecture_overview |
    setup_guide | api_reference), same reasoning as
    POST /{id}/generate-test's one-symbol-per-request scoping (see
    documentation_agent_service.py's module docstring).

    Unlike the Testing Agent's Stage A gate, this always persists — a
    grounding issue here is informational (surfaced in the `grounding`
    field), not a pass/fail block. **Never overwrites any file in the
    scanned repository** — this is purely a new database row.

    404 if the repository/analysis doesn't exist, 400 for an unknown
    doc_type, 503 if no LLM is configured."""
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    analysis = _latest_analysis_or_404(db, repository_id)

    try:
        result = run_documentation_generation(db, repo, analysis, doc_type=payload.doc_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DocGenerationSkipped as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return GenerateDocResponse(**result)
