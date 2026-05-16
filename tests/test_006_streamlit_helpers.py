from __future__ import annotations

import importlib
from pathlib import Path
from uuid import uuid4

import pytest

from agent import build_graph, make_initial_state
from agent.graph import get_paused_payload, list_paused_threads, resume_thread


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    agent_logging = importlib.import_module("agent.logging")
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(agent_logging, "LOGS_DIR", log_dir)
    return log_dir


def _thread_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _pause_offline(graph, question: str, thread_id: str) -> None:
    graph.invoke(make_initial_state(question, thread_id, "offline"), {"configurable": {"thread_id": thread_id}})


def test_list_paused_threads_empty(tmp_path: Path) -> None:
    db_path = tmp_path / ".checkpoints" / "agent.sqlite"
    build_graph(mode="offline", db_path=str(db_path))

    assert list_paused_threads(str(db_path)) == []


def test_list_paused_threads_after_pause(offline_graph) -> None:
    graph, db_path = offline_graph
    thread_id = _thread_id("paused")

    _pause_offline(graph, "What is 2+2?", thread_id)
    paused_threads = list_paused_threads(str(db_path))
    match = next((thread for thread in paused_threads if thread["thread_id"] == thread_id), None)

    assert match is not None
    assert match["node"] == "hitl_gate"
    assert match["kind"] == "approval"


def test_get_paused_payload(offline_graph) -> None:
    graph, _ = offline_graph
    thread_id = _thread_id("payload")

    _pause_offline(graph, "What is 12*12?", thread_id)
    payload = get_paused_payload(graph, thread_id)

    assert payload is not None
    assert {"kind", "draft_answer", "sources", "verifier_verdict", "attempt", "mode"} <= payload.keys()
    assert payload["kind"] == "approval"


def test_resume_thread_approves_publishes(offline_graph, temp_outbox) -> None:
    graph, _ = offline_graph
    thread_id = _thread_id("approve")

    _pause_offline(graph, "What is 12*12?", thread_id)
    final_state = resume_thread(graph, thread_id, "approved")
    answer_path = temp_outbox / "answers" / f"{thread_id}.md"

    assert final_state["published_path"] is not None
    assert answer_path.exists()


def test_resume_thread_rejects_no_publish(offline_graph, temp_outbox) -> None:
    graph, _ = offline_graph
    thread_id = _thread_id("reject")

    _pause_offline(graph, "What is 12*12?", thread_id)
    final_state = resume_thread(graph, thread_id, "rejected")
    answer_path = temp_outbox / "answers" / f"{thread_id}.md"

    assert final_state["published_path"] is None
    assert not answer_path.exists()
