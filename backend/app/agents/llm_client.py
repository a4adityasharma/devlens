"""
Shared LLM-call adapter (Anthropic API), extracted after the third
near-identical copy of this exact function was about to be written (for
the Documentation Agent) — chat_service.py and test_generator.py each had
their own copy first; see docs/PROGRESS.md's session notes for why this
refactor happened now rather than earlier.

Verification status is unchanged by this refactor: `api.anthropic.com` is
reachable from this sandbox but no `ANTHROPIC_API_KEY` is configured, so
`call_llm` has never been exercised against a live model in any session.
Every caller mocks it (or mocks their own wrapper around it) in tests —
see test_chat_service.py, test_test_generator.py, and (new)
test_doc_generator.py for the pattern.
"""
from app.core.config import get_settings

settings = get_settings()


class LLMSkipped(Exception):
    """No ANTHROPIC_API_KEY configured. Callers typically catch this and
    re-raise their own more specific exception (ChatSkipped,
    TestGenerationSkipped, DocGenerationSkipped, ...) so each module keeps
    its own named exception for existing exception-handling call sites
    (the API routes) to catch, without every caller needing to know about
    this shared implementation detail."""


def call_llm(system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-5",
             max_tokens: int = 1024) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise LLMSkipped(
            "ANTHROPIC_API_KEY is not set — cannot call the LLM. Set it in .env to enable this feature."
        )
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model, max_tokens=max_tokens, system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
