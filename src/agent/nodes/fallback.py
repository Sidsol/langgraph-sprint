from __future__ import annotations

from agent.logging import EVENT_END, EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState

_FALLBACK_MESSAGE = "Unable to provide a confident answer; tools or evidence were insufficient."


def fallback(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"]
    write_event(
        state["thread_id"],
        attempt,
        "fallback",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={"retry_log": len(state["retry_log"]), "tool_error": state["tool_error"]},
    )

    update = {
        "draft_answer": _FALLBACK_MESSAGE,
        "confidence": 0.0,
        "decision": "end",
    }

    write_event(
        state["thread_id"],
        attempt,
        "fallback",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff=update,
    )
    write_event(
        state["thread_id"],
        attempt,
        "END",
        EVENT_END,
        state["mode"],
        state_diff={"final_decision": "fallback"},
    )
    return update
