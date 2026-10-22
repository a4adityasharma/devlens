"""
Security Agent orchestrator (Phase 7 / architecture doc §16, §23).

Runs the Semgrep scanner (app.agents.security_scanner) against a cloned
repository, then validates every raw finding against real, checkable facts
before persisting it as a Finding row — mirroring
app.services.chat_service.py's citation-dropping philosophy: a finding
pointing at a file/line that doesn't actually exist gets rejected, not
"fixed" or trusted anyway. Unlike chat_service's citations (which guard
against an LLM inventing a source), this guards against a simpler failure
mode — a path-handling bug in the scanner wrapper producing a
file_path/line_start that doesn't correspond to real content — but the
principle (verify before persisting, don't just trust the tool) is the
same one this project has applied at every phase.

Design decision this phase had to make explicitly (per docs/PROGRESS.md's
own instruction not to default into the existing pattern): a Semgrep scan
is meaningfully slower than parsing/graph-build/embedding for a
Flask-sized repo, and isn't something every analysis needs immediately.
So this is wired as an **on-demand endpoint**
(`POST /repositories/{id}/analyze/security`), NOT a fourth best-effort step
chained onto `POST /repositories`. Revisit if scan time proves fast enough
in practice to belong in the automatic chain after all.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.security_scanner import ScannerError, ScannerUnavailable, parse_semgrep_result, run_semgrep
from app.models.models import Finding, Repository, RepositoryAnalysis


class SecurityScanSkipped(Exception):
    """semgrep isn't installed/reachable — same soft-fail shape as
    GraphBuildSkipped/EmbeddingSkipped, raised so the caller can decide how
    to surface it rather than crashing."""


def _validate_finding(finding: dict, local_path: Path) -> bool:
    """A finding is only as trustworthy as the file/line it points at
    actually being real. Checks the file exists under the repo root and
    the claimed start line is within the file's actual line count —
    cheap, deterministic, catches path-handling bugs (e.g. an absolute vs.
    relative path mismatch) before they become a persisted, user-visible
    finding pointing at nothing."""
    file_path = local_path / finding["file_path"]
    if not file_path.is_file():
        return False
    try:
        line_count = sum(1 for _ in file_path.open(encoding="utf-8", errors="replace"))
    except OSError:
        return False
    return 1 <= finding["line_start"] <= line_count


def run_security_scan(db: Session, repository: Repository, analysis: RepositoryAnalysis) -> dict:
    """Scans `repository.local_path`, validates each raw finding, persists
    the valid ones as Finding rows tied to `analysis`. Returns a summary
    dict; raises SecurityScanSkipped if semgrep isn't available, or the
    underlying ScannerError if the scan ran but failed (timeout, bad
    output) — callers should distinguish "not installed" (soft-fail,
    expected in environments without it) from "installed but broke"
    (worth surfacing as a real error)."""
    local_path = Path(repository.local_path)

    try:
        raw_results = run_semgrep(local_path)
    except ScannerUnavailable as exc:
        raise SecurityScanSkipped(str(exc)) from exc
    # ScannerError (timeout / bad output) intentionally propagates — a
    # scan that ran and broke is a real problem, not a soft-fail case.

    created = 0
    rejected = 0
    for raw in raw_results:
        parsed = parse_semgrep_result(raw, local_path)
        if not _validate_finding(parsed, local_path):
            rejected += 1
            continue
        db.add(Finding(
            analysis_id=analysis.id,
            agent="security",
            category=parsed["category"],
            severity=parsed["severity"],
            confidence=parsed["confidence"],
            file_path=parsed["file_path"],
            line_start=parsed["line_start"],
            line_end=parsed["line_end"],
            title=parsed["title"],
            description=parsed["description"],
            recommendation=parsed["recommendation"],
            validated="valid",
        ))
        created += 1
    db.commit()

    return {"findings_created": created, "findings_rejected": rejected, "total_raw": len(raw_results)}
