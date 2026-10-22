from pathlib import Path

from app.services.performance_agent_service import run_performance_analysis


class _FakeRepository:
    def __init__(self, local_path):
        self.local_path = str(local_path)


class _FakeAnalysis:
    def __init__(self, symbols):
        self.id = "analysis-1"
        self.symbols = symbols


class _RecordingDb:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass


def test_run_performance_analysis_persists_findings(tmp_path: Path):
    long_body = "\n".join(f"    x{i} = {i}" for i in range(60))
    (tmp_path / "big.py").write_text(f"def big_function():\n{long_body}\n    return x0\n")
    symbols = [{"type": "function", "name": "big_function", "file": "big.py",
                "line_start": 1, "line_end": 62, "parameters": []}]

    db = _RecordingDb()
    summary = run_performance_analysis(db, _FakeRepository(tmp_path), _FakeAnalysis(symbols))

    assert summary["findings_created"] == 1
    assert summary["by_category"] == {"Large Function": 1}
    assert len(db.added) == 1
    assert db.added[0].agent == "performance"
    assert db.added[0].validated == "valid"


def test_run_performance_analysis_no_findings_for_clean_code(tmp_path: Path):
    (tmp_path / "clean.py").write_text("def add(a, b):\n    return a + b\n")
    symbols = [{"type": "function", "name": "add", "file": "clean.py",
                "line_start": 1, "line_end": 2, "parameters": ["a", "b"]}]
    db = _RecordingDb()
    summary = run_performance_analysis(db, _FakeRepository(tmp_path), _FakeAnalysis(symbols))
    assert summary["findings_created"] == 0
    assert db.added == []


def test_run_performance_analysis_handles_empty_symbols(tmp_path: Path):
    db = _RecordingDb()
    summary = run_performance_analysis(db, _FakeRepository(tmp_path), _FakeAnalysis(symbols=None))
    assert summary["findings_created"] == 0
