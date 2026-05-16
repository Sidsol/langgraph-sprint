from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

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
_INTERRUPT_CHANNEL = "__interrupt__"


def _resolve_db_path(db_path: str | None = None) -> Path:
    resolved_db_path = Path(db_path or os.getenv("CHECKPOINT_DB") or _DEFAULT_CHECKPOINT_DB)
    if not resolved_db_path.is_absolute():
        resolved_db_path = Path.cwd() / resolved_db_path
    return resolved_db_path


def _open_checkpointer(db_path: str | None = None) -> tuple[SqliteSaver, sqlite3.Connection]:
    resolved_db_path = _resolve_db_path(db_path)
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(resolved_db_path), check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.conn.execute("PRAGMA journal_mode=WAL;")
    saver.setup()
    return saver, connection


def _extract_interrupt_payload(interrupt: Any) -> dict[str, Any] | None:
    payload = interrupt.value if hasattr(interrupt, "value") else interrupt
    return payload if isinstance(payload, dict) else None


def _extract_interrupt_node(interrupt: Any) -> str | None:
    namespaces = getattr(interrupt, "ns", ()) or ()
    if not namespaces:
        return None
    return str(namespaces[0]).split(":", 1)[0]


def _extract_pending_interrupt(pending_writes: list[tuple[Any, str, Any]] | None) -> tuple[str | None, dict[str, Any] | None]:
    for _, channel, value in pending_writes or []:
        if channel != _INTERRUPT_CHANNEL:
            continue
        interrupt = value[0] if isinstance(value, list) and value else value
        payload = _extract_interrupt_payload(interrupt)
        if payload is not None:
            return _extract_interrupt_node(interrupt), payload
    return None, None


def _checkpoint_sort_key(checkpoint_tuple: Any) -> tuple[float, int, str]:
    checkpoint = checkpoint_tuple.checkpoint if isinstance(checkpoint_tuple.checkpoint, dict) else {}
    metadata = checkpoint_tuple.metadata if isinstance(checkpoint_tuple.metadata, dict) else {}

    raw_ts = checkpoint.get("ts")
    try:
        timestamp = datetime.fromisoformat(raw_ts).timestamp() if isinstance(raw_ts, str) else float("-inf")
    except ValueError:
        timestamp = float("-inf")

    step = metadata.get("step") if isinstance(metadata.get("step"), int) else -1
    checkpoint_id = checkpoint.get("id") if isinstance(checkpoint.get("id"), str) else ""
    return timestamp, step, checkpoint_id


def make_checkpointer(db_path: str | None = None) -> SqliteSaver:
    saver, _ = _open_checkpointer(db_path)
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


def list_paused_threads(db_path: str | None = None) -> list[dict[str, Any]]:
    """List paused root threads by scanning the latest SqliteSaver checkpoint per thread.

    This uses ``SqliteSaver.list(None)`` rather than querying SQLite tables directly.
    We keep the newest root checkpoint for each ``thread_id`` and then look for a
    pending ``__interrupt__`` write to identify paused approval/escalation threads.
    """

    resolved_db_path = _resolve_db_path(db_path)
    if not resolved_db_path.exists():
        return []

    saver, connection = _open_checkpointer(str(resolved_db_path))
    try:
        latest_by_thread: dict[str, tuple[tuple[float, int, str], Any]] = {}
        for checkpoint_tuple in saver.list(None):
            config = checkpoint_tuple.config if isinstance(checkpoint_tuple.config, dict) else {}
            configurable = config.get("configurable") if isinstance(config.get("configurable"), dict) else {}
            if configurable.get("checkpoint_ns", "") not in {"", None}:
                continue

            thread_id = configurable.get("thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                continue

            sort_key = _checkpoint_sort_key(checkpoint_tuple)
            current = latest_by_thread.get(thread_id)
            if current is None or sort_key > current[0]:
                latest_by_thread[thread_id] = (sort_key, checkpoint_tuple)

        paused_threads: list[dict[str, Any]] = []
        for thread_id, (_, checkpoint_tuple) in latest_by_thread.items():
            node, payload = _extract_pending_interrupt(checkpoint_tuple.pending_writes)
            if payload is None:
                continue
            paused_threads.append(
                {
                    "thread_id": thread_id,
                    "node": node or "",
                    "kind": str(payload.get("kind", "unknown")),
                    "payload": payload,
                }
            )

        paused_threads.sort(key=lambda item: str(item["thread_id"]))
        return paused_threads
    finally:
        connection.close()


def get_paused_payload(graph: CompiledGraph, thread_id: str) -> dict[str, Any] | None:
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    if not getattr(snapshot, "next", ()):  # not paused
        return None

    for interrupt in getattr(snapshot, "interrupts", ()):
        payload = _extract_interrupt_payload(interrupt)
        if payload is not None:
            return payload
    return None


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


def resume_thread(
    graph: CompiledGraph,
    thread_id: str,
    decision: str,
    edited_text: str | None = None,
) -> dict[str, object]:
    return resume_pause(graph, thread_id, decision, edited_text)


__all__ = [
    "build_graph",
    "derive_thread_id",
    "get_paused_payload",
    "list_paused_threads",
    "make_checkpointer",
    "resume_pause",
    "resume_thread",
]
