"""
Orchestrates Phase 5 (Semantic Search) on top of an already-completed
RepositoryAnalysis: chunks the repo's symbols, embeds each chunk, and
upserts into Qdrant. Mirrors analysis_service.py / graph_service.py's
pattern — its own file so Modules 1-3 stay untouched, and this stage can
fail/be skipped independently of them.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.embeddings.chunker import chunk_repository
from app.embeddings.embedder import get_embedder
from app.knowledge.qdrant_client import get_qdrant_client
from app.models.models import Repository, RepositoryAnalysis

COLLECTION_NAME = "devlens_code_chunks"


class EmbeddingSkipped(Exception):
    """Raised (and caught by the caller) when Qdrant isn't reachable, so a
    missing vector store degrades gracefully instead of failing the whole
    ingestion pipeline — same pattern as graph_service.GraphBuildSkipped."""


def run_embedding(db: Session, repository: Repository, analysis: RepositoryAnalysis) -> dict:
    client = get_qdrant_client()
    if not client.verify_connectivity():
        raise EmbeddingSkipped(
            "Qdrant is not reachable — skipping embedding. "
            "Start it via `docker compose up qdrant` and re-run analysis to enable search."
        )

    embedder = get_embedder()
    chunks = chunk_repository(Path(repository.local_path), repository.id, analysis.symbols or [])

    client.ensure_collection(COLLECTION_NAME, embedder.dimension)
    client.delete_by_repository(COLLECTION_NAME, repository.id)

    if chunks:
        vectors = embedder.embed_batch([c.text for c in chunks])
        points = [
            {"id": c.id, "vector": v, "payload": c.to_payload()}
            for c, v in zip(chunks, vectors)
        ]
        client.upsert(COLLECTION_NAME, points)

    summary = {
        "chunk_count": len(chunks),
        "embedder": type(embedder).__name__,
        "dimension": embedder.dimension,
        "by_type": _count_by(chunks, lambda c: c.type),
        "by_language": _count_by(chunks, lambda c: c.language),
    }

    stats = dict(analysis.stats or {})
    stats["embedding"] = summary
    analysis.stats = stats
    db.commit()
    return summary


def search_repository(repository_id: str, query: str, limit: int = 10) -> list[dict]:
    """Standalone semantic search — independently testable ahead of Phase 6
    (RAG), which will wrap an LLM + Neo4j graph context around this."""
    client = get_qdrant_client()
    if not client.verify_connectivity():
        raise EmbeddingSkipped("Qdrant is not reachable — cannot search.")
    embedder = get_embedder()
    [vector] = embedder.embed_batch([query])
    return client.search(COLLECTION_NAME, vector, limit=limit, repository_id=repository_id)


def _count_by(items, key_fn) -> dict:
    counts: dict[str, int] = {}
    for item in items:
        k = key_fn(item)
        counts[k] = counts.get(k, 0) + 1
    return counts
