"""
Real data throughout, same standard as test_architecture_analyzer.py: the
existing multi-language fixtures, plus self-analysis of this project's own
backend, which genuinely has functions covered by tests and functions
that (as this session discovered) are not.
"""
from pathlib import Path

from app.agents.test_coverage_analyzer import find_untested_symbols, is_test_file
from app.analyzer.repository_analyzer import analyze_repository

BACKEND_SRC = Path(__file__).parent.parent


def test_is_test_file_matches_common_conventions():
    assert is_test_file("tests/test_chunker.py")
    assert is_test_file("src/auth.test.js")
    assert is_test_file("src/auth.spec.ts")
    assert is_test_file("some_module_test.py")
    assert is_test_file("__tests__/component.js")
    assert is_test_file("app/services/repository_service.py") is False
    assert is_test_file("src/models/user.py") is False


def test_is_test_file_treats_anything_under_a_tests_directory_as_test_related():
    """Deliberately inclusive: even a non-test-named file living under a
    'tests/' directory (e.g. a fixture file) counts, since the point is
    'don't suggest generating a test for something that's already part of
    the test infrastructure' — a false positive here just means one fewer
    generation candidate, not a wrong test being generated."""
    assert is_test_file("tests/fixtures/sample.py")


def test_find_untested_symbols_basic_case():
    symbols = [
        {"type": "function", "name": "add", "file": "app.py", "line_start": 1, "line_end": 2, "parameters": ["a", "b"]},
        {"type": "function", "name": "subtract", "file": "app.py", "line_start": 4, "line_end": 5, "parameters": ["a", "b"]},
        {"type": "call", "name": "add", "file": "tests/test_app.py", "caller": "test_add"},
    ]
    untested = find_untested_symbols(symbols)
    assert [u.name for u in untested] == ["subtract"]


def test_find_untested_symbols_excludes_test_helper_functions():
    """A helper function defined INSIDE a test file isn't 'code under
    test' — it shouldn't show up as a candidate for generation even if
    nothing calls it from another test file."""
    symbols = [
        {"type": "function", "name": "make_fixture", "file": "tests/test_app.py",
         "line_start": 1, "line_end": 2, "parameters": []},
    ]
    assert find_untested_symbols(symbols) == []


def test_find_untested_symbols_call_from_non_test_file_does_not_count():
    symbols = [
        {"type": "function", "name": "helper", "file": "app.py", "line_start": 1, "line_end": 2, "parameters": []},
        {"type": "call", "name": "helper", "file": "app.py", "caller": "main"},  # not a test file
    ]
    untested = find_untested_symbols(symbols)
    assert [u.name for u in untested] == ["helper"]


def test_find_untested_symbols_preserves_metadata():
    symbols = [
        {"type": "method", "name": "authenticate", "file": "auth.py", "parent": "AuthService",
         "line_start": 10, "line_end": 15, "parameters": ["self", "username", "password"]},
    ]
    [u] = find_untested_symbols(symbols)
    assert u.type == "method"
    assert u.parent == "AuthService"
    assert u.parameters == ["self", "username", "password"]
    d = u.to_dict()
    assert d["name"] == "authenticate"


def test_self_analysis_finds_known_real_coverage_gaps():
    """This project's own core pipeline functions (clone_repository,
    scan_repository, ingest_repository, run_code_intelligence) were
    verified via live HTTP/curl checks across many sessions but never
    given direct pytest unit tests that call them by name — confirmed by
    grepping tests/ for their names before writing this assertion. This
    test locks in that real, previously-undocumented finding rather than
    asserting something invented."""
    result = analyze_repository(BACKEND_SRC)
    untested_names = {u.name for u in find_untested_symbols(result["symbols"])}
    assert "clone_repository" in untested_names
    assert "scan_repository" in untested_names
    assert "ingest_repository" in untested_names
    assert "run_code_intelligence" in untested_names


def test_self_analysis_finds_known_real_tested_functions():
    """Conversely, validate_github_url IS directly unit-tested
    (tests/test_repository_service.py) — confirms the detector doesn't
    just report everything as untested."""
    result = analyze_repository(BACKEND_SRC)
    untested_names = {u.name for u in find_untested_symbols(result["symbols"])}
    assert "validate_github_url" not in untested_names
