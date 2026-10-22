"""
Testing Agent — coverage analysis (Phase 7 / architecture doc §17, step 1).

Identifies which function/method symbols are NOT called from any test
file — the candidates for test generation. Pure, deterministic computation
over the same flat `symbols` list every other phase already produces; no
LLM, no I/O beyond what's already in memory. This half of the Testing
Agent gets the same real (non-mocked) verification the Architecture Agent
did — see docs/PROGRESS.md's session notes.

"Tested" here means "referenced by name from a call symbol whose file
looks like a test file" — the same name-based, not type-resolved,
matching every other phase in this project uses (graph_builder.py's
CALLS, architecture_analyzer.py's cross-layer edges). A function called
only indirectly (e.g. only through a mock, or only via a fixture that
itself isn't directly named in a call) may be under-counted as untested;
that's a known limitation of name-based analysis, not a bug.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

_TEST_FILE_PATTERNS = [
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"(^|/)[^/]+_test\.py$"),
    re.compile(r"(^|/)[^/]+\.test\.[jt]sx?$"),
    re.compile(r"(^|/)[^/]+\.spec\.[jt]sx?$"),
]
_TEST_DIR_NAMES = {"tests", "test", "__tests__"}


def is_test_file(file_path: str) -> bool:
    """True if this file's name or containing directory marks it as a
    test file, by the conventions this project (and most Python/JS/TS
    projects) actually use."""
    if any(pattern.search(file_path) for pattern in _TEST_FILE_PATTERNS):
        return True
    parts = {p.lower() for p in Path(file_path).parts[:-1]}
    return bool(parts & _TEST_DIR_NAMES)


@dataclass
class UntestedSymbol:
    file: str
    name: str
    type: str  # function | method
    parent: str | None
    line_start: int
    line_end: int
    parameters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.file, "name": self.name, "type": self.type,
            "parent": self.parent, "line_start": self.line_start,
            "line_end": self.line_end, "parameters": self.parameters,
        }


def find_untested_symbols(symbols: list[dict]) -> list[UntestedSymbol]:
    """Returns every function/method NOT defined in a test file that has
    no call from a test file referencing it by name."""
    tested_names: set[str] = set()
    for s in symbols:
        if s.get("type") != "call":
            continue
        if is_test_file(s.get("file", "")):
            tested_names.add(s.get("name"))

    untested = []
    for s in symbols:
        if s.get("type") not in ("function", "method"):
            continue
        if is_test_file(s.get("file", "")):
            continue  # test helper functions aren't "code under test"
        if s.get("name") in tested_names:
            continue
        untested.append(UntestedSymbol(
            file=s["file"], name=s["name"], type=s["type"], parent=s.get("parent"),
            line_start=s["line_start"], line_end=s["line_end"],
            parameters=s.get("parameters") or [],
        ))
    return untested
