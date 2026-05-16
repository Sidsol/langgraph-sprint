from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledGraph

from agent.nodes import calculator_tool, escalate_to_human, evaluator, fallback, planner, search_tool
from agent.routers import route_after_evaluator, route_planner_output
from agent.state import AgentState
from agent.subgraphs import citation_verifier_subgraph


def build_graph(*, mode: str, checkpointer: BaseCheckpointSaver | None = None) -> CompiledGraph:
    if mode not in {"live", "offline"}:
        raise ValueError(f"unsupported mode: {mode}")

    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("planner", planner)
    graph_builder.add_node("search_tool", search_tool)
    graph_builder.add_node("calculator_tool", calculator_tool)
    graph_builder.add_node("citation_verifier", citation_verifier_subgraph)
    graph_builder.add_node("evaluator", evaluator)
    graph_builder.add_node("fallback", fallback)
    graph_builder.add_node("escalate_to_human", escalate_to_human)

    graph_builder.add_edge(START, "planner")
    graph_builder.add_conditional_edges(
        "planner",
        route_planner_output,
        {
            "search_tool": "search_tool",
            "calculator_tool": "calculator_tool",
            "fallback": "fallback",
        },
    )
    graph_builder.add_edge("search_tool", "citation_verifier")
    graph_builder.add_edge("calculator_tool", "citation_verifier")
    graph_builder.add_edge("citation_verifier", "evaluator")
    graph_builder.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "END_PROVISIONAL": END,
            "planner": "planner",
            "fallback": "fallback",
            "escalate_to_human": "escalate_to_human",
        },
    )
    graph_builder.add_edge("fallback", END)
    graph_builder.add_edge("escalate_to_human", END)

    saver = checkpointer or InMemorySaver()
    return graph_builder.compile(checkpointer=saver)


__all__ = ["build_graph"]
