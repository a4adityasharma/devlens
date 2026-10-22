"""
Unlike test_graph_service.py (which has to mock Neo4j entirely — no live
instance reachable here), these tests run against a REAL Qdrant engine via
its local in-memory mode (see app/knowledge/qdrant_client.py's module
docstring). This is the strongest verification level available in this
sandbox for Phase 5: actual vector storage and cosine-similarity search,
not a hand-written stand-in for one.
"""
from pathlib import Path
from unittest.mock import patch

import pytest
from qdrant_client import QdrantClient

from app.knowledge.qdrant_client import VectorStoreClient
from app.services.embedding_service import EmbeddingSkipped, run_embedding, search_repository


class _FakeRepository:
    def __init__(self, local_path):
        self.id = "repo-1"
        self.local_path = str(local_path)


class _FakeAnalysis:
    def __init__(self, symbols):
        self.symbols = symbols
        self.stats = {"function_count": 1}


class _FakeDb:
    def commit(self):
        pass


class _FakeUnreachableClient:
    def verify_connectivity(self):
        return False


def _write_sample_repo(tmp_path: Path):
    (tmp_path / "auth.py").write_text(
        "def authenticate_user(username, password):\n"
        "    validate_credentials(username, password)\n"
        "    return True\n"
        "\n"
        "def render_chart(data):\n"
        "    return plot(data)\n"
    )
    symbols = [
        {"type": "function", "name": "authenticate_user", "file": "auth.py",
         "line_start": 1, "line_end": 3, "parameters": ["username", "password"], "parent": None},
        {"type": "function", "name": "render_chart", "file": "auth.py",
         "line_start": 5, "line_end": 6, "parameters": ["data"], "parent": None},
    ]
    return symbols


def test_run_embedding_skips_gracefully_when_qdrant_unreachable(tmp_path):
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols=[])
    with patch("app.services.embedding_service.get_qdrant_client", return_value=_FakeUnreachableClient()):
        with pytest.raises(EmbeddingSkipped):
            run_embedding(db=_FakeDb(), repository=repo, analysis=analysis)


def test_run_embedding_real_round_trip_with_local_qdrant(tmp_path):
    """The full pipeline against the real (local-mode) Qdrant engine:
    chunk two functions from real source text, embed with the offline
    HashingEmbedder (no network in this sandbox — see embedder.py), upsert,
    then search for something semantically closer to one of the two."""
    symbols = _write_sample_repo(tmp_path)
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols=symbols)

    local_client = VectorStoreClient(qdrant_client=QdrantClient(":memory:"))

    with patch("app.services.embedding_service.get_qdrant_client", return_value=local_client):
        summary = run_embedding(db=_FakeDb(), repository=repo, analysis=analysis)

        assert summary["chunk_count"] == 2
        assert summary["by_type"] == {"function": 2}
        assert analysis.stats["embedding"] == summary
        # existing stats preserved, not overwritten
        assert analysis.stats["function_count"] == 1

        results = search_repository("repo-1", "authenticate credentials login", limit=5)

    assert len(results) == 2
    # The auth-related function should rank above the unrelated chart one
    # for an auth-flavored query — real cosine similarity over real chunks.
    assert results[0]["symbol"] == "authenticate_user"
    assert results[0]["file"] == "auth.py"
    assert "text" in results[0]  # payload is self-contained (chunker.py)


def test_run_embedding_scopes_results_to_repository(tmp_path):
    """Two different 'repositories' embedded into the same collection —
    search must not leak results across repository_id."""
    symbols = _write_sample_repo(tmp_path)
    local_client = VectorStoreClient(qdrant_client=QdrantClient(":memory:"))

    with patch("app.services.embedding_service.get_qdrant_client", return_value=local_client):
        repo1 = _FakeRepository(tmp_path)
        repo1.id = "repo-A"
        run_embedding(db=_FakeDb(), repository=repo1, analysis=_FakeAnalysis(symbols))

        repo2 = _FakeRepository(tmp_path)
        repo2.id = "repo-B"
        run_embedding(db=_FakeDb(), repository=repo2, analysis=_FakeAnalysis(symbols))

        results_a = search_repository("repo-A", "authenticate", limit=10)
        results_b = search_repository("repo-B", "authenticate", limit=10)

    assert all(r["repository_id"] == "repo-A" for r in results_a)
    assert all(r["repository_id"] == "repo-B" for r in results_b)
    assert len(results_a) == 2
    assert len(results_b) == 2


def test_run_embedding_re_analysis_replaces_not_duplicates(tmp_path):
    symbols = _write_sample_repo(tmp_path)
    repo = _FakeRepository(tmp_path)
    local_client = VectorStoreClient(qdrant_client=QdrantClient(":memory:"))

    with patch("app.services.embedding_service.get_qdrant_client", return_value=local_client):
        run_embedding(db=_FakeDb(), repository=repo, analysis=_FakeAnalysis(symbols))
        run_embedding(db=_FakeDb(), repository=repo, analysis=_FakeAnalysis(symbols))
        results = search_repository("repo-1", "authenticate", limit=100)

    assert len(results) == 2  # not 4 — delete_by_repository cleared stale points first
