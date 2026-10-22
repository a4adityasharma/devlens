"""
Verifies the graph *shape* graph_builder.py produces — actual nodes and
relationships, not just "a write call happened" (that's already covered by
test_graph_builder.py's mock-based tests). Uses Neo4jSimulator (see its
module docstring for why: no live Neo4j is reachable in this sandbox).
"""
from pathlib import Path

from app.analyzer.repository_analyzer import analyze_repository
from app.knowledge.graph_builder import build_knowledge_graph
from tests.neo4j_simulator import Neo4jSimulator

FIXTURES = Path(__file__).parent / "fixtures"

HAND_BUILT_SYMBOLS = [
    {"type": "import", "name": "os", "file": "app.py", "line_start": 1, "line_end": 1,
     "parameters": [], "parent": None, "source": "os", "caller": None, "receiver": None},
    {"type": "function", "name": "generate_token", "file": "app.py", "line_start": 3, "line_end": 4,
     "parameters": ["username"], "parent": None, "source": None, "caller": None, "receiver": None},
    {"type": "class", "name": "UserService", "file": "app.py", "line_start": 6, "line_end": 12,
     "parameters": [], "parent": None, "source": None, "caller": None, "receiver": None},
    {"type": "method", "name": "authenticate", "file": "app.py", "line_start": 7, "line_end": 9,
     "parameters": ["self", "username"], "parent": "UserService", "source": None,
     "caller": None, "receiver": None},
    {"type": "call", "name": "generate_token", "file": "app.py", "line_start": 8, "line_end": 8,
     "parameters": [], "parent": "UserService", "source": None,
     "caller": "UserService.authenticate", "receiver": None},
    {"type": "method", "name": "validate", "file": "app.py", "line_start": 10, "line_end": 11,
     "parameters": ["self", "token"], "parent": "UserService", "source": None,
     "caller": None, "receiver": None},
    {"type": "call", "name": "validate", "file": "app.py", "line_start": 8, "line_end": 8,
     "parameters": [], "parent": "UserService", "source": None,
     "caller": "UserService.authenticate", "receiver": "self"},
]


def test_simulated_graph_has_correct_containment_chain():
    sim = Neo4jSimulator()
    build_knowledge_graph(sim, "repo-1", HAND_BUILT_SYMBOLS)

    [repo] = sim.match("Repository", id="repo-1")
    [file] = sim.match("File", repo_id="repo-1", path="app.py")
    [cls] = sim.match("Class", repo_id="repo-1", file="app.py", name="UserService")
    [method] = sim.match("Method", repo_id="repo-1", file="app.py", name="authenticate")
    [module] = sim.match("Module", repo_id="repo-1", name="os")

    contains = sim.relationships_of_type("CONTAINS")
    defines = sim.relationships_of_type("DEFINES")
    imports = sim.relationships_of_type("IMPORTS")

    assert any(r.start == repo.id and r.end == file.id for r in contains), \
        "Repository -[:CONTAINS]-> File missing"
    assert any(r.start == cls.id and r.end == method.id for r in contains), \
        "Class -[:CONTAINS]-> Method missing"
    assert any(r.start == file.id and r.end == cls.id for r in defines), \
        "File -[:DEFINES]-> Class missing"
    assert any(r.start == file.id and r.end == module.id for r in imports), \
        "File -[:IMPORTS]-> Module missing"


def test_simulated_graph_resolves_calls_to_correct_targets():
    sim = Neo4jSimulator()
    build_knowledge_graph(sim, "repo-1", HAND_BUILT_SYMBOLS)

    [authenticate] = sim.match("Method", name="authenticate")
    [generate_token] = sim.match("Function", name="generate_token")
    [validate] = sim.match("Method", name="validate")

    calls = sim.relationships_of_type("CALLS")
    call_targets = {(r.start, r.end) for r in calls}

    assert (authenticate.id, generate_token.id) in call_targets, \
        "authenticate() should CALL generate_token() (bare call, no receiver)"
    assert (authenticate.id, validate.id) in call_targets, \
        "authenticate() should CALL validate() (self.validate(...))"

    # every CALLS edge should be tagged as a name-based (not type-resolved) match
    for r in calls:
        assert r.props["match_type"] == "by_name"


def test_simulated_graph_rebuild_replaces_stale_data_not_duplicates():
    sim = Neo4jSimulator()
    build_knowledge_graph(sim, "repo-1", HAND_BUILT_SYMBOLS)
    first_node_count = len(sim.nodes)
    first_rel_count = len(sim.rels)

    # Re-run against the SAME symbols (simulating a re-analysis of an
    # unchanged repo) — should not accumulate duplicate nodes/edges.
    build_knowledge_graph(sim, "repo-1", HAND_BUILT_SYMBOLS)

    assert len(sim.nodes) == first_node_count
    assert len(sim.rels) == first_rel_count


def test_simulated_graph_scoped_to_repository_does_not_touch_other_repos():
    sim = Neo4jSimulator()
    build_knowledge_graph(sim, "repo-1", HAND_BUILT_SYMBOLS)
    build_knowledge_graph(sim, "repo-2", HAND_BUILT_SYMBOLS)

    repo1_files = sim.match("File", repo_id="repo-1")
    repo2_files = sim.match("File", repo_id="repo-2")
    assert len(repo1_files) == 1
    assert len(repo2_files) == 1
    assert repo1_files[0].id != repo2_files[0].id

    # Re-analyzing repo-1 must not delete repo-2's graph.
    build_knowledge_graph(sim, "repo-1", HAND_BUILT_SYMBOLS)
    assert len(sim.match("File", repo_id="repo-2")) == 1


def test_simulated_graph_against_real_multi_language_fixtures():
    """Same real symbol set used in earlier sessions' manual smoke test
    (3 files across Python/JS/TS, 29 symbols) — this time asserting on
    actual resulting graph shape instead of just counting write calls."""
    result = analyze_repository(FIXTURES)
    symbols = result["symbols"]

    sim = Neo4jSimulator()
    summary = build_knowledge_graph(sim, "fixtures-repo", symbols)

    assert len(sim.match("File", repo_id="fixtures-repo")) == summary["file_count"] == 3
    assert len(sim.match("Class", repo_id="fixtures-repo")) == summary["class_count"] == 3
    assert len(sim.match("Function", repo_id="fixtures-repo")) == summary["function_count"] == 6
    assert len(sim.match("Method", repo_id="fixtures-repo")) == summary["method_count"] == 7

    # Cross-check one specific known relationship from sample.py:
    # UserService.authenticate() calls self.validate(...). Filter by file
    # since "validate" is also a method name in sample.ts's TokenValidator
    # — this fixture set deliberately reuses that name to make sure the
    # simulator (and the real Cypher it mirrors) doesn't accidentally
    # collapse same-named methods across different files/classes.
    [authenticate] = sim.match("Method", repo_id="fixtures-repo", file="sample.py", name="authenticate")
    [validate] = sim.match("Method", repo_id="fixtures-repo", file="sample.py", name="validate")
    calls = sim.relationships_of_type("CALLS")
    assert any(r.start == authenticate.id and r.end == validate.id for r in calls)


def test_ambiguous_callee_name_fans_out_to_all_matches():
    """Two unrelated classes both define save(); a call to `x.save()`
    should (per the documented MVP behavior) link to BOTH — this is the
    'name-only resolution' tradeoff graph_builder.py's docstring warns
    about, verified here so the fan-out behavior is explicit and can't
    silently change."""
    symbols = [
        {"type": "class", "name": "Invoice", "file": "a.py", "line_start": 1, "line_end": 5,
         "parameters": [], "parent": None, "source": None, "caller": None, "receiver": None},
        {"type": "method", "name": "save", "file": "a.py", "line_start": 2, "line_end": 3,
         "parameters": ["self"], "parent": "Invoice", "source": None, "caller": None, "receiver": None},
        {"type": "class", "name": "Draft", "file": "b.py", "line_start": 1, "line_end": 5,
         "parameters": [], "parent": None, "source": None, "caller": None, "receiver": None},
        {"type": "method", "name": "save", "file": "b.py", "line_start": 2, "line_end": 3,
         "parameters": ["self"], "parent": "Draft", "source": None, "caller": None, "receiver": None},
        {"type": "function", "name": "process", "file": "c.py", "line_start": 1, "line_end": 4,
         "parameters": [], "parent": None, "source": None, "caller": None, "receiver": None},
        {"type": "call", "name": "save", "file": "c.py", "line_start": 2, "line_end": 2,
         "parameters": [], "parent": None, "source": None, "caller": "process", "receiver": "obj"},
    ]
    sim = Neo4jSimulator()
    build_knowledge_graph(sim, "repo-1", symbols)

    [process] = sim.match("Function", name="process")
    invoice_save = sim.match("Method", file="a.py", name="save")[0]
    draft_save = sim.match("Method", file="b.py", name="save")[0]

    calls = sim.relationships_of_type("CALLS")
    call_ends = {r.end for r in calls if r.start == process.id}
    assert call_ends == {invoice_save.id, draft_save.id}
