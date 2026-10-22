"""
Real verification throughout — hand-computed cyclomatic complexity values
(traced by hand against the actual McCabe formula, not just "runs without
crashing"), plus self-analysis of this project's own backend, same
standard as the Architecture and Testing Agents.
"""
from pathlib import Path

from app.agents.performance_analyzer import (
    HIGH_COMPLEXITY_THRESHOLD, LARGE_FUNCTION_LINE_THRESHOLD,
    analyze_performance, compute_complexity,
)
from app.analyzer.repository_analyzer import analyze_repository

BACKEND_SRC = Path(__file__).parent.parent / "app"


def test_simple_function_has_complexity_one():
    code = "def add(a, b):\n    return a + b\n"
    result = compute_complexity(code, "python")
    assert result.complexity == 1  # no decision points -> base complexity


def test_python_complexity_matches_hand_count():
    """1 (base) + if + boolean_operator(and) + for + if + boolean_operator(or) = 6."""
    code = (
        "def f(a, b, c):\n"
        "    if a and b:\n"
        "        for i in range(10):\n"
        "            if i > 5 or c:\n"
        "                pass\n"
    )
    result = compute_complexity(code, "python")
    assert result.complexity == 6


def test_python_elif_and_except_each_count():
    """1 (base) + if + elif + except = 4."""
    code = (
        "def f(a):\n"
        "    if a == 1:\n"
        "        pass\n"
        "    elif a == 2:\n"
        "        pass\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError:\n"
        "        pass\n"
    )
    result = compute_complexity(code, "python")
    assert result.complexity == 4


def test_python_ternary_counts():
    code = "def f(a):\n    return 1 if a else 2\n"
    result = compute_complexity(code, "python")
    assert result.complexity == 2  # base + conditional_expression


def test_javascript_complexity_matches_hand_count():
    """1 (base) + if + && + for + if + || = 6."""
    code = (
        "function f(a, b, c) {\n"
        "  if (a && b) {\n"
        "    for (let i = 0; i < 10; i++) {\n"
        "      if (i > 5 || c) {}\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    result = compute_complexity(code, "javascript")
    assert result.complexity == 6


def test_javascript_else_if_chain_counts_each_as_one():
    """JS 'else if' is a nested if_statement inside an else_clause — no
    separate node type the way Python has elif_clause. 1 (base) + the
    first if + 2 nested "else if" if_statements = 4."""
    code = (
        "function f(a) {\n"
        "  if (a === 1) {\n"
        "  } else if (a === 2) {\n"
        "  } else if (a === 3) {\n"
        "  }\n"
        "}\n"
    )
    result = compute_complexity(code, "javascript")
    assert result.complexity == 4


def test_javascript_switch_case_counts():
    code = (
        "function f(a) {\n"
        "  switch (a) {\n"
        "    case 1: break;\n"
        "    case 2: break;\n"
        "  }\n"
        "}\n"
    )
    result = compute_complexity(code, "javascript")
    assert result.complexity == 3  # base + 2 switch_case


def test_javascript_binary_expression_arithmetic_does_not_count():
    """A plain arithmetic binary_expression (e.g. a + b) must NOT be
    counted as a decision point — only && / || should. This guards
    against a naive 'count all binary_expression nodes' bug."""
    code = "function f(a, b) {\n  return a + b - a * b;\n}\n"
    result = compute_complexity(code, "javascript")
    assert result.complexity == 1


def test_compute_complexity_returns_none_for_unsupported_language():
    assert compute_complexity("whatever", "ruby") is None


def test_analyze_performance_flags_large_function(tmp_path):
    long_body = "\n".join(f"    x{i} = {i}" for i in range(60))
    (tmp_path / "big.py").write_text(f"def big_function():\n{long_body}\n    return x0\n")
    symbols = [{"type": "function", "name": "big_function", "file": "big.py",
                "line_start": 1, "line_end": 62, "parameters": []}]
    findings = analyze_performance(tmp_path, symbols)
    large_function_findings = [f for f in findings if f["category"] == "Large Function"]
    assert len(large_function_findings) == 1
    assert large_function_findings[0]["metric"]["line_count"] == 62


def test_analyze_performance_flags_high_complexity(tmp_path):
    branches = "\n".join(f"    if x == {i}:\n        pass" for i in range(15))
    (tmp_path / "complex.py").write_text(f"def complex_func(x):\n{branches}\n")
    symbols = [{"type": "function", "name": "complex_func", "file": "complex.py",
                "line_start": 1, "line_end": 31, "parameters": ["x"]}]
    findings = analyze_performance(tmp_path, symbols)
    complexity_findings = [f for f in findings if f["category"] == "High Complexity"]
    assert len(complexity_findings) == 1
    assert complexity_findings[0]["metric"]["cyclomatic_complexity"] == 16  # base + 15 ifs


def test_analyze_performance_no_findings_for_simple_code(tmp_path):
    (tmp_path / "simple.py").write_text("def add(a, b):\n    return a + b\n")
    symbols = [{"type": "function", "name": "add", "file": "simple.py",
                "line_start": 1, "line_end": 2, "parameters": ["a", "b"]}]
    assert analyze_performance(tmp_path, symbols) == []


def test_analyze_performance_skips_missing_files_silently(tmp_path):
    symbols = [{"type": "function", "name": "ghost", "file": "does_not_exist.py",
                "line_start": 1, "line_end": 2, "parameters": []}]
    assert analyze_performance(tmp_path, symbols) == []


def test_analyze_performance_ignores_non_function_symbols(tmp_path):
    (tmp_path / "a.py").write_text("class Foo:\n    pass\n")
    symbols = [{"type": "class", "name": "Foo", "file": "a.py", "line_start": 1, "line_end": 2}]
    assert analyze_performance(tmp_path, symbols) == []


def test_self_analysis_finds_real_verifiable_complexity_issue():
    """This project's own app/analyzer/ast_extractor.py's _walk_js is a
    known, real, independently-verifiable high-complexity function (many
    elif-equivalent branches for different Tree-sitter node types) — this
    locks in that self-analysis finds it, the same 'demonstrate on our own
    codebase' bar the Architecture and Testing Agents were held to."""
    result = analyze_repository(BACKEND_SRC)
    findings = analyze_performance(BACKEND_SRC, result["symbols"])
    walk_js_findings = [f for f in findings if "_walk_js" in f["title"]]
    assert len(walk_js_findings) == 2  # both Large Function and High Complexity
    complexity_finding = next(f for f in walk_js_findings if f["category"] == "High Complexity")
    assert complexity_finding["metric"]["cyclomatic_complexity"] > HIGH_COMPLEXITY_THRESHOLD


def test_thresholds_are_reasonable_constants():
    """Sanity check that the thresholds are the values every other test
    in this file assumes — catches an accidental threshold change from
    silently breaking every hand-computed test's assumptions."""
    assert LARGE_FUNCTION_LINE_THRESHOLD == 50
    assert HIGH_COMPLEXITY_THRESHOLD == 10
