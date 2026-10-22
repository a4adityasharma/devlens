"""
RAG Chat (Phase 6 / architecture doc §14, §29).

Takes a question, runs hybrid retrieval (app.retrieval.hybrid_retriever),
sends the retrieved context to an LLM, and returns an answer whose sources
are validated against what was actually retrieved — never trusted blindly
from the LLM's output. Citations are non-negotiable per the architecture
doc; an LLM claiming a source that isn't in `[SOURCE: ...]` markers from
the actual retrieved context gets that specific claim dropped, not passed
through.

Split the same way every prior phase was: `_extract_and_validate_citations`
is a pure function (no I/O, unit-tested directly with hand-built LLM output
strings) separate from `_call_llm` (the I/O adapter, mocked in tests — see
module docstring note on why this phase can't get the same real-engine
verification Qdrant got: there's no local-in-process Claude to run against,
unlike Qdrant's embedded mode).

`_call_llm` here is a thin wrapper around `app.agents.llm_client.call_llm`
(the shared adapter also used by test_generator.py and doc_generator.py)
that converts the shared `LLMSkipped` into this module's own `ChatSkipped`
— existing call sites (the `/chat` route) catch `ChatSkipped` specifically,
so this keeps that working without every caller needing to know the LLM
call is now centralized.

Verification status: `api.anthropic.com` IS reachable from this sandbox
(unlike api.openai.com), but no `ANTHROPIC_API_KEY` is configured here, so
`_call_llm` has never actually been exercised against a live model in any
session. Every test mocks it. Whoever has a real key should verify this
before trusting answer quality.
"""
import re

from app.agents.llm_client import LLMSkipped, call_llm
from app.core.config import get_settings
from app.retrieval.hybrid_retriever import retrieve

settings = get_settings()

_SOURCE_LINE_RE = re.compile(r"^-?\s*([^\s:]+):(\d+)-(\d+)\s*$")

_SYSTEM_PROMPT = """You are a code assistant answering questions about a specific repository.

You will be given retrieved code snippets, each preceded by a marker like:
[SOURCE: path/to/file.py:10-25]

Answer the question using ONLY the information in these snippets. Do not
invent behavior, file paths, or line numbers that aren't shown to you.

End your answer with a line that says exactly "Sources:" followed by one
[SOURCE: ...] marker per line, copied EXACTLY (same file path, same line
numbers) from the snippets you actually used. Do not cite a source you
did not use, and do not alter the file path or line numbers when copying
them."""


class ChatSkipped(Exception):
    """Raised when the LLM can't be called (no API key configured) — the
    caller can decide how to surface this (e.g. return retrieval results
    without a generated answer) rather than crashing."""


def _build_user_prompt(question: str, context: str) -> str:
    if not context:
        return (
            f"Question: {question}\n\n"
            "No relevant code was found in this repository for this question. "
            "Say so plainly; do not guess at an answer."
        )
    return f"Retrieved context:\n\n{context}\n\nQuestion: {question}"


def _call_llm(system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-5") -> str:
    try:
        return call_llm(system_prompt, user_prompt, model=model)
    except LLMSkipped as exc:
        raise ChatSkipped(str(exc)) from exc


def _valid_sources(hits: list[dict]) -> set[str]:
    return {f"{h['file']}:{h['start_line']}-{h['end_line']}" for h in hits}


def _extract_and_validate_citations(raw_answer: str, hits: list[dict]) -> tuple[str, list[dict]]:
    """Splits the LLM's raw output into (answer_text, validated_sources).

    Any line after "Sources:" that doesn't EXACTLY match a real
    `[SOURCE: file:start-end]` marker from the retrieved hits is silently
    dropped — not corrected, not "fuzzy matched". A citation the model
    invented or altered is worse than no citation; better to under-cite
    than to give false confidence in a wrong source.
    """
    valid = _valid_sources(hits)
    hits_by_source = {f"{h['file']}:{h['start_line']}-{h['end_line']}": h for h in hits}

    if "Sources:" in raw_answer:
        answer_part, _, sources_part = raw_answer.rpartition("Sources:")
    else:
        answer_part, sources_part = raw_answer, ""

    validated: list[dict] = []
    for line in sources_part.strip().splitlines():
        line = line.strip()
        line = line.removeprefix("[SOURCE:").removesuffix("]").strip()
        line = line.lstrip("-").strip()
        match = _SOURCE_LINE_RE.match(line)
        if not match:
            continue
        key = f"{match.group(1)}:{match.group(2)}-{match.group(3)}"
        if key in valid:
            hit = hits_by_source[key]
            validated.append({
                "file": hit["file"], "line_start": hit["start_line"], "line_end": hit["end_line"],
                "symbol": hit["symbol"],
            })
        # else: ungrounded citation, dropped — see docstring.

    return answer_part.strip(), validated


def answer_question(repository_id: str, question: str, neo4j_client=None) -> dict:
    """Top-level entry point: retrieve -> call LLM -> validate citations.

    Returns {"answer": str, "sources": [...], "graph_available": bool,
    "hit_count": int}. Raises ChatSkipped if no LLM is configured — the
    caller (the /chat endpoint) can decide how to surface that rather than
    this function guessing at a fallback response.
    """
    retrieval = retrieve(repository_id, question, neo4j_client=neo4j_client)

    if not retrieval["hits"]:
        return {
            "answer": "I couldn't find relevant code in this repository to answer that question.",
            "sources": [], "graph_available": retrieval["graph_available"], "hit_count": 0,
        }

    user_prompt = _build_user_prompt(question, retrieval["context"])
    raw_answer = _call_llm(_SYSTEM_PROMPT, user_prompt)
    answer_text, sources = _extract_and_validate_citations(raw_answer, retrieval["hits"])

    return {
        "answer": answer_text,
        "sources": sources,
        "graph_available": retrieval["graph_available"],
        "hit_count": len(retrieval["hits"]),
    }
