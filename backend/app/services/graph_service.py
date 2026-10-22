"""
Orchestrates Phase 4 (Knowledge Graph) on top of an already-completed
RepositoryAnalysis: takes its `symbols` list and writes it into Neo4j via
app/knowledge/graph_builder.py.

Kept as its own service (mirrors analysis_service.py's pattern) so Modules
1-2 stay untouched and this stage can fail/be skipped independently — e.g.
if Neo4j isn't reachable, the repository is still fully usable for its
scan + parsed-symbol data, it just won't have a graph yet.
"""
from sqlalchemy.orm import Session

from app.knowledge.graph_builder import build_knowledge_graph
from app.knowledge.neo4j_client import get_neo4j_client
from app.models.models import RepositoryAnalysis


class GraphBuildSkipped(Exception):
    """Raised (and caught by the caller) when Neo4j isn't reachable, so a
    missing graph backend degrades gracefully instead of failing the whole
    ingestion pipeline."""


def run_graph_build(db: Session, analysis: RepositoryAnalysis) -> dict:
    client = get_neo4j_client()
    if not client.verify_connectivity():
        raise GraphBuildSkipped(
            "Neo4j is not reachable — skipping graph build. "
            "Start it via `docker compose up neo4j` and re-run analysis to build the graph."
        )

    summary = build_knowledge_graph(client, analysis.repository_id, analysis.symbols or [])

    stats = dict(analysis.stats or {})
    stats["graph"] = summary
    analysis.stats = stats
    db.commit()
    return summary
