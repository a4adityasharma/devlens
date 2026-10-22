"""
test_run_security_scan_creates_validated_findings uses the REAL semgrep
scanner against the real vulnerable_repo fixture (same one
test_security_scanner.py uses) — this exercises the full
scan -> parse -> validate -> persist path with nothing mocked except the
DB session, same verification depth as the scanner tests themselves.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.security_scanner import ScannerUnavailable
from app.services.security_agent_service import SecurityScanSkipped, _validate_finding, run_security_scan

FIXTURES = Path(__file__).parent / "security_fixtures" / "vulnerable_repo"


class _FakeRepository:
    def __init__(self, local_path):
        self.local_path = str(local_path)


class _FakeAnalysis:
    def __init__(self):
        self.id = "analysis-1"


class _RecordingDb:
    """Real enough to prove the orchestration logic, without needing a
    real SQLAlchemy session — records every Finding object passed to
    add(), same lightweight-fake pattern used throughout this project's
    other service tests (see test_graph_service.py, test_embedding_service.py)."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass


def test_run_security_scan_creates_validated_findings():
    repo = _FakeRepository(FIXTURES)
    analysis = _FakeAnalysis()
    db = _RecordingDb()

    summary = run_security_scan(db, repo, analysis)

    assert summary["total_raw"] == 7
    assert summary["findings_created"] == 7
    assert summary["findings_rejected"] == 0
    assert len(db.added) == 7
    assert all(f.agent == "security" for f in db.added)
    assert all(f.analysis_id == "analysis-1" for f in db.added)
    assert all(f.validated == "valid" for f in db.added)
    categories = {f.category for f in db.added}
    assert "Command Injection" in categories
    assert "SQL Injection" in categories


def test_run_security_scan_skips_gracefully_when_semgrep_unavailable():
    repo = _FakeRepository(FIXTURES)
    with patch("app.services.security_agent_service.run_semgrep", side_effect=ScannerUnavailable("not found")):
        with pytest.raises(SecurityScanSkipped):
            run_security_scan(_RecordingDb(), repo, _FakeAnalysis())


# ---------------------------------------------------------------------------
# _validate_finding — the grounding check, pure logic
# ---------------------------------------------------------------------------

def test_validate_finding_accepts_real_file_and_line(tmp_path):
    (tmp_path / "a.py").write_text("line1\nline2\nline3\n")
    finding = {"file_path": "a.py", "line_start": 2}
    assert _validate_finding(finding, tmp_path) is True


def test_validate_finding_rejects_nonexistent_file(tmp_path):
    finding = {"file_path": "does_not_exist.py", "line_start": 1}
    assert _validate_finding(finding, tmp_path) is False


def test_validate_finding_rejects_line_beyond_file_length(tmp_path):
    (tmp_path / "a.py").write_text("line1\nline2\n")
    finding = {"file_path": "a.py", "line_start": 999}
    assert _validate_finding(finding, tmp_path) is False


def test_validate_finding_rejects_line_zero_or_negative(tmp_path):
    (tmp_path / "a.py").write_text("line1\n")
    assert _validate_finding({"file_path": "a.py", "line_start": 0}, tmp_path) is False
