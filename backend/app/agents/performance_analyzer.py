"""
Performance Agent (Phase 7 / architecture doc §20).

Deliberately built LLM-free, unlike the Security/Testing/Documentation
Agents — architecture doc §20's signals (cyclomatic complexity, function
size) are fully deterministic, and a raw metric + fixed-template
recommendation is arguably MORE trustworthy for "is this function too
complex" (McCabe's cyclomatic complexity is an objective, decades-old
metric, not a judgment call) than LLM prose would be, not less useful.
This mirrors the Architecture Agent's precedent (pure computation, no
LLM) — a deliberate choice, not an oversight; see docs/PROGRESS.md
session 11 notes.

Complexity is computed by re-parsing each function/method's own source
slice (same source-slicing technique as app.embeddings.chunker.py) with
Tree-sitter, then counting McCabe decision-point nodes. The node type
sets below were determined by inspecting real Tree-sitter output for
each language (see session 11 notes), not assumed from grammar
documentation — e.g. JS's `&&`/`||` don't have their own node type, they
show up as a `binary_expression` whose `operator` field must be checked,
and "else if" chains in JS are nested `if_statement`s (no separate
"elif"-equivalent node the way Python has `elif_clause`), both of which
would be easy to get wrong without checking.

McCabe complexity = decision points + 1.
"""
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from app.analyzer.parser import EXTENSION_TO_LANGUAGE, get_parser_pool

_PYTHON_DECISION_TYPES = {
    "if_statement", "elif_clause", "for_statement", "while_statement",
    "except_clause", "boolean_operator", "conditional_expression",
}
_JS_DECISION_TYPES = {
    "if_statement", "for_statement", "for_in_statement", "while_statement",
    "do_statement", "catch_clause", "switch_case", "ternary_expression",
}
_JS_LOGICAL_OPERATORS = {"&&", "||"}

LARGE_FUNCTION_LINE_THRESHOLD = 50
HIGH_COMPLEXITY_THRESHOLD = 10


@dataclass
class ComplexityResult:
    complexity: int
    line_count: int


def _count_decision_points(node: Node, language: str) -> int:
    count = 0
    node_types = _PYTHON_DECISION_TYPES if language == "python" else _JS_DECISION_TYPES
    if node.type in node_types:
        count += 1
    if language != "python" and node.type == "binary_expression":
        op = node.child_by_field_name("operator")
        if op is not None and op.text.decode("utf-8", errors="ignore") in _JS_LOGICAL_OPERATORS:
            count += 1
    for child in node.children:
        count += _count_decision_points(child, language)
    return count


def compute_complexity(source_text: str, language: str) -> ComplexityResult | None:
    """source_text: a function/method's own source slice (e.g. from
    chunker.chunk_repository's line-range extraction). Returns None for
    languages this project doesn't parse."""
    if language == "tsx":
        language = "typescript"
    if language not in ("python", "javascript", "typescript"):
        return None
    pool = get_parser_pool()
    parser = pool.get_parser(language)
    tree = parser.parse(source_text.encode("utf-8"))
    decision_points = _count_decision_points(tree.root_node, language)
    return ComplexityResult(complexity=decision_points + 1, line_count=len(source_text.splitlines()))


def _read_source_slice(local_path: Path, file: str, start: int, end: int, cache: dict) -> str | None:
    if file not in cache:
        try:
            cache[file] = (local_path / file).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            cache[file] = None
    lines = cache[file]
    if lines is None:
        return None
    return "\n".join(lines[max(0, start - 1):min(len(lines), end)])


def analyze_performance(local_path: Path, symbols: list[dict]) -> list[dict]:
    """Returns finding dicts for functions/methods exceeding size or
    complexity thresholds. The only I/O is reading source files already
    on disk (same pattern as chunker.py); each unique file is read once
    regardless of how many symbols it contains."""
    findings = []
    file_cache: dict[str, list[str] | None] = {}

    for s in symbols:
        if s.get("type") not in ("function", "method"):
            continue
        file, name = s.get("file"), s.get("name")
        start, end = s.get("line_start"), s.get("line_end")
        if not file or not name or not start or not end or end < start:
            continue

        language = EXTENSION_TO_LANGUAGE.get(Path(file).suffix.lower())
        if language is None:
            continue

        line_count = end - start + 1
        if line_count > LARGE_FUNCTION_LINE_THRESHOLD:
            findings.append({
                "category": "Large Function",
                "severity": "ERROR" if line_count > LARGE_FUNCTION_LINE_THRESHOLD * 2 else "WARNING",
                "file": file, "line_start": start, "line_end": end,
                "title": f"{name} is {line_count} lines long",
                "description": (
                    f"{s['type'].capitalize()} '{name}' spans {line_count} lines "
                    f"(threshold: {LARGE_FUNCTION_LINE_THRESHOLD})."
                ),
                "recommendation": "Consider splitting into smaller, single-purpose functions.",
                "metric": {"line_count": line_count},
            })

        snippet = _read_source_slice(local_path, file, start, end, file_cache)
        if snippet is None:
            continue
        result = compute_complexity(snippet, language)
        if result is not None and result.complexity > HIGH_COMPLEXITY_THRESHOLD:
            findings.append({
                "category": "High Complexity",
                "severity": "ERROR" if result.complexity > HIGH_COMPLEXITY_THRESHOLD * 2 else "WARNING",
                "file": file, "line_start": start, "line_end": end,
                "title": f"{name} has cyclomatic complexity {result.complexity}",
                "description": (
                    f"{s['type'].capitalize()} '{name}' has a McCabe cyclomatic complexity of "
                    f"{result.complexity} (threshold: {HIGH_COMPLEXITY_THRESHOLD})."
                ),
                "recommendation": (
                    "Consider splitting into smaller sub-functions (e.g. separate validation, "
                    "transformation, and persistence steps) to reduce branching."
                ),
                "metric": {"cyclomatic_complexity": result.complexity},
            })

    return findings
