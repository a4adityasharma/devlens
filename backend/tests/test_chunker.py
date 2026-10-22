from pathlib import Path

from app.embeddings.chunker import chunk_repository


def test_chunk_repository_slices_real_source_text(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "import os\n"
        "\n"
        "def generate_token(username):\n"
        "    return username\n"
        "\n"
        "class UserService:\n"
        "    def authenticate(self, username):\n"
        "        return generate_token(username)\n"
    )

    symbols = [
        {"type": "import", "name": "os", "file": "app.py", "line_start": 1, "line_end": 1,
         "parameters": [], "parent": None},
        {"type": "function", "name": "generate_token", "file": "app.py",
         "line_start": 3, "line_end": 4, "parameters": ["username"], "parent": None},
        {"type": "class", "name": "UserService", "file": "app.py",
         "line_start": 6, "line_end": 8, "parameters": [], "parent": None},
        {"type": "method", "name": "authenticate", "file": "app.py",
         "line_start": 7, "line_end": 8, "parameters": ["self", "username"], "parent": "UserService"},
    ]

    chunks = chunk_repository(tmp_path, "repo-1", symbols)

    # import symbols are not chunked — only function/class/method
    assert {c.symbol for c in chunks} == {"generate_token", "UserService", "authenticate"}

    fn_chunk = next(c for c in chunks if c.symbol == "generate_token")
    assert fn_chunk.text == "def generate_token(username):\n    return username"
    assert fn_chunk.type == "function"
    assert fn_chunk.language == "python"
    assert fn_chunk.start_line == 3 and fn_chunk.end_line == 4

    method_chunk = next(c for c in chunks if c.symbol == "authenticate")
    assert method_chunk.parent == "UserService"
    assert "return generate_token(username)" in method_chunk.text


def test_chunk_repository_skips_missing_files(tmp_path: Path):
    symbols = [
        {"type": "function", "name": "ghost", "file": "does_not_exist.py",
         "line_start": 1, "line_end": 2, "parameters": [], "parent": None},
    ]
    assert chunk_repository(tmp_path, "repo-1", symbols) == []


def test_chunk_repository_skips_invalid_line_ranges(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n")
    symbols = [
        {"type": "function", "name": "bad", "file": "a.py",
         "line_start": 5, "line_end": 2, "parameters": [], "parent": None},  # end < start
        {"type": "function", "name": "no_lines", "file": "a.py",
         "line_start": None, "line_end": None, "parameters": [], "parent": None},
    ]
    assert chunk_repository(tmp_path, "repo-1", symbols) == []


def test_chunk_ids_are_stable_across_reruns(tmp_path: Path):
    (tmp_path / "a.py").write_text("def foo():\n    pass\n")
    symbols = [{"type": "function", "name": "foo", "file": "a.py",
                "line_start": 1, "line_end": 2, "parameters": [], "parent": None}]

    first = chunk_repository(tmp_path, "repo-1", symbols)
    second = chunk_repository(tmp_path, "repo-1", symbols)
    assert first[0].id == second[0].id


def test_chunk_payload_is_self_contained(tmp_path: Path):
    (tmp_path / "a.py").write_text("def foo():\n    pass\n")
    symbols = [{"type": "function", "name": "foo", "file": "a.py",
                "line_start": 1, "line_end": 2, "parameters": [], "parent": None}]
    chunk = chunk_repository(tmp_path, "repo-1", symbols)[0]
    payload = chunk.to_payload()
    assert payload["text"] == chunk.text
    assert payload["repository_id"] == "repo-1"
    assert payload["symbol"] == "foo"
