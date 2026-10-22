"""
Same split as every other LLM-touching module in this project:
`check_grounding` is pure logic and gets real, thorough test coverage;
`generate_documentation`'s actual LLM call is mocked (see doc_generator.py's
module docstring for why — no live API key available in this sandbox).
"""
from unittest.mock import patch

import pytest

from app.agents.doc_generator import DocGenerationSkipped, check_grounding, generate_documentation


# ---------------------------------------------------------------------------
# check_grounding — pure logic, the core "don't trust generated docs" guarantee
# ---------------------------------------------------------------------------

def test_grounded_file_and_symbol_mentions_pass():
    doc = "See `app/services/auth_service.py` for `AuthService.login`."
    result = check_grounding(
        doc,
        valid_files={"app/services/auth_service.py"},
        valid_symbol_names={"login", "AuthService"},
    )
    assert result["fully_grounded"] is True
    assert result["ungrounded_files"] == []
    assert result["ungrounded_symbols"] == []
    assert result["total_mentions"] == 2


def test_fabricated_file_reference_is_caught():
    """Required negative-path demo: a plausible-looking but nonexistent
    file path must be flagged, not trusted."""
    doc = "Configuration is handled in `app/config/settings_loader.py`."
    result = check_grounding(doc, valid_files={"app/core/config.py"}, valid_symbol_names=set())
    assert result["fully_grounded"] is False
    assert "app/config/settings_loader.py" in result["ungrounded_files"]


def test_fabricated_symbol_reference_is_caught():
    """Second required negative-path demo: a plausible-looking but
    nonexistent function/class name must be flagged."""
    doc = "Authentication is handled by `AuthenticationManager.verify`."
    result = check_grounding(doc, valid_files=set(), valid_symbol_names={"AuthService", "login"})
    assert result["fully_grounded"] is False
    assert "AuthenticationManager.verify" in result["ungrounded_symbols"]


def test_dotted_method_reference_matches_on_bare_name():
    """`AuthService.login` should be accepted if 'login' is a known symbol
    name, even though symbols are tracked by bare name, not fully-qualified
    dotted path (see app.analyzer.ast_extractor.Symbol)."""
    doc = "Call `AuthService.login` to authenticate."
    result = check_grounding(doc, valid_files=set(), valid_symbol_names={"login"})
    assert result["fully_grounded"] is True


def test_mixed_grounded_and_ungrounded_mentions():
    doc = "See `real_file.py` and `fake_file.py`, using `real_func` and `fake_func`."
    result = check_grounding(
        doc, valid_files={"real_file.py"}, valid_symbol_names={"real_func"},
    )
    assert result["ungrounded_files"] == ["fake_file.py"]
    assert result["ungrounded_symbols"] == ["fake_func"]
    assert result["total_mentions"] == 4


def test_no_backtick_mentions_is_trivially_grounded():
    doc = "This project has no code references in this paragraph at all."
    result = check_grounding(doc, valid_files=set(), valid_symbol_names=set())
    assert result["fully_grounded"] is True
    assert result["total_mentions"] == 0


def test_prose_in_backticks_that_happens_to_match_nothing_is_flagged_as_symbol():
    """A non-path-like backticked span that isn't a known symbol name is
    treated as an ungrounded symbol mention, even if it's arguably just
    stray formatting rather than a hallucinated reference — the checker
    can't distinguish intent, so it flags conservatively rather than
    silently ignoring unexpected backtick usage."""
    doc = "This uses `some made up thing` internally."
    result = check_grounding(doc, valid_files=set(), valid_symbol_names=set())
    assert result["fully_grounded"] is False
    assert "some made up thing" in result["ungrounded_symbols"]


# ---------------------------------------------------------------------------
# generate_documentation — orchestration, LLM mocked
# ---------------------------------------------------------------------------

def test_generate_documentation_rejects_unknown_doc_type():
    with pytest.raises(ValueError):
        generate_documentation("changelog", "myrepo", [], {})


def test_generate_documentation_raises_when_no_api_key(monkeypatch):
    monkeypatch.setattr("app.agents.llm_client.settings.ANTHROPIC_API_KEY", "")
    with pytest.raises(DocGenerationSkipped):
        generate_documentation("readme", "myrepo", ["app.py"], {"app.py": ["main"]})


def test_generate_documentation_returns_llm_output(monkeypatch):
    monkeypatch.setattr("app.agents.llm_client.settings.ANTHROPIC_API_KEY", "fake-key")
    mocked_output = "# myrepo\n\nSee `app.py` for `main`."
    with patch("app.agents.doc_generator._call_llm", return_value=mocked_output) as mock_llm:
        result = generate_documentation("readme", "myrepo", ["app.py"], {"app.py": ["main"]})

    assert result == mocked_output
    assert mock_llm.called
    user_prompt = mock_llm.call_args[0][1]
    assert "app.py" in user_prompt
    assert "main" in user_prompt


def test_generate_documentation_includes_existing_readme_and_architecture_summary(monkeypatch):
    monkeypatch.setattr("app.agents.llm_client.settings.ANTHROPIC_API_KEY", "fake-key")
    with patch("app.agents.doc_generator._call_llm", return_value="output") as mock_llm:
        generate_documentation(
            "architecture_overview", "myrepo", ["app.py"], {"app.py": ["main"]},
            existing_readme="Old readme text here.",
            architecture_summary="Layers: Services (3 files) -> Models (2 files).",
        )
    user_prompt = mock_llm.call_args[0][1]
    assert "Old readme text here." in user_prompt
    assert "Services (3 files)" in user_prompt
