"""
Documentation Agent (Phase 7 / architecture doc §19).

Unlike the Security and Architecture Agents, this one's ENTIRE value
proposition is the LLM generation step — there is no meaningful LLM-free
version of "write a README." So unlike those two, there's no way to keep
the risky part small; instead, the prompt and the grounding check are
co-designed the same way chat_service.py's `[SOURCE: ...]` markers and its
citation validator were: the prompt REQUIRES backtick-wrapping for any
file path or function/class/method name claimed to be real, which makes
"did it reference something that doesn't exist" mechanically checkable
rather than a fuzzy prose-parsing problem.

Architecture doc §19 is explicit: don't overwrite repository files.
Generated docs are persisted as GeneratedArtifact rows
(agent="documentation"), never written back into the cloned repo.

Verification status: same as chat_service.py and test_generator.py —
`api.anthropic.com` is reachable from this sandbox, no
`ANTHROPIC_API_KEY` is configured, so generation has never been exercised
against a live model. `_call_llm` is mocked in every test. What DOES get
real test coverage: the grounding checker, which is pure logic — see
test_doc_generator.py, including a deliberately-fabricated reference the
checker must catch (same bar the Testing Agent's validator was held to).
"""
import re

from app.agents.llm_client import LLMSkipped, call_llm

DOC_TYPES = ("readme", "architecture_overview", "setup_guide", "api_reference")

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_KNOWN_FILE_EXTENSIONS = {
    "py", "js", "jsx", "ts", "tsx", "json", "yaml", "yml", "md", "txt",
    "toml", "cfg", "ini", "html", "css", "sh", "env", "sql", "xml",
}


def _looks_like_a_path(mention: str) -> bool:
    """A file path, not a dotted symbol reference like `AuthService.login`
    or a Python module path like `app.services.auth`. The distinguishing
    signal is a slash, or a trailing segment that's a recognized file
    extension — a bare dotted identifier's last segment ('login') won't
    be one of those, so it correctly falls through to symbol-name
    checking instead."""
    if "/" in mention:
        return True
    tail = mention.rsplit(".", 1)[-1].lower()
    return tail in _KNOWN_FILE_EXTENSIONS


_SYSTEM_PROMPT = """You write clear, accurate technical documentation for a software repository.

You will be given: the repository's real file list, real function/class/
method names (grouped by file), any existing README content, and (if
available) an architecture summary already derived from the real
codebase.

Base everything strictly on this provided information. Do not invent
files, functions, classes, endpoints, or behavior that isn't shown to
you. If you don't have enough information for a section, say so briefly
rather than guessing.

Any time you reference a specific real file path or a real function/
class/method name, wrap it in single backticks EXACTLY as it appears in
the provided lists (e.g. `app/services/auth_service.py` or
`AuthService.login`). Do not wrap ordinary prose, generic terms, or
invented names in backticks — backticks are a claim of "this exact thing
exists in the repository," so only use them for names taken directly from
the provided lists."""

_DOC_TYPE_INSTRUCTIONS = {
    "readme": "Write a README: what the project does, key features (only ones evidenced by the real file/symbol list), and a brief usage note.",
    "architecture_overview": "Write an architecture overview: the main layers/components and how they relate, using the provided architecture summary if given.",
    "setup_guide": "Write a setup guide: how someone would install dependencies and run this project, based on real files like requirements/package manifests if mentioned.",
    "api_reference": "Write API reference documentation for the functions/methods provided, grouped by file.",
}


class DocGenerationSkipped(Exception):
    """Raised when the LLM can't be called (no API key configured) — same
    soft-fail shape as chat_service.ChatSkipped / test_generator.TestGenerationSkipped."""


def _call_llm(system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-5") -> str:
    try:
        return call_llm(system_prompt, user_prompt, model=model, max_tokens=2048)
    except LLMSkipped as exc:
        raise DocGenerationSkipped(str(exc)) from exc


def build_user_prompt(doc_type: str, repo_name: str, files: list[str],
                       symbols_by_file: dict[str, list[str]], existing_readme: str | None,
                       architecture_summary: str | None) -> str:
    lines = [
        _DOC_TYPE_INSTRUCTIONS.get(doc_type, f"Write documentation of type: {doc_type}"),
        f"\nRepository: {repo_name}",
        f"\nReal files ({len(files)}):",
    ]
    lines.extend(f"  {f}" for f in files[:200])  # cap to keep the prompt bounded for huge repos
    if len(files) > 200:
        lines.append(f"  ... and {len(files) - 200} more files")

    lines.append("\nReal functions/classes/methods by file:")
    for f, names in list(symbols_by_file.items())[:100]:
        if names:
            lines.append(f"  {f}: {', '.join(names[:30])}")

    if architecture_summary:
        lines.append(f"\nArchitecture summary (derived from real code):\n{architecture_summary}")
    if existing_readme:
        lines.append(f"\nExisting README content (for reference, don't just repeat it):\n{existing_readme[:3000]}")

    return "\n".join(lines)


def generate_documentation(doc_type: str, repo_name: str, files: list[str],
                            symbols_by_file: dict[str, list[str]], existing_readme: str | None = None,
                            architecture_summary: str | None = None) -> str:
    if doc_type not in DOC_TYPES:
        raise ValueError(f"Unknown doc_type '{doc_type}', must be one of {DOC_TYPES}")
    user_prompt = build_user_prompt(doc_type, repo_name, files, symbols_by_file, existing_readme, architecture_summary)
    return _call_llm(_SYSTEM_PROMPT, user_prompt)


def check_grounding(doc_text: str, valid_files: set[str], valid_symbol_names: set[str]) -> dict:
    """Pure function, no I/O — extracts every backtick-wrapped span and
    checks it against the real file/symbol sets. A backticked span that
    doesn't match either set is "ungrounded": either a hallucinated
    file/name, or (less likely, given the prompt) a mis-escaped piece of
    ordinary prose. Either way it's flagged, not silently trusted.

    Handles dotted method references (`AuthService.login`) by also
    accepting a match on just the trailing segment, since symbols are
    tracked by bare name (see app.analyzer.ast_extractor.Symbol), not by
    fully-qualified path.
    """
    mentions = _BACKTICK_RE.findall(doc_text)
    ungrounded_files = []
    ungrounded_symbols = []

    for mention in mentions:
        if _looks_like_a_path(mention):
            if mention not in valid_files:
                ungrounded_files.append(mention)
        else:
            bare_name = mention.rsplit(".", 1)[-1]
            if mention not in valid_symbol_names and bare_name not in valid_symbol_names:
                ungrounded_symbols.append(mention)

    return {
        "total_mentions": len(mentions),
        "ungrounded_files": ungrounded_files,
        "ungrounded_symbols": ungrounded_symbols,
        "fully_grounded": not ungrounded_files and not ungrounded_symbols,
    }
