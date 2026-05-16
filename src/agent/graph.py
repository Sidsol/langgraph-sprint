from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledGraph

from agent.logging import EVENT_BRANCH_DECISION, EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.nodes import calculator_tool, evaluator, planner, search_tool
from agent.state import AgentState
from agent.subgraphs import citation_verifier_subgraph


def _route_tool(state: AgentState) -> Literal["search_tool", "calculator_tool"]:
    branch: Literal["search_tool", "calculator_tool"]
    if state["selected_tool"] == "calculator":
        branch = "calculator_tool"
    else:
        branch = "search_tool"

    write_event(
        state["thread_id"],
        state["attempt"],
        "tool_router",
        EVENT_BRANCH_DECISION,
        state["mode"],
        branch=branch,
        state_diff={"selected_tool": state["selected_tool"]},
    )
    return branch


def _fallback_stub(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"]
    write_event(
        state["thread_id"],
        attempt,
        "fallback",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={"draft_answer": bool(state["draft_answer"]), "tool_error": state["tool_error"]},
    )
    draft_answer = state["draft_answer"] or "Fallback is deferred to feature 003-routing-and-retry-loop."
    update = {"draft_answer": draft_answer, "decision": "fallback", "unsafe_to_publish": bool(state["tool_error"])}
    write_event(
        state["thread_id"],
        attempt,
        "fallback",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff=update,
    )
    return update


def build_graph(*, mode: str, checkpointer: BaseCheckpointSaver | None = None) -> CompiledGraph:
    if mode not in {"live", "offline"}:
        raise ValueError(f"unsupported mode: {mode}")

    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("planner", planner)
    graph_builder.add_node("search_tool", search_tool)
    graph_builder.add_node("calculator_tool", calculator_tool)
    graph_builder.add_node("citation_verifier", citation_verifier_subgraph)
    graph_builder.add_node("evaluator", evaluator)
    graph_builder.add_node("fallback", _fallback_stub)

    graph_builder.add_edge(START, "planner")
    graph_builder.add_conditional_edges(
        "planner",
        _route_tool,
        {"search_tool": "search_tool", "calculator_tool": "calculator_tool"},
    )
    graph_builder.add_edge("search_tool", "citation_verifier")
    graph_builder.add_edge("calculator_tool", "citation_verifier")
    graph_builder.add_edge("citation_verifier", "evaluator")
    graph_builder.add_edge("evaluator", END)
    graph_builder.add_edge("fallback", END)

    saver = checkpointer or InMemorySaver()
    return graph_builder.compile(checkpointer=saver)


__all__ = ["build_graph"]
