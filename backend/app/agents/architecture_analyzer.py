"""
Architecture Agent — analysis logic (Phase 7 / architecture doc §18).

Architecture doc §18 is explicit: "This agent shouldn't invent
architecture. It should use [symbols/graph data] to determine [layers],
then generate Mermaid." Everything in this module is pure, deterministic
computation over the same flat `symbols` list every other phase already
produces (RepositoryAnalysis.symbols) — no LLM call anywhere in this file.

Two deliberate MVP scope cuts, stated plainly rather than silently:
1. Layer detection is directory-name heuristics (a fixed keyword map,
   falling back to the immediate parent directory name) — not an LLM
   classifying ambiguous cases, per doc §18's instruction to derive
   structure from data first. A repo with unconventional naming will get
   a less meaningful layer breakdown; that's an honest reflection of the
   heuristic's limits, not a bug to paper over with a guess.
2. Only CALLS relationships (already resolved by name in
   app.analyzer.ast_extractor's "call" symbols) become diagram edges.
   IMPORTS aren't used for edges — resolving an import's module path
   string (e.g. "app.services.foo", "../utils") to a specific file
   reliably across Python/JS/TS import syntaxes is a meaningfully harder
   problem than reusing the CALLS resolution this project already has and
   tests; not attempted here. Revisit if edges prove too sparse in
   practice.

Same by-name ambiguity caveat as app/knowledge/graph_builder.py's CALLS
resolution applies here too: a call to a name that exists in multiple
files creates an edge to every one of them, not just the "correct" one.
"""
from dataclasses import dataclass, field
from pathlib import Path

# Deepest-matching path component wins (see infer_layer) — e.g.
# "app/services/foo.py" matches "services" even though "app" doesn't match
# anything, and a repo with "src/app/controllers/x.py" still finds
# "controllers" despite two non-matching components above it.
_LAYER_KEYWORDS = {
    "controllers": "Controllers", "controller": "Controllers",
    "routes": "Routes", "route": "Routes",
    "views": "Views", "view": "Views",
    "services": "Services", "service": "Services",
    "models": "Models", "model": "Models",
    "repositories": "Repositories", "repository": "Repositories",
    "db": "Database", "database": "Database",
    "middleware": "Middleware", "middlewares": "Middleware",
    "utils": "Utilities", "util": "Utilities", "helpers": "Utilities", "helper": "Utilities",
    "api": "API", "apis": "API",
    "schemas": "Schemas", "schema": "Schemas",
    "workers": "Workers", "worker": "Workers",
    "components": "Components", "component": "Components",
    "pages": "Pages", "page": "Pages",
    "hooks": "Hooks",
    "tests": "Tests", "test": "Tests",
}


def infer_layer(file_path: str) -> str:
    """'app/services/repository_service.py' -> 'Services'.
    'src/flask/cli.py' -> 'Flask' (no keyword matches; falls back to the
    immediate parent directory name, title-cased — an honest "this repo's
    layout doesn't use conventional layer names" result, not a forced fit).
    A file with no parent directory (repo-root file) -> 'Root'."""
    parts = Path(file_path).parts[:-1]  # exclude the filename itself
    for part in reversed(parts):
        layer = _LAYER_KEYWORDS.get(part.lower())
        if layer:
            return layer
    if parts:
        return parts[-1].replace("_", " ").replace("-", " ").title()
    return "Root"


@dataclass
class LayerGraph:
    layers: dict[str, dict] = field(default_factory=dict)  # layer -> {"file_count": int}
    edges: list[dict] = field(default_factory=list)  # [{"from", "to", "count"}], sorted by count desc


def build_layer_graph(symbols: list[dict]) -> LayerGraph:
    files = sorted({s["file"] for s in symbols if s.get("file")})
    file_to_layer = {f: infer_layer(f) for f in files}

    layer_files: dict[str, set] = {}
    for f, layer in file_to_layer.items():
        layer_files.setdefault(layer, set()).add(f)

    # name -> every file that defines something with that name (functions,
    # methods, classes) — deliberately name-only, same ambiguity tradeoff
    # as graph_builder.py's CALLS resolution, for the same reason: no
    # type-aware resolution in this project's MVP scope.
    definitions_by_name: dict[str, list[str]] = {}
    for s in symbols:
        if s.get("type") in ("function", "method", "class") and s.get("name"):
            definitions_by_name.setdefault(s["name"], []).append(s["file"])

    edge_counts: dict[tuple[str, str], int] = {}
    for s in symbols:
        if s.get("type") != "call":
            continue
        caller_file = s.get("file")
        callee_name = s.get("name")
        if not caller_file or caller_file not in file_to_layer or not callee_name:
            continue
        caller_layer = file_to_layer[caller_file]
        for def_file in definitions_by_name.get(callee_name, []):
            if def_file == caller_file:
                continue  # same-file call — not interesting at layer granularity
            callee_layer = file_to_layer.get(def_file)
            if callee_layer is None or callee_layer == caller_layer:
                continue  # same-layer call — skipped to keep the diagram to genuinely cross-cutting structure
            key = (caller_layer, callee_layer)
            edge_counts[key] = edge_counts.get(key, 0) + 1

    layers_summary = {
        layer: {"file_count": len(fs)} for layer, fs in sorted(layer_files.items())
    }
    edges = [
        {"from": frm, "to": to, "count": count}
        for (frm, to), count in sorted(edge_counts.items(), key=lambda kv: -kv[1])
    ]
    return LayerGraph(layers=layers_summary, edges=edges)


def generate_mermaid(graph: LayerGraph) -> str:
    """Pure string generation — every node/edge traces back to a real
    layer/count computed by build_layer_graph, nothing invented for
    presentability (architecture doc §18's core requirement)."""
    lines = ["graph TD"]
    node_id = {layer: f"L{i}" for i, layer in enumerate(sorted(graph.layers.keys()))}

    for layer, nid in node_id.items():
        count = graph.layers[layer]["file_count"]
        label = f"{layer} ({count} file{'s' if count != 1 else ''})"
        lines.append(f'    {nid}["{label}"]')

    for edge in graph.edges:
        frm_id, to_id = node_id.get(edge["from"]), node_id.get(edge["to"])
        if frm_id is None or to_id is None:
            continue
        lines.append(f'    {frm_id} -->|{edge["count"]}| {to_id}')

    return "\n".join(lines)


def analyze_architecture(symbols: list[dict]) -> dict:
    """Top-level entry point: symbols -> {"layers", "edges", "mermaid"}."""
    graph = build_layer_graph(symbols)
    return {
        "layers": graph.layers,
        "edges": graph.edges,
        "mermaid": generate_mermaid(graph),
    }
