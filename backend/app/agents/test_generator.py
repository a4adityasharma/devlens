"""
Testing Agent — test generation (Phase 7 / architecture doc §17, step 2).

Unlike coverage analysis (test_coverage_analyzer.py) and validation
(test_validator.py), this step genuinely needs an LLM — there's no
deterministic way to write a meaningful test body from a function
signature alone. This inherits app.services.chat_service.py's exact
verification situation: written against the Anthropic API,
api.anthropic.com is reachable from this sandbox, but no
ANTHROPIC_API_KEY is configured, so generation quality is categorically
unverified here regardless of how carefully the prompt is written. Every
test mocks `_call_llm`, the same way test_chat_service.py does.

`_call_llm` here is a thin wrapper around `app.agents.llm_client.call_llm`
(the shared adapter, also used by chat_service.py and doc_generator.py).
"""
from app.agents.llm_client import LLMSkipped, call_llm

_SYSTEM_PROMPT = """You write a single, focused unit test for one function or method.

You will be given the function's source code, its file path, and the
testing framework already in use in this repository (or a sensible
default if none is detected).

Output ONLY the test code — no explanation, no markdown code fences, no
commentary before or after. The test must import or reference the
function under test correctly and contain at least one real assertion.
Do not invent behavior the function doesn't actually have; base the test
strictly on the provided source."""


class TestGenerationSkipped(Exception):
    """Raised when the LLM can't be called (no API key configured) — same
    soft-fail shape as chat_service.ChatSkipped."""
    __test__ = False  # tells pytest not to try collecting this as a test class


def _build_user_prompt(symbol_name: str, symbol_type: str, file_path: str,
                        source_text: str, framework_hint: str) -> str:
    return (
        f"Function/method to test: {symbol_name} ({symbol_type})\n"
        f"File: {file_path}\n"
        f"Test framework in use: {framework_hint}\n\n"
        f"Source:\n{source_text}\n\n"
        f"Write one test for {symbol_name}."
    )


def _call_llm(system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-5") -> str:
    try:
        return call_llm(system_prompt, user_prompt, model=model)
    except LLMSkipped as exc:
        raise TestGenerationSkipped(str(exc)) from exc


def generate_test(symbol_name: str, symbol_type: str, file_path: str,
                   source_text: str, framework_hint: str = "pytest") -> str:
    """Returns the LLM's raw generated code — NOT validated, NOT safe to
    execute. Callers must run this through
    app.agents.test_validator.validate_generated_test before persisting
    or showing it to anyone (see that module's docstring for exactly what
    validation does and does not guarantee)."""
    user_prompt = _build_user_prompt(symbol_name, symbol_type, file_path, source_text, framework_hint)
    return _call_llm(_SYSTEM_PROMPT, user_prompt)
