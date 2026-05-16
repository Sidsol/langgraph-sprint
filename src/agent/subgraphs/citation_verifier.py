from __future__ import annotations

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, CitationVerdict

# STUB — replaced by 004-citation-verifier-subgraph with the real extract_claims/check_alignment/emit_verdict subgraph.


def citation_verifier(state: AgentState) -> dict[str, CitationVerdict]:
    attempt = state["attempt"]
    write_event(
        state["thread_id"],
        attempt,
        "citation_verifier",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={"sources": len(state["sources"]), "draft_answer": bool(state["draft_answer"])},
    )

    verdict: CitationVerdict = {
        "status": "grounded" if state["sources"] else "not_applicable",
        "confidence": 0.85,
        "notes": [],
    }

    write_event(
        state["thread_id"],
        attempt,
        "citation_verifier",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff={"citation_verdict": verdict},
    )
    return {"citation_verdict": verdict}
