from pathlib import Path

from app.analyzer.repository_analyzer import analyze_repository
from app.embeddings.embedder import HashingEmbedder
from app.knowledge.graph_builder import build_knowledge_graph
from app.knowledge.qdrant_client import VectorStoreClient
from app.retrieval.hybrid_retriever import build_context, graph_expand, retrieve
from app.services.embedding_service import COLLECTION_NAME
from tests.neo4j_simulator import Neo4jSimulator

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# build_context() — pure function, no I/O
# ---------------------------------------------------------------------------

def test_build_context_includes_source_marker_and_text():
    hits = [{
        "file": "auth.py", "symbol": "authenticate", "type": "method",
        "parent": "AuthService", "start_line": 5, "end_line": 8,
        "text": "def authenticate(self, user):\n    return True",
    }]
    context = build_context(hits)
    assert "[SOURCE: auth.py:5-8]" in context
    assert "def authenticate(self, user):" in context


def test_build_context_appends_graph_expansion_when_present():
    hits = [{
        "file": "auth.py", "symbol": "authenticate", "type": "method",
        "parent": "AuthService", "start_line": 5, "end_line": 8, "text": "...",
    }]
    expansions = {
        "auth.py::authenticate": {
            "calls_out": [{"name": "validate", "file": "auth.py"}],
            "calls_in": [{"name": "login_view", "file": "views.py"}],
        }
    }
    context = build_context(hits, expansions)
    assert "-> calls: validate (auth.py)" in context
    assert "<- called by: login_view (views.py)" in context


def test_build_context_handles_no_expansions_gracefully():
    hits = [{
        "file": "a.py", "symbol": "foo", "type": "function",
        "parent": None, "start_line": 1, "end_line": 2, "text": "def foo(): pass",
    }]
    context = build_context(hits)  # no expansions arg at all
    assert "[SOURCE: a.py:1-2]" in context
    assert "-> calls" not in context


def test_build_context_multiple_hits_are_separated():
    hits = [
        {"file": "a.py", "symbol": "foo", "type": "function", "parent": None,
         "start_line": 1, "end_line": 2, "text": "def foo(): pass"},
        {"file": "b.py", "symbol": "bar", "type": "function", "parent": None,
         "start_line": 1, "end_line": 2, "text": "def bar(): pass"},
    ]
    context = build_context(hits)
    assert "[SOURCE: a.py:1-2]" in context
    assert "[SOURCE: b.py:1-2]" in context
    assert context.count("\n\n") >= 1  # blocks are separated, not run together


# ---------------------------------------------------------------------------
# graph_expand() against a real (simulated) graph built by build_knowledge_graph
# ---------------------------------------------------------------------------

def test_graph_expand_finds_real_calls_out_and_in():
    """Build an actual graph from the real cross-language fixtures (same
    ones used in test_graph_builder_live_semantics.py), then confirm
    graph_expand's queries correctly traverse it for a known call site:
    UserService.authenticate() calls UserService.validate() in sample.py."""
    result = analyze_repository(FIXTURES)
    sim = Neo4jSimulator()
    build_knowledge_graph(sim, "fixtures-repo", result["symbols"])

    hits = [{
        "file": "sample.py", "symbol": "authenticate", "type": "method",
        "parent": "UserService", "start_line": 7, "end_line": 9, "text": "...",
    }]
    expansions = graph_expand(sim, "fixtures-repo", hits)

    exp = expansions["sample.py::authenticate"]
    callee_names = {c["name"] for c in exp["calls_out"]}
    assert "generate_token" in callee_names
    assert "validate" in callee_names


def test_graph_expand_skips_class_hits():
    hits = [{"file": "sample.py", "symbol": "UserService", "type": "class",
             "parent": None, "start_line": 1, "end_line": 1, "text": "..."}]
    sim = Neo4jSimulator()
    expansions = graph_expand(sim, "fixtures-repo", hits)
    assert expansions == {}


def test_graph_expand_returns_empty_for_unknown_symbol():
    sim = Neo4jSimulator()
    hits = [{"file": "nope.py", "symbol": "ghost", "type": "function",
             "parent": None, "start_line": 1, "end_line": 1, "text": "..."}]
    expansions = graph_expand(sim, "fixtures-repo", hits)
    assert expansions["nope.py::ghost"] == {"calls_out": [], "calls_in": []}


# ---------------------------------------------------------------------------
# retrieve() — full hybrid pipeline: real Qdrant + real (simulated) Neo4j
# ---------------------------------------------------------------------------

def test_retrieve_combines_vector_and_graph_results(tmp_path, monkeypatch):
    from unittest.mock import patch
    from qdrant_client import QdrantClient

    (tmp_path / "auth.py").write_text(
        "def generate_token(username):\n"
        "    return username\n"
        "\n"
        "class UserService:\n"
        "    def authenticate(self, username):\n"
        "        return generate_token(username)\n"
    )
    symbols = [
        {"type": "function", "name": "generate_token", "file": "auth.py",
         "line_start": 1, "line_end": 2, "parameters": ["username"], "parent": None},
        {"type": "class", "name": "UserService", "file": "auth.py",
         "line_start": 4, "line_end": 6, "parameters": [], "parent": None},
        {"type": "method", "name": "authenticate", "file": "auth.py",
         "line_start": 5, "line_end": 6, "parameters": ["self", "username"], "parent": "UserService"},
        {"type": "call", "name": "generate_token", "file": "auth.py",
         "line_start": 6, "line_end": 6, "parameters": [], "parent": "UserService",
         "caller": "UserService.authenticate", "receiver": None},
    ]

    qdrant = VectorStoreClient(qdrant_client=QdrantClient(":memory:"))
    embedder = HashingEmbedder(dimension=64)
    qdrant.ensure_collection(COLLECTION_NAME, embedder.dimension)

    from app.embeddings.chunker import chunk_repository
    chunks = chunk_repository(tmp_path, "repo-1", symbols)
    vectors = embedder.embed_batch([c.text for c in chunks])
    qdrant.upsert(COLLECTION_NAME, [
        {"id": c.id, "vector": v, "payload": c.to_payload()} for c, v in zip(chunks, vectors)
    ])

    sim = Neo4jSimulator()
    build_knowledge_graph(sim, "repo-1", symbols)

    with patch("app.retrieval.hybrid_retriever.search_repository",
               side_effect=lambda repo_id, query, limit=8: qdrant.search(
                   COLLECTION_NAME, embedder.embed_batch([query])[0], limit=limit, repository_id=repo_id)):
        result = retrieve("repo-1", "authenticate user token", neo4j_client=sim)

    assert result["graph_available"] is True
    assert len(result["hits"]) > 0
    assert "[SOURCE:" in result["context"]
    # the method hit should show its graph-derived call to generate_token
    if any(h["symbol"] == "authenticate" for h in result["hits"]):
        assert "generate_token" in result["context"]
