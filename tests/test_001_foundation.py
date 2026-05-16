from __future__ import annotations

import json

import pytest

from agent import logging as agent_logging
from agent.state import AgentState, initial_state
from tools.calculator import safe_calc
from tools.llm import Chat, StubChat
from tools.searcher import FakeSearcher, Searcher

EXPECTED_STATE_KEYS = {
    "thread_id",
    "question",
    "plan",
    "selected_tool",
    "draft_answer",
    "edited_text",
    "sources",
    "messages",
    "tool_calls",
    "tool_results",
    "evaluator_verdict",
    "evaluator_history",
    "citation_verdict",
    "_verifier_claims",
    "_verifier_scores",
    "_verifier_notes",
    "attempt",
    "max_attempts",
    "retry_log",
    "confidence",
    "decision",
    "human_decision",
    "unsafe_to_publish",
    "published_path",
    "mode",
    "tool_error",
}


def test_initial_state_contains_every_architecture_key() -> None:
    state = initial_state("What is 12*12?", "thread-001", "offline")

    assert isinstance(state, dict)
    assert set(AgentState.__annotations__) == EXPECTED_STATE_KEYS
    assert set(state) == EXPECTED_STATE_KEYS
    assert state["thread_id"] == "thread-001"
    assert state["mode"] == "offline"


def test_fake_searcher_returns_normalized_results() -> None:
    searcher: Searcher = FakeSearcher()
    results = searcher.search("query")

    assert isinstance(searcher, Searcher)
    assert len(results) == 2
    for result in results:
        assert {"title", "url", "snippet"} <= set(result)
        assert "query" in result["snippet"]


def test_safe_calc_evaluates_restricted_arithmetic() -> None:
    assert safe_calc("12*12") == 144


def test_safe_calc_rejects_unsafe_expression() -> None:
    with pytest.raises(ValueError, match="unsafe expression"):
        safe_calc("__import__('os')")


def test_stub_chat_returns_string() -> None:
    chat: Chat = StubChat()
    response = chat.complete("hello world")

    assert isinstance(chat, Chat)
    assert isinstance(response, str)
    assert response.startswith("[STUB]")


def test_write_event_appends_jsonl_line(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")

    agent_logging.write_event(
        "thread-log",
        1,
        "planner",
        agent_logging.EVENT_NODE_ENTER,
        "offline",
        state_diff={"question": "hello"},
    )

    log_path = tmp_path / "logs" / "run-thread-log.jsonl"
    assert log_path.exists()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["thread_id"] == "thread-log"
    assert payload["attempt"] == 1
    assert payload["node"] == "planner"
    assert payload["event"] == agent_logging.EVENT_NODE_ENTER
    assert payload["mode"] == "offline"
    assert payload["state_diff"] == {"question": "hello"}
