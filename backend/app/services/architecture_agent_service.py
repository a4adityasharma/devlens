"""
Architecture Agent orchestrator (Phase 7 / architecture doc §18).

Unlike the Security Agent (app/services/security_agent_service.py), this
one is wired as a fourth **chained** best-effort pipeline step, not an
on-demand endpoint — a deliberate, measured decision, not a default:
`app/agents/architecture_analyzer.py`'s `analyze_architecture()` is pure
in-memory computation over data the pipeline already has (no subprocess,
no external tool), and benchmarked at ~3ms against a 6,000+-symbol real
repository (pallets/flask) during this phase's development — negligible
compared to the clone/parse/graph/embedding steps already in the chain.
The Security Agent's semgrep subprocess has no comparable guarantee (scan
time scales with repo size and rule count in a way this doesn't), which is
exactly why that one stayed on-demand — see its own module docstring.
"""
from sqlalchemy.orm import Session

from app.agents.architecture_analyzer import analyze_architecture
from app.models.models import GeneratedArtifact, RepositoryAnalysis


def run_architecture_analysis(db: Session, analysis: RepositoryAnalysis) -> dict:
    """Runs the layer/edge analysis over `analysis.symbols` and persists
    the Mermaid diagram (+ structured layer/edge data) as a
    GeneratedArtifact. No soft-fail path needed here (unlike
    graph_service/embedding_service/security_agent_service) — there's no
    external service that can be unreachable; an empty symbols list just
    produces an empty diagram rather than raising."""
    result = analyze_architecture(analysis.symbols or [])

    db.add(GeneratedArtifact(
        analysis_id=analysis.id,
        agent="architecture",
        artifact_type="mermaid_diagram",
        content=result["mermaid"],
        extra={"layers": result["layers"], "edges": result["edges"]},
    ))
    db.commit()

    return {
        "layer_count": len(result["layers"]),
        "edge_count": len(result["edges"]),
        "layers": result["layers"],
    }
