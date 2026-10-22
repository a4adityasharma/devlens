"""
Real Tree-sitter parsing throughout — no mocking, same as
test_ast_extractor.py's verification standard. This is the module doing
the actual safety-relevant work (rejecting bad generated output before
it's ever shown to anyone), so it gets the same real-verification bar as
Qdrant/Semgrep, not a lighter one just because there's no external tool
involved this time.
"""
from app.agents.test_validator import validate_generated_test


def test_valid_python_test_passes():
    code = (
        "import pytest\n"
        "from app import add\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )
    result = validate_generated_test(code, target_symbol_name="add", language="python")
    assert result.valid is True
    assert result.reasons == []


def test_valid_javascript_test_passes():
    code = (
        "const { add } = require('./app');\n\n"
        "test('add adds two numbers', () => {\n"
        "  expect(add(1, 2)).toBe(3);\n"
        "});\n"
    )
    result = validate_generated_test(code, target_symbol_name="add", language="javascript")
    assert result.valid is True


def test_syntactically_invalid_python_is_rejected():
    """Required negative-path demo #1: syntactically broken generated
    output must be rejected, not silently accepted."""
    code = "def test_add(:\n    assert add(1 2) == 3\n"
    result = validate_generated_test(code, target_symbol_name="add", language="python")
    assert result.valid is False
    assert any("syntax error" in r for r in result.reasons)


def test_test_referencing_nonexistent_function_is_rejected():
    """Required negative-path demo #2: a syntactically valid test that
    doesn't actually reference the function it's supposed to test must be
    rejected — this catches an LLM generating a plausible-looking test for
    the wrong thing (or a hallucinated function name)."""
    code = (
        "import pytest\n\n"
        "def test_something_else():\n"
        "    assert subtract(5, 2) == 3\n"
    )
    result = validate_generated_test(code, target_symbol_name="add", language="python")
    assert result.valid is False
    assert any("add" in r for r in result.reasons)


def test_empty_generation_is_rejected():
    result = validate_generated_test("", target_symbol_name="add", language="python")
    assert result.valid is False
    assert "empty" in result.reasons[0]


def test_code_with_no_assertions_is_rejected():
    """Syntactically valid, references the right name, but doesn't
    actually test anything — no assert/expect anywhere."""
    code = "def test_add():\n    add(1, 2)\n"
    result = validate_generated_test(code, target_symbol_name="add", language="python")
    assert result.valid is False
    assert any("doesn't look like a test" in r for r in result.reasons)


def test_unsupported_language_is_rejected():
    result = validate_generated_test("whatever", target_symbol_name="add", language="ruby")
    assert result.valid is False
    assert "unsupported language" in result.reasons[0]


def test_multiple_failures_all_reported():
    """A generated test can fail more than one check at once — all
    failure reasons should be surfaced, not just the first."""
    code = "def broken(:\n    pass\n"
    result = validate_generated_test(code, target_symbol_name="add", language="python")
    assert result.valid is False
    assert len(result.reasons) >= 2  # syntax error AND missing target reference AND no assertion


def test_valid_typescript_test_passes():
    code = (
        "import { add } from './app';\n\n"
        "describe('add', () => {\n"
        "  it('adds numbers', () => {\n"
        "    expect(add(1, 2)).toBe(3);\n"
        "  });\n"
        "});\n"
    )
    result = validate_generated_test(code, target_symbol_name="add", language="typescript")
    assert result.valid is True
