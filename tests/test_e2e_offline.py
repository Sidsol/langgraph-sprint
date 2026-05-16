from __future__ import annotations

import json
from typing import Any, get_args
from uuid import uuid4

import pytest

from agent import build_graph, make_initial_state
from agent import logging as agent_logging
from agent.state import Mitigation


@pytest.fixture
def isolated_logs(tmp_path, monkeypatch: pytest.MonkeyPatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(agent_logging, "LOGS_DIR", log_dir)
    return log_dir


@pytest.fixture
def thread_id_factory():
    def factory(prefix: str) -> str:
        return f"{prefix}-{uuid4().hex}"

    return factory


def _invoke_offline(question: str, thread_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    graph = build_graph(mode="offline")
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(make_initial_state(question, thread_id, "offline"), config)
    return graph, config, result


def _extract_interrupt_payload(graph: Any, config: dict[str, Any], result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
    if interrupts:
        snapshot = graph.get_state(config)
        payload = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        return snapshot.values, payload

    snapshot = graph.get_state(config)
    snapshot_interrupts = getattr(snapshot, "interrupts", ())
    if snapshot_interrupts:
        payload = snapshot_interrupts[0].value if hasattr(snapshot_interrupts[0], "value") else snapshot_interrupts[0]
        return snapshot.values, payload

    return result, {}


def test_offline_pass_through(isolated_logs, thread_id_factory) -> None:
    thread_id = thread_id_factory("pass")
    _, _, result = _invoke_offline("What is 2+3?", thread_id)

    assert "__interrupt__" not in result
    assert result["draft_answer"] == "2+3 = 5"
    assert result["selected_tool"] == "calculator"
    assert result["attempt"] == 1
    assert result["retry_log"] == []
    assert result["decision"] == "publish"


def test_offline_retry_then_pass(isolated_logs, thread_id_factory) -> None:
    thread_id = thread_id_factory("retry")
    _, _, result = _invoke_offline("FORCE_RETRY tell me about LangGraph", thread_id)

    assert "__interrupt__" not in result
    assert result["attempt"] == 2
    assert len(result["retry_log"]) == 1
    assert result["retry_log"][0]["mitigation"] in {"revised_query", "switched_tool", "added_context"}


def test_offline_escalate_after_budget_exhausted(isolated_logs, thread_id_factory) -> None:
    thread_id = thread_id_factory("escalate")
    graph, config, result = _invoke_offline("FORCE_WEAK tell me about LangGraph", thread_id)
    state, payload = _extract_interrupt_payload(graph, config, result)

    assert payload["kind"] == "escalation"
    assert len(state["retry_log"]) == 2
    assert state["retry_log"][-1]["mitigation"] == "escalated_to_human"


def test_jsonl_retry_event_has_mitigation(isolated_logs, thread_id_factory) -> None:
    thread_id = thread_id_factory("retry-log")
    _invoke_offline("FORCE_RETRY tell me about LangGraph", thread_id)

    log_path = isolated_logs / f"run-{thread_id}.jsonl"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    retry_events = [event for event in events if event["event"] == agent_logging.EVENT_RETRY]
    mitigation_values = set(get_args(Mitigation))

    assert retry_events
    assert any(
        "reason" in event
        and "mitigation" in event
        and event["mitigation"] in mitigation_values
        for event in retry_events
    )
