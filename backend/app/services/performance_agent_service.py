"""
Performance Agent orchestrator (Phase 7 / architecture doc §20).

Chained into the automatic ingestion pipeline, like the Architecture
Agent and unlike the Security/Testing/Documentation Agents — measured
before deciding, per this project's established practice: benchmarked at
~126ms against a real 6,233-symbol repository (pallets/flask), negligible
next to the clone/parse/graph/embedding steps already in the chain. No
LLM, no subprocess, no soft-fail path needed (same reasoning as
architecture_agent_service.py).

Persists findings as `Finding` rows (`agent="performance"`) — reusing the
Security Agent's table rather than `GeneratedArtifact` (which the
Architecture and Documentation Agents use for whole-repo artifacts, not
per-location findings). A performance issue tied to a specific file/line
with a severity/category is exactly the shape `Finding` was built for.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.performance_analyzer import analyze_performance
from app.models.models import Finding, Repository, RepositoryAnalysis


def run_performance_analysis(db: Session, repository: Repository, analysis: RepositoryAnalysis) -> dict:
    findings = analyze_performance(Path(repository.local_path), analysis.symbols or [])

    for f in findings:
        db.add(Finding(
            analysis_id=analysis.id,
            agent="performance",
            category=f["category"],
            severity=f["severity"],
            confidence=None,
            file_path=f["file"],
            line_start=f["line_start"],
            line_end=f["line_end"],
            title=f["title"],
            description=f["description"],
            recommendation=f["recommendation"],
            validated="valid",  # deterministic metric, not an LLM claim needing grounding-style validation
        ))
    db.commit()

    by_category: dict[str, int] = {}
    for f in findings:
        by_category[f["category"]] = by_category.get(f["category"], 0) + 1

    return {"findings_created": len(findings), "by_category": by_category}
