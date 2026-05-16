from __future__ import annotations

import pytest

from agent import make_initial_state
from agent import logging as agent_logging
from agent.routers import route_after_evaluator, route_after_hitl, route_planner_output


@pytest.fixture
def isolated_logs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")


def _state(**overrides):
    state = make_initial_state("test question", "t-router", "offline")
    state.update(overrides)
    return state


def test_route_planner_output_returns_expected_branch(isolated_logs) -> None:
    assert route_planner_output(_state(selected_tool="search")) == "search_tool"
    assert route_planner_output(_state(selected_tool="calculator")) == "calculator_tool"
    assert route_planner_output(_state(selected_tool=None)) == "fallback"


def test_route_after_evaluator_returns_end_provisional_on_pass(isolated_logs) -> None:
    state = _state(
        evaluator_verdict={"status": "pass", "score": 0.9, "reason": "publishable"},
        unsafe_to_publish=False,
    )

    assert route_after_evaluator(state) == "END_PROVISIONAL"


def test_route_after_evaluator_returns_planner_on_retry(isolated_logs) -> None:
    state = _state(
        attempt=1,
        max_attempts=2,
        evaluator_verdict={"status": "retry", "score": 0.4, "reason": "needs retry"},
        unsafe_to_publish=True,
    )

    assert route_after_evaluator(state) == "planner"


def test_route_after_evaluator_returns_escalate_when_budget_exhausted(isolated_logs) -> None:
    state = _state(
        attempt=2,
        max_attempts=2,
        evaluator_verdict={"status": "retry", "score": 0.1, "reason": "budget exhausted"},
        unsafe_to_publish=True,
    )

    assert route_after_evaluator(state) == "escalate_to_human"


def test_route_after_evaluator_returns_fallback_otherwise(isolated_logs) -> None:
    state = _state(
        evaluator_verdict={"status": "fallback", "score": 0.6, "reason": "bounded answer only"},
        unsafe_to_publish=False,
    )

    assert route_after_evaluator(state) == "fallback"


def test_route_after_hitl_routes_publisher_or_end(isolated_logs) -> None:
    assert route_after_hitl(_state(human_decision="approved")) == "publisher"
    assert route_after_hitl(_state(human_decision="edited")) == "publisher"
    assert route_after_hitl(_state(human_decision="rejected")) == "END"
