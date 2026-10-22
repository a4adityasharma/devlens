"""
Knowledge Graph Builder (Phase 4 / architecture doc §9-10).

Consumes the flat `symbols` list produced by app/analyzer/* (Phase 3) for
one repository and writes it into Neo4j as:

    (:Repository)-[:CONTAINS]->(:File)-[:DEFINES]->(:Class)
    (:Class)-[:CONTAINS]->(:Method)
    (:File)-[:DEFINES]->(:Function)
    (:File)-[:IMPORTS]->(:Module)
    (:Function|:Method|:Class)-[:CALLS]->(:Function|:Method|:Class)

CALLS resolution is intentionally simple for the MVP: a call's callee is
matched **by name only**, against any Class/Function/Method in the same
repository (all three carry a shared `:Callable` label for this purpose).
This means `obj.save()` will link to every `save` method in the repo if
there happen to be several unrelated classes with that method name — see
architecture doc §36 / docs/PROGRESS.md for why full type-aware call
resolution is out of scope for MVP. Every CALLS relationship written by
this module is tagged `match_type: "by_name"` so downstream consumers
(agents, validation layer) can see it's a heuristic, not a guarantee.

Design note: `build_knowledge_graph()` takes a `Neo4jClient`-like object as
a parameter rather than importing a global client directly, and every
Cypher statement + its params can be inspected without a live database via
`build_write_plan()`. This is what makes it possible to unit test the
*logic* (which nodes/edges get created from which symbols) in this sandbox,
where no Neo4j server is reachable — the actual Cypher execution is a thin,
separately-verified adapter (app/knowledge/neo4j_client.py).
"""
from dataclasses import dataclass, field


@dataclass
class WriteStep:
    """One Cypher statement + its parameters, in execution order."""
    label: str
    cypher: str
    params: dict = field(default_factory=dict)


_CLEAR_REPO = """
MATCH (n) WHERE n.repo_id = $repo_id OR (n:Repository AND n.id = $repo_id)
DETACH DELETE n
"""

_CREATE_REPO = """
MERGE (r:Repository {id: $repo_id})
"""

_CREATE_FILES = """
MATCH (r:Repository {id: $repo_id})
UNWIND $files AS f
MERGE (file:File {repo_id: $repo_id, path: f.path})
MERGE (r)-[:CONTAINS]->(file)
"""

_CREATE_CLASSES = """
UNWIND $classes AS c
MATCH (file:File {repo_id: $repo_id, path: c.file})
MERGE (cls:Class:Callable {repo_id: $repo_id, file: c.file, name: c.name})
MERGE (file)-[:DEFINES]->(cls)
"""

_CREATE_FUNCTIONS = """
UNWIND $functions AS fn
MATCH (file:File {repo_id: $repo_id, path: fn.file})
MERGE (f:Function:Callable {repo_id: $repo_id, file: fn.file, name: fn.name})
MERGE (file)-[:DEFINES]->(f)
"""

_CREATE_METHODS = """
UNWIND $methods AS m
MATCH (file:File {repo_id: $repo_id, path: m.file})
MATCH (cls:Class {repo_id: $repo_id, file: m.file, name: m.parent})
MERGE (meth:Method:Callable {repo_id: $repo_id, file: m.file, name: m.name, parent: m.parent})
MERGE (file)-[:DEFINES]->(meth)
MERGE (cls)-[:CONTAINS]->(meth)
"""

_CREATE_IMPORTS = """
UNWIND $imports AS imp
MATCH (file:File {repo_id: $repo_id, path: imp.file})
MERGE (mod:Module {repo_id: $repo_id, name: imp.module})
MERGE (file)-[:IMPORTS]->(mod)
"""

_CREATE_CALLS_FROM_FUNCTION = """
UNWIND $calls AS call
MATCH (caller:Function {repo_id: $repo_id, file: call.file, name: call.caller_name})
MATCH (callee:Callable {repo_id: $repo_id, name: call.callee_name})
MERGE (caller)-[rel:CALLS]->(callee)
SET rel.match_type = 'by_name', rel.line = call.line
"""

_CREATE_CALLS_FROM_METHOD = """
UNWIND $calls AS call
MATCH (caller:Method {repo_id: $repo_id, file: call.file, parent: call.caller_parent, name: call.caller_name})
MATCH (callee:Callable {repo_id: $repo_id, name: call.callee_name})
MERGE (caller)-[rel:CALLS]->(callee)
SET rel.match_type = 'by_name', rel.line = call.line
"""


def _split_caller(caller: str | None) -> tuple[str | None, str | None]:
    """'AuthService.login' -> ('AuthService', 'login'); 'top_level' -> (None, 'top_level')."""
    if not caller:
        return None, None
    if "." in caller:
        parent, name = caller.rsplit(".", 1)
        return parent, name
    return None, caller


def build_write_plan(repository_id: str, symbols: list[dict]) -> list[WriteStep]:
    """Pure function: symbols -> ordered list of (cypher, params).

    No I/O. This is what test_graph_builder.py exercises directly, so the
    graph-shaping logic is verified without needing a live Neo4j instance.
    """
    files = sorted({s["file"] for s in symbols if s.get("file")})
    classes = [s for s in symbols if s["type"] == "class"]
    functions = [s for s in symbols if s["type"] == "function" and s.get("name")]
    methods = [s for s in symbols if s["type"] == "method" and s.get("name") and s.get("parent")]
    imports = [s for s in symbols if s["type"] == "import" and s.get("source")]
    calls = [s for s in symbols if s["type"] == "call" and s.get("name")]

    function_calls = []
    method_calls = []
    for c in calls:
        parent, name = _split_caller(c.get("caller"))
        if name is None:
            continue  # module-level call with no enclosing function/method — skip for MVP
        row = {
            "file": c["file"],
            "callee_name": c["name"],
            "line": c.get("line_start"),
        }
        if parent:
            method_calls.append({**row, "caller_parent": parent, "caller_name": name})
        else:
            function_calls.append({**row, "caller_name": name})

    steps = [
        WriteStep("clear_existing", _CLEAR_REPO, {"repo_id": repository_id}),
        WriteStep("create_repository", _CREATE_REPO, {"repo_id": repository_id}),
        WriteStep("create_files", _CREATE_FILES, {
            "repo_id": repository_id, "files": [{"path": f} for f in files],
        }),
        WriteStep("create_classes", _CREATE_CLASSES, {
            "repo_id": repository_id,
            "classes": [{"file": c["file"], "name": c["name"]} for c in classes],
        }),
        WriteStep("create_functions", _CREATE_FUNCTIONS, {
            "repo_id": repository_id,
            "functions": [{"file": f["file"], "name": f["name"]} for f in functions],
        }),
        WriteStep("create_methods", _CREATE_METHODS, {
            "repo_id": repository_id,
            "methods": [{"file": m["file"], "name": m["name"], "parent": m["parent"]} for m in methods],
        }),
        WriteStep("create_imports", _CREATE_IMPORTS, {
            "repo_id": repository_id,
            "imports": [{"file": i["file"], "module": i["source"]} for i in imports],
        }),
    ]
    if function_calls:
        steps.append(WriteStep("create_calls_from_function", _CREATE_CALLS_FROM_FUNCTION, {
            "repo_id": repository_id, "calls": function_calls,
        }))
    if method_calls:
        steps.append(WriteStep("create_calls_from_method", _CREATE_CALLS_FROM_METHOD, {
            "repo_id": repository_id, "calls": method_calls,
        }))

    return steps


def build_knowledge_graph(client, repository_id: str, symbols: list[dict]) -> dict:
    """Executes the write plan against `client` (a Neo4jClient, or any
    object exposing `.run_write(cypher, **params)` — tests pass a mock).

    Returns a small summary dict for logging/verification.
    """
    plan = build_write_plan(repository_id, symbols)
    for step in plan:
        client.run_write(step.cypher, **step.params)

    return {
        "steps_executed": [s.label for s in plan],
        "file_count": len(plan[2].params["files"]),
        "class_count": len(plan[3].params["classes"]),
        "function_count": len(plan[4].params["functions"]),
        "method_count": len(plan[5].params["methods"]),
        "import_count": len(plan[6].params["imports"]),
        "call_relationship_candidates": sum(
            len(s.params.get("calls", [])) for s in plan if s.label.startswith("create_calls")
        ),
    }
