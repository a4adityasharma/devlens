from unittest.mock import patch

import pytest

from app.agents.test_generator import TestGenerationSkipped, generate_test


def test_generate_test_raises_when_no_api_key(monkeypatch):
    monkeypatch.setattr("app.agents.llm_client.settings.ANTHROPIC_API_KEY", "")
    with pytest.raises(TestGenerationSkipped):
        generate_test("add", "function", "app.py", "def add(a, b):\n    return a + b")


def test_generate_test_returns_llm_output_when_configured(monkeypatch):
    monkeypatch.setattr("app.agents.llm_client.settings.ANTHROPIC_API_KEY", "fake-key")
    mocked_output = "import pytest\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    with patch("app.agents.test_generator._call_llm", return_value=mocked_output) as mock_llm:
        result = generate_test("add", "function", "app.py", "def add(a, b):\n    return a + b")

    assert result == mocked_output
    assert mock_llm.called
    # confirm the prompt actually included the source and target name
    call_args = mock_llm.call_args
    user_prompt = call_args[0][1]
    assert "add" in user_prompt
    assert "return a + b" in user_prompt
