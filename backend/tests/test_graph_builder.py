from app.knowledge.graph_builder import build_knowledge_graph, build_write_plan


SAMPLE_SYMBOLS = [
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
    {"type": "function", "name": "top_level_helper", "file": "app.py", "line_start": 14, "line_end": 16,
     "parameters": ["a", "b"], "parent": None, "source": None, "caller": None, "receiver": None},
    {"type": "call", "name": "UserService", "file": "app.py", "line_start": 15, "line_end": 15,
     "parameters": [], "parent": None, "source": None, "caller": "top_level_helper", "receiver": None},
]


class MockNeo4jClient:
    """Captures every write call instead of talking to a real database, so
    the graph-shaping logic can be verified without a live Neo4j instance
    (none is reachable in this environment). See docs/PROGRESS.md for how
    to verify this same plan against a real Neo4j via docker compose."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run_write(self, cypher: str, **params):
        self.calls.append((cypher, params))


def test_write_plan_shapes_nodes_correctly():
    plan = build_write_plan("repo-1", SAMPLE_SYMBOLS)
    by_label = {step.label: step for step in plan}

    assert by_label["create_files"].params["files"] == [{"path": "app.py"}]
    assert by_label["create_classes"].params["classes"] == [{"file": "app.py", "name": "UserService"}]
    assert {f["name"] for f in by_label["create_functions"].params["functions"]} == {
        "generate_token", "top_level_helper",
    }
    assert {m["name"] for m in by_label["create_methods"].params["methods"]} == {
        "authenticate", "validate",
    }
    assert by_label["create_imports"].params["imports"] == [{"file": "app.py", "module": "os"}]


def test_write_plan_splits_calls_by_caller_kind():
    plan = build_write_plan("repo-1", SAMPLE_SYMBOLS)
    by_label = {step.label: step for step in plan}

    # Two calls originate from inside a method (UserService.authenticate)
    method_calls = by_label["create_calls_from_method"].params["calls"]
    assert {c["callee_name"] for c in method_calls} == {"generate_token", "validate"}
    assert all(c["caller_parent"] == "UserService" and c["caller_name"] == "authenticate" for c in method_calls)

    # One call originates from a top-level function
    function_calls = by_label["create_calls_from_function"].params["calls"]
    assert function_calls == [{
        "file": "app.py", "callee_name": "UserService", "line": 15, "caller_name": "top_level_helper",
    }]


def test_write_plan_omits_call_steps_when_no_calls_present():
    symbols_without_calls = [s for s in SAMPLE_SYMBOLS if s["type"] != "call"]
    plan = build_write_plan("repo-1", symbols_without_calls)
    labels = {step.label for step in plan}
    assert "create_calls_from_method" not in labels
    assert "create_calls_from_function" not in labels


def test_write_plan_clears_existing_repo_graph_first():
    plan = build_write_plan("repo-1", SAMPLE_SYMBOLS)
    assert plan[0].label == "clear_existing"
    assert plan[0].params == {"repo_id": "repo-1"}


def test_build_knowledge_graph_executes_full_plan_against_client():
    client = MockNeo4jClient()
    summary = build_knowledge_graph(client, "repo-1", SAMPLE_SYMBOLS)

    # Every planned step actually got sent to the client.
    executed_labels = [label for label, _ in [(s.label, None) for s in build_write_plan("repo-1", SAMPLE_SYMBOLS)]]
    assert len(client.calls) == len(executed_labels)

    assert summary["file_count"] == 1
    assert summary["class_count"] == 1
    assert summary["function_count"] == 2
    assert summary["method_count"] == 2
    assert summary["import_count"] == 1
    assert summary["call_relationship_candidates"] == 3


def test_module_level_call_with_no_enclosing_function_is_skipped():
    module_level_call = {
        "type": "call", "name": "setup", "file": "app.py", "line_start": 1, "line_end": 1,
        "parameters": [], "parent": None, "source": None, "caller": None, "receiver": None,
    }
    plan = build_write_plan("repo-1", [module_level_call])
    labels = {step.label for step in plan}
    assert "create_calls_from_method" not in labels
    assert "create_calls_from_function" not in labels
