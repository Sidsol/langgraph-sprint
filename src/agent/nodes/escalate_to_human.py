from __future__ import annotations

import json

from langgraph.types import interrupt

from agent import logging as agent_logging
from agent.logging import EVENT_ESCALATE, EVENT_INTERRUPT_EMITTED, EVENT_INTERRUPT_RESUMED, write_event
from agent.state import AgentState


def _interrupt_already_emitted(thread_id: str, attempt: int) -> bool:
    log_path = agent_logging.LOGS_DIR / f"run-{thread_id}.jsonl"
    if not log_path.exists():
        return False

    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                payload.get("node") == "escalate_to_human"
                and payload.get("event") == EVENT_INTERRUPT_EMITTED
                and payload.get("attempt") == attempt
            ):
                return True
    return False


def escalate_to_human(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"]
    payload = {
        "kind": "escalation",
        "question": state["question"],
        "draft_answer": state["draft_answer"],
        "sources": state["sources"],
        "retry_log": state["retry_log"],
        "attempt": attempt,
        "mode": state["mode"],
    }

    if not _interrupt_already_emitted(state["thread_id"], attempt):
        write_event(
            state["thread_id"],
            attempt,
            "escalate_to_human",
            EVENT_INTERRUPT_EMITTED,
            state["mode"],
            state_diff={"kind": payload["kind"], "sources": len(state["sources"])} ,
        )

    resume_value = interrupt(payload)
    if not isinstance(resume_value, dict):
        raise ValueError("invalid escalation resume payload")

    decision = resume_value.get("decision")
    if decision not in {"acknowledged", "edited"}:
        raise ValueError("decision must be 'acknowledged' or 'edited'")

    edited_text = resume_value.get("edited_text")
    if decision == "edited" and not isinstance(edited_text, str):
        raise ValueError("edited escalation decisions require edited_text")
    if decision != "edited":
        edited_text = None

    write_event(
        state["thread_id"],
        attempt,
        "escalate_to_human",
        EVENT_INTERRUPT_RESUMED,
        state["mode"],
        decision=decision,
        state_diff={"edited_text": edited_text},
    )

    retry_entry = state["retry_log"][-1] if state["retry_log"] else {
        "attempt": attempt,
        "reason": "manual takeover requested",
        "mitigation": "escalated_to_human",
    }
    write_event(
        state["thread_id"],
        attempt,
        "escalate_to_human",
        EVENT_ESCALATE,
        state["mode"],
        decision=decision,
        reason=retry_entry["reason"],
        mitigation=retry_entry["mitigation"],
        state_diff={"unsafe_to_publish": state["unsafe_to_publish"]},
    )

    update: dict[str, object] = {"human_decision": decision, "decision": "end"}
    if edited_text is not None:
        update["edited_text"] = edited_text
    return update
