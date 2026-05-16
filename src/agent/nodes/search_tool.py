from __future__ import annotations

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, SourceRecord, ToolCallRecord, ToolResultRecord
from tools import make_searcher


def _build_draft_answer(question: str, sources: list[SourceRecord]) -> str:
    lead = sources[0]
    source_titles = ", ".join(source["title"] for source in sources)
    return f"For '{question}', the strongest evidence says: {lead['snippet']} Sources: {source_titles}."


def search_tool(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"]
    question = state["question"]
    write_event(
        state["thread_id"],
        attempt,
        "search_tool",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={"question": question, "plan": state["plan"]},
    )

    tool_call: ToolCallRecord = {
        "tool": "search",
        "input": question,
        "attempt": attempt,
        "mode": state["mode"],
    }

    try:
        results = make_searcher(state["mode"]).search(question, max_results=2)
        if not results:
            raise RuntimeError("search returned no results")

        sources: list[SourceRecord] = [
            {"title": result["title"], "url": result["url"], "snippet": result["snippet"]}
            for result in results
        ]
        draft_answer = _build_draft_answer(question, sources)
        confidence = 0.85 if state["mode"] == "offline" else 0.8
        tool_result: ToolResultRecord = {
            "tool": "search",
            "ok": True,
            "summary": f"Retrieved {len(sources)} search result(s).",
            "error": None,
        }
        update = {
            "sources": sources,
            "draft_answer": draft_answer,
            "confidence": confidence,
            "tool_calls": [tool_call],
            "tool_results": [tool_result],
            "tool_error": None,
        }
    except Exception as exc:
        error = str(exc)
        tool_result = {
            "tool": "search",
            "ok": False,
            "summary": "Search execution failed.",
            "error": error,
        }
        update = {
            "sources": [],
            "draft_answer": "",
            "confidence": 0.0,
            "tool_calls": [tool_call],
            "tool_results": [tool_result],
            "tool_error": error,
        }

    write_event(
        state["thread_id"],
        attempt,
        "search_tool",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff={
            "sources": len(update["sources"]),
            "confidence": update["confidence"],
            "tool_error": update["tool_error"],
        },
    )
    return update
