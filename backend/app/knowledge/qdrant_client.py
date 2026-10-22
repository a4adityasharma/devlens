"""
Thin wrapper around `qdrant-client` (architecture doc §12-13), mirroring
neo4j_client.py's shape: one client object, a handful of narrow methods,
no knowledge of chunks/repositories/symbols — that logic lives in
app/services/embedding_service.py.

Unlike Neo4j, Qdrant's Python client has a genuine embedded/local mode
(`QdrantClient(":memory:")` or `QdrantClient(path=...)`) that runs the
real Qdrant query engine in-process with no server — this was verified
directly in this session (see docs/PROGRESS.md session notes) and is what
tests/test_qdrant_client.py and test_embedding_service.py run against, so
those tests exercise real Qdrant behavior, not a hand-written mock.
`docker compose up qdrant` + QDRANT_URL is still the production path.
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import get_settings

settings = get_settings()


class VectorStoreClient:
    def __init__(self, qdrant_client: QdrantClient | None = None, url: str | None = None):
        """Pass `qdrant_client` directly to inject a local (":memory:")
        instance in tests; otherwise connects to `url` (default:
        settings.QDRANT_URL, the docker-compose service)."""
        if qdrant_client is not None:
            self._client = qdrant_client
        else:
            self._client = QdrantClient(url=url or settings.QDRANT_URL)

    def verify_connectivity(self) -> bool:
        try:
            self._client.get_collections()
            return True
        except Exception:  # noqa: BLE001
            return False

    def ensure_collection(self, name: str, dimension: int, distance: Distance = Distance.COSINE) -> None:
        existing = {c.name for c in self._client.get_collections().collections}
        if name not in existing:
            self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dimension, distance=distance),
            )

    def upsert(self, collection: str, points: list[dict]) -> None:
        """points: [{"id": ..., "vector": [...], "payload": {...}}, ...]
        `id` should be a stable string/int per chunk (see chunker._chunk_id)
        so re-analysis upserts in place rather than duplicating."""
        self._client.upsert(
            collection_name=collection,
            points=[PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points],
        )

    def delete_by_repository(self, collection: str, repository_id: str) -> None:
        """Clears a repository's existing points before a fresh upsert, same
        pattern as graph_builder.py's _CLEAR_REPO step — re-analysis
        shouldn't leave stale chunks from since-deleted symbols behind."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        try:
            self._client.delete(
                collection_name=collection,
                points_selector=Filter(must=[FieldCondition(key="repository_id", match=MatchValue(value=repository_id))]),
            )
        except Exception:  # noqa: BLE001
            # Collection may not exist yet on a repo's first-ever analysis.
            pass

    def search(self, collection: str, vector: list[float], limit: int = 10,
               repository_id: str | None = None) -> list[dict]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        query_filter = None
        if repository_id is not None:
            query_filter = Filter(must=[FieldCondition(key="repository_id", match=MatchValue(value=repository_id))])

        result = self._client.query_points(
            collection_name=collection, query=vector, limit=limit, query_filter=query_filter,
        )
        return [{"id": p.id, "score": p.score, **p.payload} for p in result.points]


_client: VectorStoreClient | None = None


def get_qdrant_client() -> VectorStoreClient:
    global _client
    if _client is None:
        _client = VectorStoreClient()
    return _client
