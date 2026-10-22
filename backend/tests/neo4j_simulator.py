"""
A minimal, purpose-built simulator of Neo4j's write behavior — but ONLY for
the exact fixed set of Cypher templates defined in
app/knowledge/graph_builder.py, not general Cypher.

Why this exists: no live Neo4j instance is reachable in this sandbox (no
Docker, no `apt` package — Neo4j is JVM-based and hosted outside the
allowed network domains). tests/test_graph_builder.py already verifies
"does graph_builder call run_write() the right number of times with the
right params" via a mock that just records calls. This module goes one
step further: it actually *executes* MERGE/MATCH/UNWIND semantics for
graph_builder's specific queries, producing a real in-memory node/edge
graph, so tests can assert on the resulting graph *shape* — e.g. "does the
Method node end up CONTAINed by the right Class", "does an ambiguous call
site correctly fan out to every same-named Callable" — not just "was some
write attempted".

This is still not a substitute for running against real Neo4j: it doesn't
validate Cypher syntax, index/constraint behavior, or Neo4j-version-specific
quirks. It validates the *logic* graph_builder.py encodes. Whoever next has
access to a live Neo4j should still do the docker-compose verification
described in docs/PROGRESS.md — that remains the highest-priority
unverified assumption in the codebase.

Also supports (via `run_query`, the read counterpart to `run_write`) the
fixed set of CALLS-neighbor lookup queries from
app/retrieval/hybrid_retriever.py (Phase 6), so that module's graph
expansion logic gets the same real-shape verification treatment as the
graph builder itself, not just a canned-response mock.
"""
from app.knowledge.graph_builder import (
    _CLEAR_REPO, _CREATE_REPO, _CREATE_FILES, _CREATE_CLASSES,
    _CREATE_FUNCTIONS, _CREATE_METHODS, _CREATE_IMPORTS,
    _CREATE_CALLS_FROM_FUNCTION, _CREATE_CALLS_FROM_METHOD,
)
from app.retrieval.hybrid_retriever import (
    _CALLS_OUT_FUNCTION, _CALLS_OUT_METHOD, _CALLS_IN_FUNCTION, _CALLS_IN_METHOD,
)


class SimulatedNode:
    def __init__(self, node_id: int, labels: frozenset, props: dict):
        self.id = node_id
        self.labels = labels
        self.props = dict(props)

    def __repr__(self):
        return f"({':'.join(sorted(self.labels))} {self.props})"


class SimulatedRelationship:
    def __init__(self, start: int, rel_type: str, end: int):
        self.start = start
        self.type = rel_type
        self.end = end
        self.props: dict = {}

    def __repr__(self):
        return f"(#{self.start})-[:{self.type} {self.props}]->(#{self.end})"


class Neo4jSimulator:
    """Drop-in replacement for a Neo4jClient in tests: exposes run_write()
    with the same signature graph_builder.py calls, but backed by an
    in-memory graph instead of a real database connection."""

    def __init__(self):
        self.nodes: dict[int, SimulatedNode] = {}
        self.rels: list[SimulatedRelationship] = []
        self._next_id = 0

    # -- generic MERGE/MATCH semantics, scoped to what these queries need --

    def _find(self, labels: set, props: dict) -> list[SimulatedNode]:
        """MATCH (n:Label1:Label2 {k: v, ...}) semantics: label set must be
        a subset of the node's labels, and every given prop must equal."""
        return [
            n for n in self.nodes.values()
            if labels.issubset(n.labels) and all(n.props.get(k) == v for k, v in props.items())
        ]

    def _find_one(self, labels: set, props: dict) -> SimulatedNode | None:
        matches = self._find(labels, props)
        return matches[0] if matches else None

    def _merge_node(self, labels: set, props: dict) -> SimulatedNode:
        existing = self._find_one(labels, props)
        if existing is not None:
            return existing
        node = SimulatedNode(self._next_id, frozenset(labels), props)
        self.nodes[self._next_id] = node
        self._next_id += 1
        return node

    def _merge_rel(self, start: SimulatedNode, rel_type: str, end: SimulatedNode) -> SimulatedRelationship:
        for r in self.rels:
            if r.start == start.id and r.type == rel_type and r.end == end.id:
                return r
        rel = SimulatedRelationship(start.id, rel_type, end.id)
        self.rels.append(rel)
        return rel

    # -- dispatcher: one handler per graph_builder.py template --

    def run_write(self, cypher: str, **params) -> None:
        handler = self._HANDLERS.get(cypher)
        if handler is None:
            raise NotImplementedError(
                "Neo4jSimulator only understands the fixed set of queries "
                "in app/knowledge/graph_builder.py — got an unrecognized "
                "query. If graph_builder.py added a new query template, "
                "add a matching handler here."
            )
        handler(self, **params)

    def run_query(self, cypher: str, **params) -> list[dict]:
        """Read-query counterpart to run_write — same identity-dispatch
        pattern, for app/retrieval/hybrid_retriever.py's CALLS-neighbor
        lookups (_CALLS_OUT_FUNCTION etc.)."""
        handler = self._READ_HANDLERS.get(cypher)
        if handler is None:
            raise NotImplementedError(
                "Neo4jSimulator only understands the fixed set of read "
                "queries in app/retrieval/hybrid_retriever.py — got an "
                "unrecognized query. Add a matching handler here if a new "
                "one was introduced."
            )
        return handler(self, **params)

    def verify_connectivity(self) -> bool:
        return True  # the simulator is always "connected" — it's in-memory

    def _h_clear(self, repo_id: str):
        to_remove = {
            nid for nid, n in self.nodes.items()
            if n.props.get("repo_id") == repo_id
            or ("Repository" in n.labels and n.props.get("id") == repo_id)
        }
        self.rels = [r for r in self.rels if r.start not in to_remove and r.end not in to_remove]
        for nid in to_remove:
            del self.nodes[nid]

    def _h_create_repo(self, repo_id: str):
        self._merge_node({"Repository"}, {"id": repo_id})

    def _h_create_files(self, repo_id: str, files: list[dict]):
        repo = self._find_one({"Repository"}, {"id": repo_id})
        if repo is None:
            return
        for f in files:
            file_node = self._merge_node({"File"}, {"repo_id": repo_id, "path": f["path"]})
            self._merge_rel(repo, "CONTAINS", file_node)

    def _h_create_classes(self, repo_id: str, classes: list[dict]):
        for c in classes:
            file_node = self._find_one({"File"}, {"repo_id": repo_id, "path": c["file"]})
            if file_node is None:
                continue
            cls = self._merge_node({"Class", "Callable"}, {"repo_id": repo_id, "file": c["file"], "name": c["name"]})
            self._merge_rel(file_node, "DEFINES", cls)

    def _h_create_functions(self, repo_id: str, functions: list[dict]):
        for fn in functions:
            file_node = self._find_one({"File"}, {"repo_id": repo_id, "path": fn["file"]})
            if file_node is None:
                continue
            f = self._merge_node({"Function", "Callable"}, {"repo_id": repo_id, "file": fn["file"], "name": fn["name"]})
            self._merge_rel(file_node, "DEFINES", f)

    def _h_create_methods(self, repo_id: str, methods: list[dict]):
        for m in methods:
            file_node = self._find_one({"File"}, {"repo_id": repo_id, "path": m["file"]})
            if file_node is None:
                continue
            cls = self._find_one({"Class"}, {"repo_id": repo_id, "file": m["file"], "name": m["parent"]})
            if cls is None:
                continue
            meth = self._merge_node({"Method", "Callable"}, {
                "repo_id": repo_id, "file": m["file"], "name": m["name"], "parent": m["parent"],
            })
            self._merge_rel(file_node, "DEFINES", meth)
            self._merge_rel(cls, "CONTAINS", meth)

    def _h_create_imports(self, repo_id: str, imports: list[dict]):
        for imp in imports:
            file_node = self._find_one({"File"}, {"repo_id": repo_id, "path": imp["file"]})
            if file_node is None:
                continue
            mod = self._merge_node({"Module"}, {"repo_id": repo_id, "name": imp["module"]})
            self._merge_rel(file_node, "IMPORTS", mod)

    def _h_create_calls_from_function(self, repo_id: str, calls: list[dict]):
        for call in calls:
            caller = self._find_one({"Function"}, {"repo_id": repo_id, "file": call["file"], "name": call["caller_name"]})
            if caller is None:
                continue
            for callee in self._find({"Callable"}, {"repo_id": repo_id, "name": call["callee_name"]}):
                rel = self._merge_rel(caller, "CALLS", callee)
                rel.props["match_type"] = "by_name"
                rel.props["line"] = call["line"]

    def _h_create_calls_from_method(self, repo_id: str, calls: list[dict]):
        for call in calls:
            caller = self._find_one({"Method"}, {
                "repo_id": repo_id, "file": call["file"],
                "parent": call["caller_parent"], "name": call["caller_name"],
            })
            if caller is None:
                continue
            for callee in self._find({"Callable"}, {"repo_id": repo_id, "name": call["callee_name"]}):
                rel = self._merge_rel(caller, "CALLS", callee)
                rel.props["match_type"] = "by_name"
                rel.props["line"] = call["line"]

    _HANDLERS = {
        _CLEAR_REPO: _h_clear,
        _CREATE_REPO: _h_create_repo,
        _CREATE_FILES: _h_create_files,
        _CREATE_CLASSES: _h_create_classes,
        _CREATE_FUNCTIONS: _h_create_functions,
        _CREATE_METHODS: _h_create_methods,
        _CREATE_IMPORTS: _h_create_imports,
        _CREATE_CALLS_FROM_FUNCTION: _h_create_calls_from_function,
        _CREATE_CALLS_FROM_METHOD: _h_create_calls_from_method,
    }

    # -- read-query handlers, for app/retrieval/hybrid_retriever.py --

    def _q_calls_out_function(self, repo_id: str, file: str, name: str) -> list[dict]:
        caller = self._find_one({"Function"}, {"repo_id": repo_id, "file": file, "name": name})
        if caller is None:
            return []
        return self._callees_of(caller)

    def _q_calls_out_method(self, repo_id: str, file: str, parent: str, name: str) -> list[dict]:
        caller = self._find_one({"Method"}, {"repo_id": repo_id, "file": file, "parent": parent, "name": name})
        if caller is None:
            return []
        return self._callees_of(caller)

    def _q_calls_in_function(self, repo_id: str, file: str, name: str) -> list[dict]:
        callee = self._find_one({"Function"}, {"repo_id": repo_id, "file": file, "name": name})
        if callee is None:
            return []
        return self._callers_of(callee)

    def _q_calls_in_method(self, repo_id: str, file: str, parent: str, name: str) -> list[dict]:
        callee = self._find_one({"Method"}, {"repo_id": repo_id, "file": file, "parent": parent, "name": name})
        if callee is None:
            return []
        return self._callers_of(callee)

    def _callees_of(self, node: SimulatedNode) -> list[dict]:
        seen = set()
        out = []
        for r in self.rels:
            if r.type == "CALLS" and r.start == node.id and r.end not in seen:
                seen.add(r.end)
                callee = self.nodes[r.end]
                out.append({"name": callee.props.get("name"), "file": callee.props.get("file"),
                            "labels": sorted(callee.labels)})
        return out

    def _callers_of(self, node: SimulatedNode) -> list[dict]:
        seen = set()
        out = []
        for r in self.rels:
            if r.type == "CALLS" and r.end == node.id and r.start not in seen:
                seen.add(r.start)
                caller = self.nodes[r.start]
                out.append({"name": caller.props.get("name"), "file": caller.props.get("file"),
                            "labels": sorted(caller.labels)})
        return out

    _READ_HANDLERS = {
        _CALLS_OUT_FUNCTION: _q_calls_out_function,
        _CALLS_OUT_METHOD: _q_calls_out_method,
        _CALLS_IN_FUNCTION: _q_calls_in_function,
        _CALLS_IN_METHOD: _q_calls_in_method,
    }

    # -- query helpers for tests (mimic simple Cypher MATCH...RETURN) --

    def match(self, *labels: str, **props) -> list[SimulatedNode]:
        return self._find(set(labels), props)

    def relationships_of_type(self, rel_type: str) -> list[SimulatedRelationship]:
        return [r for r in self.rels if r.type == rel_type]
