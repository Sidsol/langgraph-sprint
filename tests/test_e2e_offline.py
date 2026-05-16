from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args
from uuid import uuid4

import pytest

from agent import make_initial_state, resume_pause
from agent import logging as agent_logging
from agent.nodes.publisher import publisher
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


def _invoke_offline(graph: Any, question: str, thread_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(make_initial_state(question, thread_id, "offline"), config)
    return config, result


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


def _read_events(log_dir: Path, thread_id: str) -> list[dict[str, Any]]:
    log_path = log_dir / f"run-{thread_id}.jsonl"
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def test_offline_pass_through(offline_graph, isolated_logs, thread_id_factory) -> None:
    graph, _ = offline_graph
    thread_id = thread_id_factory("pass")
    config, result = _invoke_offline(graph, "What is 2+3?", thread_id)
    state, payload = _extract_interrupt_payload(graph, config, result)

    assert payload["kind"] == "approval"
    assert state["draft_answer"] == "2+3 = 5"
    assert state["selected_tool"] == "calculator"
    assert state["attempt"] == 1
    assert state["retry_log"] == []
    assert state["decision"] == "publish"


def test_offline_retry_then_pass(offline_graph, isolated_logs, thread_id_factory) -> None:
    graph, _ = offline_graph
    thread_id = thread_id_factory("retry")
    config, result = _invoke_offline(graph, "FORCE_RETRY tell me about LangGraph", thread_id)
    state, payload = _extract_interrupt_payload(graph, config, result)

    assert payload["kind"] == "approval"
    assert state["attempt"] == 2
    assert len(state["retry_log"]) == 1
    assert state["retry_log"][0]["mitigation"] in {"revised_query", "switched_tool", "added_context"}


def test_offline_escalate_after_budget_exhausted(offline_graph, isolated_logs, thread_id_factory) -> None:
    graph, _ = offline_graph
    thread_id = thread_id_factory("escalate")
    config, result = _invoke_offline(graph, "FORCE_WEAK tell me about LangGraph", thread_id)
    state, payload = _extract_interrupt_payload(graph, config, result)

    assert payload["kind"] == "escalation"
    assert len(state["retry_log"]) == 2
    assert state["retry_log"][-1]["mitigation"] == "escalated_to_human"


def test_jsonl_retry_event_has_mitigation(offline_graph, isolated_logs, thread_id_factory) -> None:
    graph, _ = offline_graph
    thread_id = thread_id_factory("retry-log")
    _invoke_offline(graph, "FORCE_RETRY tell me about LangGraph", thread_id)

    retry_events = [event for event in _read_events(isolated_logs, thread_id) if event["event"] == agent_logging.EVENT_RETRY]
    mitigation_values = set(get_args(Mitigation))

    assert retry_events
    assert any(
        "reason" in event
        and "mitigation" in event
        and event["mitigation"] in mitigation_values
        for event in retry_events
    )


def test_offline_approve_path_publishes(offline_graph, temp_outbox, isolated_logs, thread_id_factory) -> None:
    graph, _ = offline_graph
    thread_id = thread_id_factory("approve")
    config, result = _invoke_offline(graph, "What is 12*12?", thread_id)
    _, payload = _extract_interrupt_payload(graph, config, result)
    final_state = resume_pause(graph, thread_id, "approved")
    answer_path = temp_outbox / "answers" / f"{thread_id}.md"

    assert payload["kind"] == "approval"
    assert final_state["published_path"] is not None
    assert answer_path.exists()


def test_offline_reject_path_no_publish(offline_graph, temp_outbox, isolated_logs, thread_id_factory) -> None:
    graph, _ = offline_graph
    thread_id = thread_id_factory("reject")
    _invoke_offline(graph, "What is 12*12?", thread_id)
    final_state = resume_pause(graph, thread_id, "rejected")
    answer_path = temp_outbox / "answers" / f"{thread_id}.md"

    assert final_state["published_path"] is None
    assert not answer_path.exists()


def test_offline_edit_path_publishes_edited_text(offline_graph, temp_outbox, isolated_logs, thread_id_factory) -> None:
    graph, _ = offline_graph
    thread_id = thread_id_factory("edit")
    _invoke_offline(graph, "What is 12*12?", thread_id)
    final_state = resume_pause(graph, thread_id, "edited", edited_text="My edit")
    answer_path = temp_outbox / "answers" / f"{thread_id}.md"

    assert final_state["published_path"] is not None
    assert answer_path.exists()
    assert "My edit" in answer_path.read_text(encoding="utf-8")


def test_publisher_dedupe_guard_noop_on_reentry(temp_outbox, isolated_logs, capsys, thread_id_factory) -> None:
    thread_id = thread_id_factory("publisher")
    state = make_initial_state("What is 12*12?", thread_id, "offline")
    state.update({"attempt": 1, "draft_answer": "12*12 = 144", "decision": "publish"})

    first_result = publisher(state)
    first_capture = capsys.readouterr()
    answer_path = temp_outbox / "answers" / f"{thread_id}.md"
    sent_path = temp_outbox / "sent" / f"{thread_id}.eml"

    second_state = {**state, **first_result}
    second_result = publisher(second_state)
    second_capture = capsys.readouterr()

    assert first_result["published_path"] is not None
    assert answer_path.exists()
    assert sent_path.exists()
    assert first_capture.out
    assert second_result == {}
    assert second_capture.out == ""
    assert len(list((temp_outbox / "answers").glob("*.md"))) == 1
    assert len(list((temp_outbox / "sent").glob("*.eml"))) == 1


def test_hitl_logs_emitted_and_resumed(offline_graph, temp_outbox, isolated_logs, thread_id_factory) -> None:
    graph, _ = offline_graph
    thread_id = thread_id_factory("hitl-log")
    _invoke_offline(graph, "What is 12*12?", thread_id)
    resume_pause(graph, thread_id, "approved")
    events = _read_events(isolated_logs, thread_id)

    assert any(event["node"] == "hitl_gate" and event["event"] == agent_logging.EVENT_INTERRUPT_EMITTED for event in events)
    assert any(event["node"] == "hitl_gate" and event["event"] == agent_logging.EVENT_INTERRUPT_RESUMED for event in events)
