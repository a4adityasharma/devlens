"""
Orchestrates Phase 3 (Code Intelligence) on top of an already-ingested
Repository: creates a RepositoryAnalysis row pinned to the current commit
hash, runs the Tree-sitter parser across the whole repo, and persists the
resulting symbol table + counts.

Kept as its own service (rather than folded into repository_service.py)
because Module 1 (clone/scan) is considered done and tested — this file
is additive so it never has to touch that module's code.
"""
from datetime import datetime
from pathlib import Path

import git
from sqlalchemy.orm import Session

from app.analyzer.repository_analyzer import analyze_repository
from app.models.models import Repository, RepositoryAnalysis


def _current_commit_hash(local_path: Path) -> str | None:
    try:
        repo = git.Repo(local_path)
        return repo.head.commit.hexsha
    except Exception:  # noqa: BLE001
        return None


def run_code_intelligence(db: Session, repository: Repository) -> RepositoryAnalysis:
    """Create + populate a RepositoryAnalysis for the given (already-cloned,
    already-scanned) repository. Safe to call multiple times — each call
    creates a new analysis row, so re-running after a `git pull` produces a
    fresh analysis tied to the new commit hash (architecture doc §5)."""
    local_path = Path(repository.local_path)

    analysis = RepositoryAnalysis(
        repository_id=repository.id,
        commit_hash=_current_commit_hash(local_path),
        status="running",
        stage="parsing",
        started_at=datetime.utcnow(),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    try:
        result = analyze_repository(local_path)
        analysis.symbols = result["symbols"]
        analysis.stats = result["stats"]
        analysis.status = "completed"
        analysis.stage = "done"
        analysis.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(analysis)
        return analysis
    except Exception as exc:  # noqa: BLE001
        analysis.status = "failed"
        analysis.error_message = str(exc)
        analysis.completed_at = datetime.utcnow()
        db.commit()
        raise
