"""
Security scanner wrapper (Phase 7 / architecture doc §16).

Wraps Semgrep as a subprocess (it's a CLI tool, not meaningfully usable as
a Python import) using ONLY the local rule file in
app/agents/rules/security_rules.yaml — never `--config=auto` or a registry
ruleset ID. Semgrep's rule registry lives at semgrep.dev, which has never
been reachable in any session's sandbox; local rule files need zero
network access and were verified end-to-end here (see docs/PROGRESS.md).

Architecture doc §16 is explicit that the Security Agent should wrap a
deterministic scanner rather than ask an LLM to find vulnerabilities from
scratch — this module is that deterministic layer. Interpretation
(severity framing, explanation) stays close to what Semgrep itself
reports; nothing here calls an LLM.
"""
import json
import os
import subprocess
from pathlib import Path

_DEFAULT_RULES_PATH = Path(__file__).parent / "rules" / "security_rules.yaml"


class ScannerUnavailable(Exception):
    """The semgrep binary couldn't be found/run at all — distinct from a
    scan that ran and failed, mirrors GraphBuildSkipped/EmbeddingSkipped's
    soft-fail pattern for 'the tool isn't installed/reachable'."""


class ScannerError(Exception):
    """semgrep ran but exited with an error, timed out, or produced
    unparseable output."""


def _semgrep_binary() -> str:
    """Defaults to 'semgrep' on PATH — a plain `pip install -r
    requirements.txt` puts it there directly. Overridable via SEMGREP_BIN
    for any environment where that's not the case (e.g. a separate venv).

    Note: an earlier version of requirements.txt pinned `pydantic==2.9.2`
    and `uvicorn==0.30.6`, which made semgrep's own dependency (`mcp`,
    needed for semgrep's MCP-server feature) impossible to resolve
    alongside the rest of this project's stack — NOT a sandbox-specific
    quirk, a real conflict that would break `pip install -r
    requirements.txt` anywhere. Fixed by relaxing those two pins (see
    requirements.txt and docs/PROGRESS.md's session notes on this) rather
    than by routing around it with a separate venv, which is what an
    earlier session did before finding the real cause."""
    return os.environ.get("SEMGREP_BIN", "semgrep")


def run_semgrep(target_path: Path, rules_path: Path | None = None, timeout: int = 120) -> list[dict]:
    """Runs semgrep against target_path with the local rules file, returns
    the raw list of result dicts from semgrep's `--json` output (each
    shaped like {"check_id", "path", "start": {"line",...}, "end": {...},
    "extra": {"message", "severity", "metadata": {...}}})."""
    rules_path = rules_path or _DEFAULT_RULES_PATH
    binary = _semgrep_binary()
    cmd = [binary, "--config", str(rules_path), "--json", "--quiet", str(target_path)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ScannerUnavailable(
            f"semgrep binary not found ('{binary}'). Install it (pip install semgrep) "
            f"or set SEMGREP_BIN to its path."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ScannerError(f"semgrep scan exceeded {timeout}s timeout on {target_path}") from exc

    # semgrep exits 0 (no findings) or 1 (findings present, still a
    # successful run) — anything else is a real error.
    if result.returncode not in (0, 1):
        raise ScannerError(f"semgrep exited {result.returncode}: {result.stderr[:500]}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ScannerError(f"semgrep produced non-JSON output: {result.stdout[:500]}") from exc

    return data.get("results", [])


def parse_semgrep_result(result: dict, repo_root: Path) -> dict:
    """Converts one raw semgrep result into the common finding shape the
    rest of the pipeline (validation, Finding model) expects.

    Resolves both `result["path"]` and `repo_root` to absolute, canonical
    paths before computing the relative path between them — NOT a simple
    "is it absolute already?" check. That simpler check was the first
    version of this function and was wrong: semgrep echoes back whatever
    path form was used to invoke it (relative-to-CWD when the target was
    passed as a relative path, like `repository.local_path` genuinely is
    in production — see repository_service.py's REPO_STORAGE_PATH
    default). Treating an already-relative result path as "relative to
    repo_root" only happened to work when repo_root itself was passed as
    an absolute path; with a relative repo_root (the real pipeline's
    actual case), every real finding failed `_validate_finding()` and was
    silently rejected. Caught by testing against a real cloned repository
    through the live API, not by the unit tests — every unit test in this
    project so far happened to pass an absolute tmp_path/FIXTURES path,
    which is exactly the case that masked this bug.
    """
    resolved_result_path = Path(result["path"]).resolve()
    resolved_repo_root = repo_root.resolve()
    try:
        file_path = str(resolved_result_path.relative_to(resolved_repo_root))
    except ValueError:
        # Shouldn't happen (semgrep only reports paths under the scanned
        # target), but fall back to the raw path rather than crashing.
        file_path = str(result["path"])

    extra = result.get("extra", {})
    metadata = extra.get("metadata", {})
    check_id = result.get("check_id", "unknown-check").split(".")[-1]

    return {
        "category": metadata.get("category", "Security"),
        "severity": extra.get("severity", "WARNING"),
        "title": check_id.replace("-", " ").replace("_", " ").title(),
        "description": extra.get("message", ""),
        "recommendation": metadata.get("recommendation"),
        "file_path": file_path,
        "line_start": result["start"]["line"],
        "line_end": result["end"]["line"],
        "confidence": None,  # this ruleset doesn't attach confidence scores
    }
