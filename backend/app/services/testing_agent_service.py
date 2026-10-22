"""
Testing Agent orchestrator (Phase 7 / architecture doc §17).

Design decision, made deliberately rather than defaulted (per this
project's established practice — see graph_service.py, embedding_service.py,
security_agent_service.py, architecture_agent_service.py, each of which
had to make the same call): **on-demand, scoped to ONE function per
request**, not "generate tests for every untested function" as a single
call. An LLM call per function is real latency and real API cost, unlike
the Architecture Agent's ~3ms in-memory computation — generating for an
entire repo's worth of untested functions (69, in this project's own
self-analysis) in one request would be slow, expensive, and give the
caller no chance to review one result before triggering the next. The
route is `POST /repositories/{id}/generate-test` with a target file+symbol
in the request body, mirroring how a human would actually use this
feature: pick one function, generate a test for it, look at the result.

Persists successfully-validated tests as a GeneratedArtifact
(agent="testing", artifact_type="generated_test") — reusing the table the
Architecture Agent added rather than a new one, since the shape (an
analysis-scoped piece of generated content) fits. A test that fails Stage
A validation is NOT persisted — it's returned to the caller with the
validation failure reasons so they can see why, but nothing untrustworthy
enters the database.

**This module never executes the generated test.** See
app/agents/test_validator.py's module docstring for exactly what Stage A
validation does and does not guarantee, and docs/PROGRESS.md for why
Stage B (real sandboxed execution) is out of scope for this session.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.test_coverage_analyzer import find_untested_symbols
from app.agents.test_generator import TestGenerationSkipped, generate_test
from app.agents.test_validator import validate_generated_test
from app.analyzer.parser import EXTENSION_TO_LANGUAGE
from app.models.models import GeneratedArtifact, Repository, RepositoryAnalysis


class SymbolNotFound(Exception):
    """The requested file/symbol doesn't exist in this analysis's symbols
    — distinct from a generation/validation failure, since it means the
    caller asked for something that was never there."""


def list_untested_symbols(analysis: RepositoryAnalysis) -> list[dict]:
    """Read-only helper backing GET /{id}/untested — lets a caller (or a
    future frontend) see the candidate list before picking one to
    generate a test for."""
    return [u.to_dict() for u in find_untested_symbols(analysis.symbols or [])]


def _read_source(local_path: Path, file: str, line_start: int, line_end: int) -> str:
    text = (local_path / file).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[max(0, line_start - 1):min(len(lines), line_end)])


def _detect_framework_hint(file: str) -> str:
    ext = Path(file).suffix.lower()
    if ext == ".py":
        return "pytest"
    if ext in (".ts", ".tsx"):
        return "jest (TypeScript)"
    return "jest"


def run_test_generation(
    db: Session, repository: Repository, analysis: RepositoryAnalysis,
    file: str, symbol_name: str,
) -> dict:
    """Generates and Stage-A-validates a test for one specific
    function/method. Raises SymbolNotFound if file+symbol_name doesn't
    match anything in this analysis; raises TestGenerationSkipped if no
    LLM is configured (caller should translate both to HTTP errors, same
    pattern as every other *_service.py in this project)."""
    target = next(
        (s for s in (analysis.symbols or [])
         if s.get("file") == file and s.get("name") == symbol_name
         and s.get("type") in ("function", "method")),
        None,
    )
    if target is None:
        raise SymbolNotFound(f"No function/method named '{symbol_name}' found in {file} for this analysis")

    language = EXTENSION_TO_LANGUAGE.get(Path(file).suffix.lower(), "python")
    source_text = _read_source(Path(repository.local_path), file, target["line_start"], target["line_end"])
    framework_hint = _detect_framework_hint(file)

    raw_code = generate_test(symbol_name, target["type"], file, source_text, framework_hint)
    validation = validate_generated_test(raw_code, target_symbol_name=symbol_name, language=language)

    result = {
        "file": file, "symbol": symbol_name, "generated_code": raw_code,
        "validation": validation.to_dict(), "persisted": False, "artifact_id": None,
    }

    if validation.valid:
        artifact = GeneratedArtifact(
            analysis_id=analysis.id, agent="testing", artifact_type="generated_test",
            content=raw_code, extra={"file": file, "symbol": symbol_name, "language": language},
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        result["persisted"] = True
        result["artifact_id"] = artifact.id

    return result
