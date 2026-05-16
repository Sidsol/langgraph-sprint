from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledGraph
from langgraph.types import Command

from agent.nodes import (
    calculator_tool,
    escalate_to_human,
    evaluator,
    fallback,
    hitl_gate,
    planner,
    publisher,
    search_tool,
)
from agent.routers import route_after_evaluator, route_after_hitl, route_planner_output
from agent.state import AgentState
from agent.subgraphs import citation_verifier_subgraph

_DEFAULT_CHECKPOINT_DB = ".checkpoints/agent.sqlite"


def make_checkpointer(db_path: str | None = None) -> SqliteSaver:
    resolved_db_path = Path(db_path or os.getenv("CHECKPOINT_DB") or _DEFAULT_CHECKPOINT_DB)
    if not resolved_db_path.is_absolute():
        resolved_db_path = Path.cwd() / resolved_db_path
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(resolved_db_path), check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.conn.execute("PRAGMA journal_mode=WAL;")
    saver.setup()
    return saver


def build_graph(
    *,
    mode: str,
    checkpointer: BaseCheckpointSaver | None = None,
    db_path: str | None = None,
) -> CompiledGraph:
    if mode not in {"live", "offline"}:
        raise ValueError(f"unsupported mode: {mode}")

    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("planner", planner)
    graph_builder.add_node("search_tool", search_tool)
    graph_builder.add_node("calculator_tool", calculator_tool)
    graph_builder.add_node("citation_verifier", citation_verifier_subgraph)
    graph_builder.add_node("evaluator", evaluator)
    graph_builder.add_node("hitl_gate", hitl_gate)
    graph_builder.add_node("publisher", publisher)
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
            "hitl_gate": "hitl_gate",
            "planner": "planner",
            "fallback": "fallback",
            "escalate_to_human": "escalate_to_human",
        },
    )
    graph_builder.add_conditional_edges(
        "hitl_gate",
        route_after_hitl,
        {
            "publisher": "publisher",
            "END": END,
        },
    )
    graph_builder.add_edge("publisher", END)
    graph_builder.add_edge("fallback", END)
    graph_builder.add_edge("escalate_to_human", END)

    saver = checkpointer or make_checkpointer(db_path)
    return graph_builder.compile(checkpointer=saver)


def derive_thread_id(prefix: str = "t") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def resume_pause(
    graph: CompiledGraph,
    thread_id: str,
    decision: str,
    edited_text: str | None = None,
) -> dict[str, object]:
    return graph.invoke(
        Command(resume={"decision": decision, "edited_text": edited_text}),
        {"configurable": {"thread_id": thread_id}},
    )


__all__ = ["build_graph", "derive_thread_id", "make_checkpointer", "resume_pause"]
