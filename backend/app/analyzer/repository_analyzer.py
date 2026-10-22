"""
Repository-level driver for the Code Parsing Engine.

Walks every source file under a cloned repository (skipping the same
ignored directories as Module 1's repository_service), runs the
Tree-sitter extractor on each supported file, and aggregates the results
into the shape stored on RepositoryAnalysis.stats / .symbols.
"""
import os
from pathlib import Path

from app.analyzer.ast_extractor import Symbol, extract_symbols_from_file
from app.analyzer.parser import EXTENSION_TO_LANGUAGE
from app.core.config import get_settings

settings = get_settings()


def _iter_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in settings.IGNORED_DIRS]
        for fname in filenames:
            yield Path(dirpath) / fname


def analyze_repository(local_path: Path) -> dict:
    """Parse every supported file under local_path.

    Returns:
        {
            "symbols": [Symbol.to_dict(), ...],
            "stats": {
                "files_parsed": int,
                "files_skipped_unsupported": int,
                "function_count": int,
                "class_count": int,
                "method_count": int,
                "import_count": int,
                "by_language": {"python": N, "javascript": N, ...},
            }
        }
    """
    all_symbols: list[Symbol] = []
    files_parsed = 0
    files_skipped = 0

    for path in _iter_source_files(local_path):
        if path.suffix.lower() not in EXTENSION_TO_LANGUAGE:
            continue
        symbols = extract_symbols_from_file(path)
        if symbols or path.stat().st_size == 0:
            files_parsed += 1
        else:
            # Parsed but yielded nothing (e.g. empty file, or a file type
            # we mapped an extension for but don't have a walker for yet).
            files_skipped += 1
        rel_path = str(path.relative_to(local_path))
        for s in symbols:
            s.file = rel_path
        all_symbols.extend(symbols)

    counts = {"function": 0, "class": 0, "method": 0, "import": 0}
    by_language: dict[str, int] = {}
    for s in all_symbols:
        counts[s.type] = counts.get(s.type, 0) + 1

    for path in _iter_source_files(local_path):
        lang = EXTENSION_TO_LANGUAGE.get(path.suffix.lower())
        if lang:
            report_lang = "typescript" if lang == "tsx" else lang
            by_language[report_lang] = by_language.get(report_lang, 0) + 1

    return {
        "symbols": [s.to_dict() for s in all_symbols],
        "stats": {
            "files_parsed": files_parsed,
            "files_skipped_unsupported": files_skipped,
            "function_count": counts.get("function", 0),
            "class_count": counts.get("class", 0),
            "method_count": counts.get("method", 0),
            "import_count": counts.get("import", 0),
            "by_language": by_language,
        },
    }
