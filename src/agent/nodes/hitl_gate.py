from __future__ import annotations

from langgraph.types import interrupt

from agent.logging import EVENT_INTERRUPT_EMITTED, EVENT_INTERRUPT_RESUMED, EVENT_NODE_ENTER, write_event
from agent.state import AgentState


def hitl_gate(state: AgentState) -> dict[str, object]:
    write_event(state["thread_id"], state["attempt"], "hitl_gate", EVENT_NODE_ENTER, state["mode"])
    payload = {
        "kind": "approval",
        "draft_answer": state.get("draft_answer", ""),
        "sources": state.get("sources", []),
        "verifier_verdict": state.get("citation_verdict")
        or {"status": "not_applicable", "confidence": 1.0, "notes": []},
        "attempt": state["attempt"],
        "mode": state["mode"],
    }
    write_event(
        state["thread_id"],
        state["attempt"],
        "hitl_gate",
        EVENT_INTERRUPT_EMITTED,
        state["mode"],
        state_diff={"kind": "approval", "sources_count": len(payload["sources"])},
    )
    resume_value = interrupt(payload)
    decision = resume_value.get("decision", "rejected") if isinstance(resume_value, dict) else "rejected"
    edited_text = resume_value.get("edited_text") if isinstance(resume_value, dict) else None
    write_event(
        state["thread_id"],
        state["attempt"],
        "hitl_gate",
        EVENT_INTERRUPT_RESUMED,
        state["mode"],
        decision=decision,
        state_diff={"edited_text": edited_text},
    )
    next_decision = "publish" if decision in ("approved", "edited") else "end"
    return {
        "human_decision": decision,
        "edited_text": edited_text,
        "decision": next_decision,
    }
