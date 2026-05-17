from __future__ import annotations

from agent.logging import EVENT_END, EVENT_NODE_ENTER, EVENT_NODE_EXIT, EVENT_PUBLISH, write_event
from agent.state import AgentState
from publisher.publisher import publish_atomic


def publisher(state: AgentState) -> dict[str, object]:
    if state.get("published_path") is not None:
        write_event(
            state["thread_id"],
            state["attempt"],
            "publisher",
            EVENT_NODE_EXIT,
            state["mode"],
            state_diff={"skip": "already_published"},
        )
        return {}

    write_event(state["thread_id"], state["attempt"], "publisher", EVENT_NODE_ENTER, state["mode"])
    final_text = state.get("edited_text") or state.get("draft_answer", "")
    answer_path, eml_path = publish_atomic(
        thread_id=state["thread_id"],
        final_text=final_text,
        sources=state.get("sources", []),
        question=state.get("question", ""),
        mode=state["mode"],
        research_report=state.get("research_report"),
        research_depth=state.get("research_depth", "shallow"),
    )
    write_event(
        state["thread_id"],
        state["attempt"],
        "publisher",
        EVENT_PUBLISH,
        state["mode"],
        answer_path=answer_path,
        eml_path=eml_path,
        state_diff={"published_path": answer_path},
    )
    write_event(
        state["thread_id"],
        state["attempt"],
        "END",
        EVENT_END,
        state["mode"],
        state_diff={"final_decision": "published"},
    )
    return {
        "published_path": answer_path,
        "decision": "end",
    }
