"""
Only the LLM call itself is mocked (same as test_chat_service.py) —
source reading, symbol lookup, and Stage A validation all run for real.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.test_generator import TestGenerationSkipped
from app.services.testing_agent_service import SymbolNotFound, list_untested_symbols, run_test_generation


class _FakeRepository:
    def __init__(self, local_path):
        self.local_path = str(local_path)


class _FakeAnalysis:
    def __init__(self, symbols):
        self.id = "analysis-1"
        self.symbols = symbols


class _RecordingDb:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        obj.id = "artifact-1"


def _write_sample(tmp_path: Path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n")
    return [{
        "type": "function", "name": "add", "file": "app.py",
        "line_start": 1, "line_end": 2, "parameters": ["a", "b"], "parent": None,
    }]


def test_run_test_generation_persists_valid_generated_test(tmp_path):
    symbols = _write_sample(tmp_path)
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols)
    db = _RecordingDb()

    mocked_output = "import pytest\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    with patch("app.services.testing_agent_service.generate_test", return_value=mocked_output):
        result = run_test_generation(db, repo, analysis, file="app.py", symbol_name="add")

    assert result["persisted"] is True
    assert result["validation"]["valid"] is True
    assert result["artifact_id"] == "artifact-1"
    assert len(db.added) == 1
    assert db.added[0].content == mocked_output
    assert db.added[0].agent == "testing"


def test_run_test_generation_does_not_persist_invalid_generated_test(tmp_path):
    symbols = _write_sample(tmp_path)
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols)
    db = _RecordingDb()

    # syntactically broken — must be rejected by real Stage A validation
    mocked_output = "def test_add(:\n    assert add(1 2) == 3\n"
    with patch("app.services.testing_agent_service.generate_test", return_value=mocked_output):
        result = run_test_generation(db, repo, analysis, file="app.py", symbol_name="add")

    assert result["persisted"] is False
    assert result["validation"]["valid"] is False
    assert len(db.added) == 0


def test_run_test_generation_raises_for_unknown_symbol(tmp_path):
    symbols = _write_sample(tmp_path)
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols)

    with pytest.raises(SymbolNotFound):
        run_test_generation(_RecordingDb(), repo, analysis, file="app.py", symbol_name="does_not_exist")


def test_run_test_generation_propagates_generation_skipped(tmp_path):
    symbols = _write_sample(tmp_path)
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols)

    with patch("app.services.testing_agent_service.generate_test",
               side_effect=TestGenerationSkipped("no key")):
        with pytest.raises(TestGenerationSkipped):
            run_test_generation(_RecordingDb(), repo, analysis, file="app.py", symbol_name="add")


def test_list_untested_symbols_returns_dicts():
    symbols = [
        {"type": "function", "name": "add", "file": "app.py", "line_start": 1, "line_end": 2, "parameters": []},
    ]
    result = list_untested_symbols(_FakeAnalysis(symbols))
    assert result == [{
        "file": "app.py", "name": "add", "type": "function", "parent": None,
        "line_start": 1, "line_end": 2, "parameters": [],
    }]
