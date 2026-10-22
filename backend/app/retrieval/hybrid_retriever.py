"""
Hybrid Retrieval (Phase 6 / architecture doc §13).

Combines two independently-built retrieval paths for one question:
  - Vector search over chunked symbols (Phase 5 / app.services.embedding_service)
  - Graph expansion: for each vector hit that's a function/method, pull its
    immediate CALLS neighbors (both directions) from Neo4j, so a question
    like "explain the authentication flow" surfaces related functions the
    vector search alone might rank too low to include.

Split into a pure function (`build_context`, no I/O — testable with hand-
built inputs) and I/O adapters (`graph_expand`, `retrieve`), same
separation-of-concerns pattern every prior phase in this project used.

Every context block `build_context` emits carries an explicit
`[SOURCE: file:start-end]` marker. This is deliberate: it's the anchor
app.services.chat_service.py's citation validator checks the LLM's claimed
sources against, so a citation the LLM invents (rather than copies from
here) gets caught rather than trusted. Don't change this marker format
without updating chat_service.py's parser to match.
"""
from app.services.embedding_service import EmbeddingSkipped, search_repository

# -- Cypher templates for the graph-expansion side --
# Mirrors app/knowledge/graph_builder.py's function-vs-method split (Method
# nodes carry a `parent` property Function nodes don't have, so they need
# a different MATCH pattern) — same reasoning, see that module's docstring.

_CALLS_OUT_FUNCTION = """
MATCH (n:Function {repo_id: $repo_id, file: $file, name: $name})-[:CALLS]->(callee)
RETURN DISTINCT callee.name AS name, callee.file AS file, labels(callee) AS labels
"""

_CALLS_OUT_METHOD = """
MATCH (n:Method {repo_id: $repo_id, file: $file, parent: $parent, name: $name})-[:CALLS]->(callee)
RETURN DISTINCT callee.name AS name, callee.file AS file, labels(callee) AS labels
"""

_CALLS_IN_FUNCTION = """
MATCH (caller)-[:CALLS]->(n:Function {repo_id: $repo_id, file: $file, name: $name})
RETURN DISTINCT caller.name AS name, caller.file AS file, labels(caller) AS labels
"""

_CALLS_IN_METHOD = """
MATCH (caller)-[:CALLS]->(n:Method {repo_id: $repo_id, file: $file, parent: $parent, name: $name})
RETURN DISTINCT caller.name AS name, caller.file AS file, labels(caller) AS labels
"""


def _hit_key(hit: dict) -> str:
    return f"{hit['file']}::{hit['symbol']}"


def graph_expand(client, repository_id: str, hits: list[dict], limit_per_hit: int = 5) -> dict[str, dict]:
    """client: anything exposing `.run_query(cypher, **params) -> list[dict]`
    (a real Neo4jClient, or tests/neo4j_simulator.py's Neo4jSimulator).

    Returns {"file::symbol": {"calls_out": [...], "calls_in": [...]}} for
    every function/method hit. Class hits and hits with no graph data
    (unreachable Neo4j, symbol not in the graph) are simply absent from
    the result — callers should treat a missing key as "no graph context
    available", not an error.
    """
    expansions: dict[str, dict] = {}
    for hit in hits:
        if hit.get("type") not in ("function", "method"):
            continue
        file, name, parent = hit["file"], hit["symbol"], hit.get("parent")
        params = {"repo_id": repository_id, "file": file, "name": name}
        if parent:
            params["parent"] = parent
            calls_out = client.run_query(_CALLS_OUT_METHOD, **params)
            calls_in = client.run_query(_CALLS_IN_METHOD, **params)
        else:
            calls_out = client.run_query(_CALLS_OUT_FUNCTION, **params)
            calls_in = client.run_query(_CALLS_IN_FUNCTION, **params)

        expansions[_hit_key(hit)] = {
            "calls_out": [r for r in calls_out if r.get("name")][:limit_per_hit],
            "calls_in": [r for r in calls_in if r.get("name")][:limit_per_hit],
        }
    return expansions


def build_context(hits: list[dict], expansions: dict[str, dict] | None = None) -> str:
    """Pure function: vector hits (+ optional graph expansions) -> one text
    blob for the LLM prompt. No I/O, so this is unit-tested directly with
    hand-built inputs in tests/test_hybrid_retriever.py."""
    expansions = expansions or {}
    blocks = []
    for hit in hits:
        marker = f"[SOURCE: {hit['file']}:{hit['start_line']}-{hit['end_line']}]"
        header = f"{marker} {hit['type']} {hit['symbol']}"
        block = f"{header}\n{hit['text']}"

        exp = expansions.get(_hit_key(hit))
        if exp:
            if exp["calls_out"]:
                names = ", ".join(f"{c['name']} ({c['file']})" for c in exp["calls_out"])
                block += f"\n  -> calls: {names}"
            if exp["calls_in"]:
                names = ", ".join(f"{c['name']} ({c['file']})" for c in exp["calls_in"])
                block += f"\n  <- called by: {names}"
        blocks.append(block)
    return "\n\n".join(blocks)


def retrieve(repository_id: str, query: str, neo4j_client=None, limit: int = 8) -> dict:
    """Top-level hybrid retrieval for one question.

    Returns {"hits": [...], "context": "...", "graph_available": bool}.
    Vector search failing (Qdrant unreachable / nothing embedded yet)
    surfaces as an empty hits list + empty context, not an exception —
    callers (chat_service.py) decide what to say to the user about that.
    """
    try:
        hits = search_repository(repository_id, query, limit=limit)
    except EmbeddingSkipped:
        hits = []

    graph_available = False
    expansions: dict[str, dict] = {}
    if hits and neo4j_client is not None and neo4j_client.verify_connectivity():
        graph_available = True
        expansions = graph_expand(neo4j_client, repository_id, hits)

    return {
        "hits": hits,
        "context": build_context(hits, expansions),
        "graph_available": graph_available,
    }
