from __future__ import annotations

import re

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, CitationVerdict

# STUB — replaced by 004-citation-verifier-subgraph with the real extract_claims/check_alignment/emit_verdict subgraph.
# 003 added attempt-aware behavior to enable deterministic retry-loop tests.

_FORCE_WEAK_RE = re.compile(r"FORCE_WEAK", re.IGNORECASE)
_FORCE_RETRY_RE = re.compile(r"FORCE_RETRY", re.IGNORECASE)


def _stub_verdict(state: AgentState) -> CitationVerdict:
    if _FORCE_WEAK_RE.search(state["question"]):
        return {
            "status": "weak",
            "confidence": 0.42,
            "notes": ["Forced weak citation verdict for retry-loop testing."],
        }

    if _FORCE_RETRY_RE.search(state["question"]):
        if state["attempt"] == 1:
            return {
                "status": "weak",
                "confidence": 0.42,
                "notes": ["Forced weak citation verdict on the first attempt."],
            }
        return {
            "status": "grounded",
            "confidence": 0.85,
            "notes": ["Forced grounded citation verdict on the retry attempt."],
        }

    if state["sources"]:
        return {"status": "grounded", "confidence": 0.85, "notes": []}
    return {"status": "not_applicable", "confidence": 1.0, "notes": []}


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

    verdict = _stub_verdict(state)

    write_event(
        state["thread_id"],
        attempt,
        "citation_verifier",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff={"citation_verdict": verdict},
    )
    return {"citation_verdict": verdict}
