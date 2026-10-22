"""
Unlike Neo4j (no live instance reachable, ever) and unlike the LLM/OpenAI
paths (no API key), Semgrep is a real, locally-installable, offline-capable
tool — these tests run the actual `semgrep` binary against real fixture
files with real (intentionally planted) vulnerabilities, not a mock. This
is the strongest verification level in the project, on par with the Qdrant
local-mode tests.

`semgrep` installs and runs directly from requirements.txt with no env var
or workaround needed — an earlier session's requirements.txt pinned
`pydantic==2.9.2`/`uvicorn==0.30.6`, which conflicted with semgrep's own
`mcp` dependency and made a clean single-environment install impossible;
that was fixed by relaxing those two pins (see docs/PROGRESS.md), not by
routing semgrep into a separate venv. If these tests fail with "semgrep
binary not found", check `pip install -r requirements.txt` actually
succeeded before assuming a code bug here.
"""
from pathlib import Path

import pytest

from app.agents.security_scanner import ScannerError, ScannerUnavailable, parse_semgrep_result, run_semgrep

FIXTURES = Path(__file__).parent / "security_fixtures" / "vulnerable_repo"


def test_scanner_finds_all_planted_vulnerabilities():
    results = run_semgrep(FIXTURES)
    check_ids = {r["check_id"].split(".")[-1] for r in results}
    assert check_ids == {
        "python-shell-injection", "python-sql-string-concat", "python-eval-exec",
        "python-hardcoded-secret", "js-child-process-exec", "js-eval", "js-hardcoded-secret",
    }


def test_scanner_does_not_flag_safe_code():
    results = run_semgrep(FIXTURES)
    lines_flagged_in_app_py = {r["start"]["line"] for r in results if r["path"].endswith("app.py")}
    # safe_function is defined starting at a known safe line — confirm no
    # finding lands anywhere near it (it's the last function in the file).
    assert 21 not in lines_flagged_in_app_py and 22 not in lines_flagged_in_app_py


def test_parse_semgrep_result_shapes_finding_correctly():
    results = run_semgrep(FIXTURES)
    shell_injection = next(r for r in results if "shell-injection" in r["check_id"])
    parsed = parse_semgrep_result(shell_injection, FIXTURES)

    assert parsed["category"] == "Command Injection"
    assert parsed["severity"] == "ERROR"
    assert parsed["file_path"] == "app.py"  # relative to repo root, not absolute
    assert parsed["line_start"] == 6
    assert "shlex.quote" in parsed["recommendation"]
    assert parsed["title"] == "Python Shell Injection"


def test_parse_semgrep_result_handles_js_findings():
    results = run_semgrep(FIXTURES)
    js_eval = next(r for r in results if r["check_id"].endswith("js-eval"))
    parsed = parse_semgrep_result(js_eval, FIXTURES)
    assert parsed["file_path"] == "server.js"
    assert parsed["category"] == "Code Injection"


def test_scanner_unavailable_when_binary_missing(monkeypatch):
    monkeypatch.setenv("SEMGREP_BIN", "/nonexistent/path/to/semgrep")
    with pytest.raises(ScannerUnavailable):
        run_semgrep(FIXTURES)


def test_scanner_error_on_timeout(monkeypatch):
    monkeypatch.setenv("SEMGREP_BIN", "sleep")
    with pytest.raises(ScannerError):
        run_semgrep(FIXTURES, timeout=0)


def test_scan_on_clean_file_returns_no_findings(tmp_path):
    (tmp_path / "clean.py").write_text("def add(a, b):\n    return a + b\n")
    results = run_semgrep(tmp_path)
    assert results == []


def test_parse_semgrep_result_correct_with_relative_repo_root(tmp_path, monkeypatch):
    """Regression test for a real bug: repository.local_path is a relative
    path in production (see repository_service.py's REPO_STORAGE_PATH
    default), and semgrep echoes back paths relative to CWD when given a
    relative target — NOT relative to repo_root, which the first version
    of parse_semgrep_result incorrectly assumed. This test reproduces that
    exact shape (relative target, scanned from a different CWD) rather
    than only the absolute-path case every other fixture-based test here
    happens to use, which is what let the original bug ship undetected by
    unit tests and only surface via a live API call against a real repo."""
    vuln_dir = tmp_path / "some_repo"
    vuln_dir.mkdir()
    (vuln_dir / "app.py").write_text("eval(user_input)\n")

    monkeypatch.chdir(tmp_path)
    relative_target = Path("some_repo")
    assert not relative_target.is_absolute()

    results = run_semgrep(relative_target)
    assert len(results) == 1
    parsed = parse_semgrep_result(results[0], relative_target)
    assert parsed["file_path"] == "app.py"  # not "some_repo/app.py", not the raw echoed path
