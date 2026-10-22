from app.services.architecture_agent_service import run_architecture_analysis


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


def test_run_architecture_analysis_persists_artifact():
    symbols = [
        {"type": "function", "name": "handler", "file": "routes/api.py", "line_start": 1, "line_end": 2},
        {"type": "function", "name": "process", "file": "services/core.py", "line_start": 1, "line_end": 2},
        {"type": "call", "name": "process", "file": "routes/api.py", "caller": "handler"},
    ]
    db = _RecordingDb()
    summary = run_architecture_analysis(db, _FakeAnalysis(symbols))

    assert len(db.added) == 1
    artifact = db.added[0]
    assert artifact.agent == "architecture"
    assert artifact.artifact_type == "mermaid_diagram"
    assert artifact.analysis_id == "analysis-1"
    assert artifact.content.startswith("graph TD")
    assert "Routes" in artifact.extra["layers"]

    assert summary["layer_count"] == 2
    assert summary["edge_count"] == 1


def test_run_architecture_analysis_handles_empty_symbols_gracefully():
    db = _RecordingDb()
    summary = run_architecture_analysis(db, _FakeAnalysis(symbols=[]))
    assert summary["layer_count"] == 0
    assert summary["edge_count"] == 0
    assert db.added[0].content == "graph TD"


def test_run_architecture_analysis_handles_none_symbols():
    """analysis.symbols can be None (e.g. an analysis that failed before
    symbol extraction completed) — shouldn't crash."""
    db = _RecordingDb()
    summary = run_architecture_analysis(db, _FakeAnalysis(symbols=None))
    assert summary["layer_count"] == 0
