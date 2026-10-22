from unittest.mock import patch

import pytest

from app.services.chat_service import (
    ChatSkipped, _extract_and_validate_citations, answer_question,
)

SAMPLE_HITS = [
    {"file": "auth.py", "symbol": "authenticate", "type": "method", "parent": "AuthService",
     "start_line": 5, "end_line": 8, "text": "def authenticate(self, user): ..."},
    {"file": "auth.py", "symbol": "validate", "type": "method", "parent": "AuthService",
     "start_line": 10, "end_line": 12, "text": "def validate(self, token): ..."},
]


# ---------------------------------------------------------------------------
# _extract_and_validate_citations — pure logic, the core grounding guarantee
# ---------------------------------------------------------------------------

def test_valid_citation_is_kept():
    raw = (
        "Authentication happens in AuthService.authenticate.\n\n"
        "Sources:\n"
        "[SOURCE: auth.py:5-8]"
    )
    answer, sources = _extract_and_validate_citations(raw, SAMPLE_HITS)
    assert "Authentication happens" in answer
    assert sources == [{"file": "auth.py", "line_start": 5, "line_end": 8, "symbol": "authenticate"}]


def test_hallucinated_citation_is_dropped_not_trusted():
    """The core grounding guarantee: a source the LLM invents — right file,
    wrong/made-up line numbers not present in what was retrieved — must
    NOT be passed through as if it were real."""
    raw = (
        "Authentication happens in AuthService.authenticate.\n\n"
        "Sources:\n"
        "[SOURCE: auth.py:999-1005]"
    )
    answer, sources = _extract_and_validate_citations(raw, SAMPLE_HITS)
    assert sources == []


def test_citation_to_file_never_retrieved_is_dropped():
    raw = "Some answer.\n\nSources:\n[SOURCE: nonexistent_file.py:1-5]"
    _, sources = _extract_and_validate_citations(raw, SAMPLE_HITS)
    assert sources == []


def test_multiple_citations_mixed_valid_and_invalid():
    raw = (
        "Explanation here.\n\n"
        "Sources:\n"
        "[SOURCE: auth.py:5-8]\n"
        "[SOURCE: auth.py:10-12]\n"
        "[SOURCE: made_up.py:1-2]"
    )
    _, sources = _extract_and_validate_citations(raw, SAMPLE_HITS)
    assert len(sources) == 2
    assert {s["symbol"] for s in sources} == {"authenticate", "validate"}


def test_no_sources_section_returns_empty_sources():
    raw = "Just an answer with no sources section at all."
    answer, sources = _extract_and_validate_citations(raw, SAMPLE_HITS)
    assert answer == raw
    assert sources == []


def test_answer_text_excludes_sources_section():
    raw = "The real answer.\n\nSources:\n[SOURCE: auth.py:5-8]"
    answer, _ = _extract_and_validate_citations(raw, SAMPLE_HITS)
    assert "Sources:" not in answer
    assert "SOURCE" not in answer


def test_empty_hits_means_every_citation_is_dropped():
    raw = "Answer.\n\nSources:\n[SOURCE: auth.py:5-8]"
    _, sources = _extract_and_validate_citations(raw, hits=[])
    assert sources == []


# ---------------------------------------------------------------------------
# answer_question — orchestration, LLM mocked (see module docstring: no
# local-in-process LLM exists the way Qdrant has one, so this is the one
# place in the project where mocking the external call is unavoidable)
# ---------------------------------------------------------------------------

def test_answer_question_returns_early_when_no_hits():
    with patch("app.services.chat_service.retrieve",
               return_value={"hits": [], "context": "", "graph_available": False}):
        result = answer_question("repo-1", "what does this do?")
    assert result["sources"] == []
    assert result["hit_count"] == 0
    assert "couldn't find" in result["answer"].lower()


def test_answer_question_raises_chat_skipped_without_api_key(monkeypatch):
    monkeypatch.setattr("app.services.chat_service.settings.ANTHROPIC_API_KEY", "")
    with patch("app.services.chat_service.retrieve",
               return_value={"hits": SAMPLE_HITS, "context": "some context", "graph_available": True}):
        with pytest.raises(ChatSkipped):
            answer_question("repo-1", "explain authentication")


def test_answer_question_full_happy_path_with_mocked_llm(monkeypatch):
    monkeypatch.setattr("app.services.chat_service.settings.ANTHROPIC_API_KEY", "fake-key-for-test")
    mocked_llm_output = (
        "Authentication is handled by AuthService.authenticate, which "
        "delegates token checking to AuthService.validate.\n\n"
        "Sources:\n"
        "[SOURCE: auth.py:5-8]\n"
        "[SOURCE: auth.py:10-12]"
    )
    with patch("app.services.chat_service.retrieve",
               return_value={"hits": SAMPLE_HITS, "context": "fake context", "graph_available": True}), \
         patch("app.services.chat_service._call_llm", return_value=mocked_llm_output) as mock_llm:
        result = answer_question("repo-1", "explain authentication")

    assert mock_llm.called
    assert "AuthService.authenticate" in result["answer"]
    assert len(result["sources"]) == 2
    assert result["graph_available"] is True
    assert result["hit_count"] == 2


def test_answer_question_drops_hallucinated_source_in_full_flow(monkeypatch):
    """End-to-end version of the core grounding guarantee: even with a
    'successful' LLM call, a fabricated source doesn't survive to the
    final result."""
    monkeypatch.setattr("app.services.chat_service.settings.ANTHROPIC_API_KEY", "fake-key-for-test")
    mocked_llm_output = (
        "Here's the answer.\n\nSources:\n[SOURCE: auth.py:5-8]\n[SOURCE: totally_invented.py:1-99]"
    )
    with patch("app.services.chat_service.retrieve",
               return_value={"hits": SAMPLE_HITS, "context": "fake context", "graph_available": False}), \
         patch("app.services.chat_service._call_llm", return_value=mocked_llm_output):
        result = answer_question("repo-1", "explain authentication")

    assert len(result["sources"]) == 1
    assert result["sources"][0]["file"] == "auth.py"
    assert not any(s["file"] == "totally_invented.py" for s in result["sources"])
