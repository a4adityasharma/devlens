"""
Code Parsing Engine (Phase 3 / architecture doc §6).

Wraps Tree-sitter grammars for the MVP languages (Python, JavaScript,
TypeScript). Uses the individual `tree-sitter-python` / `tree-sitter-
javascript` / `tree-sitter-typescript` packages rather than the
`tree-sitter-languages` bundle: as of tree-sitter>=0.22 the bundle's
pinned ABI is incompatible with the current `Language()` constructor
signature, which breaks at import/parse time. The per-language packages
are actively maintained against the current API.
"""
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node, Parser

EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


@dataclass
class ParsedFile:
    path: str
    language: str
    root_node: Node
    source: bytes


class UnsupportedLanguageError(Exception):
    pass


class TreeSitterParserPool:
    """Lazily builds and caches one Parser per language."""

    def __init__(self):
        self._languages = {
            "python": Language(tspython.language()),
            "javascript": Language(tsjavascript.language()),
            "typescript": Language(tstypescript.language_typescript()),
            "tsx": Language(tstypescript.language_tsx()),
        }
        self._parsers: dict[str, Parser] = {}

    def get_parser(self, language: str) -> Parser:
        if language not in self._languages:
            raise UnsupportedLanguageError(f"Unsupported language: {language}")
        if language not in self._parsers:
            self._parsers[language] = Parser(self._languages[language])
        return self._parsers[language]

    def language_for_path(self, path: Path) -> str | None:
        return EXTENSION_TO_LANGUAGE.get(path.suffix.lower())

    def parse_file(self, path: Path) -> ParsedFile | None:
        language = self.language_for_path(path)
        if language is None:
            return None
        try:
            source = path.read_bytes()
        except OSError:
            return None
        parser = self.get_parser(language)
        tree = parser.parse(source)
        # Normalize tsx -> typescript for downstream reporting; the tsx
        # grammar is only needed to *parse* correctly, symbol extraction
        # logic is shared with typescript.
        report_language = "typescript" if language == "tsx" else language
        return ParsedFile(
            path=str(path),
            language=report_language,
            root_node=tree.root_node,
            source=source,
        )


_pool: TreeSitterParserPool | None = None


def get_parser_pool() -> TreeSitterParserPool:
    global _pool
    if _pool is None:
        _pool = TreeSitterParserPool()
    return _pool
