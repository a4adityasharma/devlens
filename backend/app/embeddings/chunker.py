"""
Code Chunking (Phase 5 / architecture doc §11).

Turns each function/class/method symbol (already extracted by Phase 3's
Tree-sitter pass and stored on RepositoryAnalysis.symbols) into a
searchable chunk, by slicing the *actual source text* for that symbol's
line range out of the cloned repo on disk — NOT by splitting on a fixed
character count, which architecture doc §11 explicitly calls out as the
wrong approach for source code.

This module has no embedding-provider or vector-store dependency — it only
reads files and returns plain dicts, so it can be (and is, in
tests/test_chunker.py) unit-tested with zero I/O mocking beyond real
temporary files.
"""
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.analyzer.parser import EXTENSION_TO_LANGUAGE

# Only these symbol types become chunks — imports and calls are graph data
# (Phase 4), not independently meaningful units of code to search over.
CHUNKABLE_TYPES = {"function", "class", "method"}


@dataclass
class Chunk:
    id: str
    repository_id: str
    file: str
    symbol: str
    type: str
    language: str
    start_line: int
    end_line: int
    text: str
    parent: str | None = None
    parameters: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        """Qdrant point payload — everything except the embedding vector
        itself and the raw text (payload carries text too, so results are
        self-contained without a second lookup)."""
        return {
            "repository_id": self.repository_id,
            "file": self.file,
            "symbol": self.symbol,
            "type": self.type,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent": self.parent,
            "parameters": self.parameters,
            "text": self.text,
        }


_ID_NAMESPACE = uuid.UUID("6f6e8f4a-d1b1-4c3e-9a2e-5a4e2b9f7c11")  # arbitrary, fixed


def _chunk_id(repository_id: str, file: str, symbol_type: str, name: str, start_line: int) -> str:
    """Deterministic id so re-chunking an unchanged symbol upserts the same
    Qdrant point instead of accumulating duplicates across re-analyses.

    Must be a valid UUID string (or unsigned int) — Qdrant's point IDs
    reject arbitrary strings like a raw SHA-1 hex digest (discovered by
    testing against a real local Qdrant engine, see
    tests/test_embedding_service.py: the original SHA-1-hex-string version
    of this function failed with "Point id ... is not a valid UUID" the
    first time it actually hit Qdrant, mock-based tests would never have
    caught this). uuid5 gives a deterministic UUID from the same raw key.
    """
    raw = f"{repository_id}:{file}:{symbol_type}:{name}:{start_line}"
    return str(uuid.uuid5(_ID_NAMESPACE, raw))


def _read_lines(local_path: Path, file: str) -> list[str] | None:
    try:
        text = (local_path / file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text.splitlines()


def chunk_repository(local_path: Path, repository_id: str, symbols: list[dict]) -> list[Chunk]:
    """symbols: the flat list from RepositoryAnalysis.symbols (Phase 3
    output). Returns one Chunk per function/class/method symbol that has a
    non-empty line range and whose source file could be read."""
    chunks: list[Chunk] = []
    file_cache: dict[str, list[str] | None] = {}

    for s in symbols:
        if s.get("type") not in CHUNKABLE_TYPES:
            continue
        file = s.get("file")
        name = s.get("name")
        start = s.get("line_start")
        end = s.get("line_end")
        if not file or not name or not start or not end or end < start:
            continue

        if file not in file_cache:
            file_cache[file] = _read_lines(local_path, file)
        lines = file_cache[file]
        if lines is None:
            continue

        # 1-indexed inclusive slice, clamped to what the file actually has.
        snippet_lines = lines[max(0, start - 1):min(len(lines), end)]
        text = "\n".join(snippet_lines).strip()
        if not text:
            continue

        language = EXTENSION_TO_LANGUAGE.get(Path(file).suffix.lower(), "unknown")
        if language == "tsx":
            language = "typescript"

        chunks.append(Chunk(
            id=_chunk_id(repository_id, file, s["type"], name, start),
            repository_id=repository_id,
            file=file,
            symbol=name,
            type=s["type"],
            language=language,
            start_line=start,
            end_line=end,
            text=text,
            parent=s.get("parent"),
            parameters=s.get("parameters") or [],
        ))

    return chunks
