"""
Documentation Agent orchestrator (Phase 7 / architecture doc §19).

Design decision, made deliberately (per this project's established
practice — every agent's orchestrator has had to make this call): **one
document type per request**, mirroring the Testing Agent's one-function-
per-request scoping and for the same reason — an LLM call per document is
real cost/latency, and generating four document types in one unreviewed
batch is a worse experience than picking one, reading it, then requesting
another.

Gathers REAL context before calling the LLM: the repository's actual file
list and real function/class/method names (from
RepositoryAnalysis.symbols — no invented structure), the actual README
file on disk if one exists (read, never overwritten — architecture doc
§19 is explicit about this), and the latest Architecture Agent output
(app.services.architecture_agent_service) if one exists, since re-deriving
layer structure here would duplicate work that module already does.

After generation, runs app.agents.doc_generator.check_grounding against
the real file/symbol sets and stores the grounding report alongside the
generated content — an ungrounded reference does NOT block persistence
(unlike the Testing Agent's Stage A, which is a binary parse/no-parse
gate, a documentation grounding issue is a matter of degree: a README
with one stray ungrounded mention among fifty correct ones is still
mostly useful) but IS surfaced to the caller so they can see exactly
what wasn't verifiable, the same "don't silently trust, don't silently
hide problems either" principle as every other phase.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.doc_generator import DOC_TYPES, check_grounding, generate_documentation
from app.models.models import GeneratedArtifact, Repository, RepositoryAnalysis


def _gather_symbols_by_file(symbols: list[dict]) -> tuple[list[str], dict[str, list[str]]]:
    files = sorted({s["file"] for s in symbols if s.get("file")})
    by_file: dict[str, list[str]] = {}
    for s in symbols:
        if s.get("type") in ("function", "method", "class") and s.get("file") and s.get("name"):
            by_file.setdefault(s["file"], []).append(s["name"])
    return files, by_file


def _valid_symbol_names(symbols: list[dict]) -> set[str]:
    return {s["name"] for s in symbols if s.get("type") in ("function", "method", "class") and s.get("name")}


def _read_existing_readme(local_path: Path) -> str | None:
    for candidate in ("README.md", "README.rst", "README.txt", "README"):
        path = local_path / candidate
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
    return None


def _latest_architecture_summary(db: Session, analysis_id: str) -> str | None:
    artifact = (
        db.query(GeneratedArtifact)
        .filter(GeneratedArtifact.analysis_id == analysis_id, GeneratedArtifact.agent == "architecture")
        .order_by(GeneratedArtifact.created_at.desc())
        .first()
    )
    if not artifact:
        return None
    layers = artifact.extra.get("layers", {})
    edges = artifact.extra.get("edges", [])
    lines = [f"{name}: {info['file_count']} file(s)" for name, info in layers.items()]
    lines.extend(f"{e['from']} -> {e['to']} ({e['count']} call(s))" for e in edges[:20])
    return "\n".join(lines) if lines else None


def run_documentation_generation(
    db: Session, repository: Repository, analysis: RepositoryAnalysis, doc_type: str,
) -> dict:
    """Generates one document of `doc_type` (must be one of
    app.agents.doc_generator.DOC_TYPES). Always persists — unlike the
    Testing Agent's Stage A gate, grounding issues here are informational,
    not a pass/fail block (see module docstring)."""
    if doc_type not in DOC_TYPES:
        raise ValueError(f"Unknown doc_type '{doc_type}', must be one of {DOC_TYPES}")

    symbols = analysis.symbols or []
    files, symbols_by_file = _gather_symbols_by_file(symbols)
    existing_readme = _read_existing_readme(Path(repository.local_path))
    architecture_summary = _latest_architecture_summary(db, analysis.id)

    content = generate_documentation(
        doc_type, repository.name, files, symbols_by_file,
        existing_readme=existing_readme, architecture_summary=architecture_summary,
    )

    grounding = check_grounding(content, valid_files=set(files), valid_symbol_names=_valid_symbol_names(symbols))

    artifact = GeneratedArtifact(
        analysis_id=analysis.id, agent="documentation", artifact_type=doc_type,
        content=content, extra={"grounding": grounding},
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    return {
        "doc_type": doc_type, "content": content, "grounding": grounding, "artifact_id": artifact.id,
    }
