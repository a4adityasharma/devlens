"""
Testing Agent — Stage A validation (Phase 7 / architecture doc §17, step 3).

Architecture doc §17 is explicit: "never execute arbitrary generated
repository code directly on your host machine — use containers/
sandboxing." This project has NOT built that sandboxing (a real
containerization/isolation story — a separate container, gVisor/
Firecracker, or a hosted execution service — is genuine infrastructure
work, not a code change, and deliberately out of scope for this session;
see docs/PROGRESS.md's session notes). Rather than skip validation
entirely or fake it, this module is "Stage A": everything that can be
checked WITHOUT ever running the generated code.

Stage A checks, in order — reject on the first failure:
  1. Does it parse at all (Tree-sitter, no execution)?
  2. Does it actually reference the symbol it's supposed to test?
  3. Does it look like a test (imports/uses a recognized test framework,
     contains an assertion)?

This is real, meaningful validation — it catches a generated response
that isn't even valid code, or that tests the wrong thing, or that isn't
a test at all — but it is NOT a substitute for actually running the test
and seeing whether it passes. That gap is Stage B, explicitly unbuilt.
Anyone consuming this module's output must not present it to a user as
"this test was verified to work" — only as "this test passed static
checks and has not been executed."
"""
from dataclasses import dataclass, field

from app.analyzer.parser import get_parser_pool

_PY_TEST_MARKERS = ("import pytest", "import unittest", "assert ", "self.assert")
_JS_TEST_MARKERS = ("describe(", "it(", "test(", "expect(", "assert(")

_LANGUAGE_BY_EXTENSION = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
}


@dataclass
class ValidationResult:
    valid: bool
    reasons: list[str] = field(default_factory=list)  # populated only on failure

    def to_dict(self) -> dict:
        return {"valid": self.valid, "reasons": self.reasons}


def _looks_like_a_test(code: str, language: str) -> bool:
    markers = _PY_TEST_MARKERS if language == "python" else _JS_TEST_MARKERS
    return any(marker in code for marker in markers)


def validate_generated_test(code: str, target_symbol_name: str, language: str) -> ValidationResult:
    """code: the LLM's raw generated output. target_symbol_name: the
    function/method the test is supposed to exercise — must appear
    somewhere in the generated code, or it's not testing the right thing.
    language: 'python' | 'javascript' | 'typescript'.

    Never executes `code`. See module docstring for exactly what this
    does and does not guarantee.
    """
    reasons = []

    if not code or not code.strip():
        return ValidationResult(valid=False, reasons=["generated output is empty"])

    ts_language = _LANGUAGE_BY_EXTENSION.get(language)
    if ts_language is None:
        return ValidationResult(valid=False, reasons=[f"unsupported language: {language}"])

    pool = get_parser_pool()
    parser = pool.get_parser(ts_language)
    tree = parser.parse(code.encode("utf-8"))
    if tree.root_node.has_error:
        reasons.append("generated code does not parse (syntax error)")

    if target_symbol_name not in code:
        reasons.append(f"generated code never references the target symbol '{target_symbol_name}'")

    if not _looks_like_a_test(code, language):
        reasons.append("generated code doesn't look like a test (no recognized test framework/assertion found)")

    return ValidationResult(valid=len(reasons) == 0, reasons=reasons)
