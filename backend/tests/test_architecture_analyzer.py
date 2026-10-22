"""
Every test here uses real symbol data — either the project's own
multi-language fixtures or (for the most interesting cases) DevLens AI's
own backend source code, self-analyzed. No mocking is possible or needed:
this module is pure computation over a plain symbols list, so "real"
verification is simply "run it on real data and check the output," the
same standard test_chunker.py and test_graph_builder_live_semantics.py
already established for this project's other pure-logic modules.
"""
from pathlib import Path

from app.agents.architecture_analyzer import analyze_architecture, build_layer_graph, generate_mermaid, infer_layer
from app.analyzer.repository_analyzer import analyze_repository

FIXTURES = Path(__file__).parent / "fixtures"
BACKEND_SRC = Path(__file__).parent.parent / "app"


def test_infer_layer_matches_known_keywords_at_any_depth():
    assert infer_layer("app/services/repository_service.py") == "Services"
    assert infer_layer("src/app/controllers/user_controller.py") == "Controllers"
    assert infer_layer("backend/app/models/models.py") == "Models"


def test_infer_layer_falls_back_to_parent_directory_name():
    # "flask" isn't a known keyword — falls back to the immediate parent,
    # title-cased, rather than forcing it into some fixed vocabulary.
    assert infer_layer("src/flask/cli.py") == "Flask"


def test_infer_layer_root_file_has_no_parent():
    assert infer_layer("main.py") == "Root"


def test_infer_layer_prefers_deepest_matching_component():
    # "app" isn't a keyword, "services" is — should match "services" even
    # though it's not the first path component.
    assert infer_layer("backend/app/services/foo.py") == "Services"


def test_build_layer_graph_on_flat_fixtures_has_no_cross_layer_edges():
    """The existing tests/fixtures/*.py|js|ts are all directly under one
    directory with no subdirectories — every file lands in the same
    'Root' layer, so same-layer calls are correctly excluded, leaving zero
    edges. This is the honest, correct output for a genuinely flat
    layout, not a failure of the heuristic."""
    result = analyze_repository(FIXTURES)
    graph = build_layer_graph(result["symbols"])
    assert list(graph.layers.keys()) == ["Root"]
    assert graph.layers["Root"]["file_count"] == 3
    assert graph.edges == []


def test_architecture_agent_self_analysis_finds_real_layers():
    """The strongest test in this file: run the Architecture Agent on
    DevLens AI's own backend source. This project genuinely has layered
    structure (app/services/, app/api/routes/, app/models/, etc.), so this
    checks the agent finds real, previously-known-correct structure, not
    just that it runs without crashing."""
    result = analyze_repository(BACKEND_SRC)
    arch = analyze_architecture(result["symbols"])

    assert "Services" in arch["layers"]
    assert "Models" in arch["layers"]
    assert "Routes" in arch["layers"]
    assert arch["layers"]["Services"]["file_count"] >= 5  # repository/analysis/graph/embedding/chat/security services

    # Known-real relationships in this codebase: API routes call into
    # services, and services call into the knowledge-layer clients.
    edge_pairs = {(e["from"], e["to"]) for e in arch["edges"]}
    assert ("Routes", "Services") in edge_pairs
    assert ("Services", "Knowledge") in edge_pairs


def test_build_layer_graph_excludes_same_file_calls():
    symbols = [
        {"type": "function", "name": "helper", "file": "a.py", "line_start": 1, "line_end": 2},
        {"type": "function", "name": "main", "file": "a.py", "line_start": 4, "line_end": 5},
        {"type": "call", "name": "helper", "file": "a.py", "caller": "main"},
    ]
    graph = build_layer_graph(symbols)
    assert graph.edges == []  # same file -> same layer -> excluded regardless


def test_build_layer_graph_ambiguous_callee_name_creates_multiple_edges():
    """Same by-name-only ambiguity as graph_builder.py's CALLS resolution
    — documented behavior, not a bug, verified explicitly like that
    module's own test_ambiguous_callee_name_fans_out_to_all_matches."""
    symbols = [
        {"type": "function", "name": "process", "file": "controllers/main.py", "line_start": 1, "line_end": 2},
        {"type": "function", "name": "save", "file": "services/invoice.py", "line_start": 1, "line_end": 2},
        {"type": "function", "name": "save", "file": "services/draft.py", "line_start": 1, "line_end": 2},
        {"type": "call", "name": "save", "file": "controllers/main.py", "caller": "process"},
    ]
    graph = build_layer_graph(symbols)
    assert len(graph.edges) == 1  # both targets are in the same "Services" layer -> one aggregated edge
    assert graph.edges[0] == {"from": "Controllers", "to": "Services", "count": 2}


def test_generate_mermaid_produces_valid_looking_graph_syntax():
    symbols = [
        {"type": "function", "name": "handler", "file": "routes/api.py", "line_start": 1, "line_end": 2},
        {"type": "function", "name": "process", "file": "services/core.py", "line_start": 1, "line_end": 2},
        {"type": "call", "name": "process", "file": "routes/api.py", "caller": "handler"},
    ]
    result = analyze_architecture(symbols)
    mermaid = result["mermaid"]
    assert mermaid.startswith("graph TD")
    assert "Routes (1 file)" in mermaid
    assert "Services (1 file)" in mermaid
    assert "-->|1|" in mermaid


def test_empty_symbols_produces_empty_but_valid_diagram():
    result = analyze_architecture([])
    assert result["layers"] == {}
    assert result["edges"] == []
    assert result["mermaid"] == "graph TD"
