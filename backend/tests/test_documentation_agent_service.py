from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.documentation_agent_service import (
    _gather_symbols_by_file, _read_existing_readme, run_documentation_generation,
)


class _FakeRepository:
    def __init__(self, local_path, name="myrepo"):
        self.local_path = str(local_path)
        self.name = name


class _FakeAnalysis:
    def __init__(self, symbols, analysis_id="analysis-1"):
        self.id = analysis_id
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

    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return None  # no prior Architecture Agent artifact, by default


def test_gather_symbols_by_file_groups_correctly():
    symbols = [
        {"type": "function", "name": "add", "file": "a.py"},
        {"type": "method", "name": "login", "file": "auth.py"},
        {"type": "import", "name": "os", "file": "a.py"},  # not a definition, excluded
    ]
    files, by_file = _gather_symbols_by_file(symbols)
    assert files == ["a.py", "auth.py"]
    assert by_file == {"a.py": ["add"], "auth.py": ["login"]}


def test_read_existing_readme_finds_real_file(tmp_path: Path):
    (tmp_path / "README.md").write_text("# My Project\n")
    assert _read_existing_readme(tmp_path) == "# My Project\n"


def test_read_existing_readme_returns_none_when_absent(tmp_path: Path):
    assert _read_existing_readme(tmp_path) is None


def test_run_documentation_generation_persists_with_grounding_report(tmp_path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n")
    symbols = [{"type": "function", "name": "add", "file": "app.py"}]
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols)
    db = _RecordingDb()

    mocked_output = "# myrepo\n\nSee `app.py` for `add`. Also mentions `fake_file.py`."
    with patch("app.services.documentation_agent_service.generate_documentation", return_value=mocked_output):
        result = run_documentation_generation(db, repo, analysis, doc_type="readme")

    assert result["doc_type"] == "readme"
    assert result["artifact_id"] == "artifact-1"
    assert result["grounding"]["fully_grounded"] is False
    assert "fake_file.py" in result["grounding"]["ungrounded_files"]
    assert len(db.added) == 1
    assert db.added[0].agent == "documentation"
    assert db.added[0].artifact_type == "readme"
    assert db.added[0].extra["grounding"] == result["grounding"]


def test_run_documentation_generation_rejects_bad_doc_type(tmp_path):
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols=[])
    with pytest.raises(ValueError):
        run_documentation_generation(_RecordingDb(), repo, analysis, doc_type="changelog")


def test_run_documentation_generation_passes_existing_readme_to_generator(tmp_path):
    (tmp_path / "README.md").write_text("Old content.")
    repo = _FakeRepository(tmp_path)
    analysis = _FakeAnalysis(symbols=[])
    db = _RecordingDb()

    with patch("app.services.documentation_agent_service.generate_documentation",
               return_value="new doc") as mock_gen:
        run_documentation_generation(db, repo, analysis, doc_type="readme")

    _, kwargs = mock_gen.call_args
    assert kwargs.get("existing_readme") == "Old content."
