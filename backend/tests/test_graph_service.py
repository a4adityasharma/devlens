from unittest.mock import patch

import pytest

from app.services.graph_service import GraphBuildSkipped, run_graph_build


class _FakeAnalysis:
    def __init__(self, symbols):
        self.repository_id = "repo-1"
        self.symbols = symbols
        self.stats = {"function_count": 1}


class _FakeUnreachableClient:
    def verify_connectivity(self):
        return False


class _FakeReachableClient:
    def __init__(self):
        self.writes = []

    def verify_connectivity(self):
        return True

    def run_write(self, cypher, **params):
        self.writes.append((cypher, params))


def test_run_graph_build_skips_gracefully_when_neo4j_unreachable():
    with patch("app.services.graph_service.get_neo4j_client", return_value=_FakeUnreachableClient()):
        with pytest.raises(GraphBuildSkipped):
            run_graph_build(db=None, analysis=_FakeAnalysis(symbols=[]))


def test_run_graph_build_writes_graph_and_updates_stats_when_reachable():
    fake_client = _FakeReachableClient()
    analysis = _FakeAnalysis(symbols=[
        {"type": "class", "name": "Foo", "file": "a.py", "line_start": 1, "line_end": 2,
         "parameters": [], "parent": None, "source": None, "caller": None, "receiver": None},
    ])

    class _FakeDb:
        def commit(self):
            pass

    with patch("app.services.graph_service.get_neo4j_client", return_value=fake_client):
        summary = run_graph_build(db=_FakeDb(), analysis=analysis)

    assert summary["class_count"] == 1
    assert len(fake_client.writes) > 0
    # existing stats are preserved, graph summary is added alongside them
    assert analysis.stats["function_count"] == 1
    assert analysis.stats["graph"] == summary
