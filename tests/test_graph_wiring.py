from __future__ import annotations

import agent.logging as agent_logging
from agent import build_graph, make_initial_state
from agent.nodes import planner


def test_graph_compiles_offline() -> None:
    compiled = build_graph(mode="offline")

    assert compiled is not None
    assert hasattr(compiled, "invoke")


def test_graph_has_required_nodes() -> None:
    compiled = build_graph(mode="offline")

    graph_nodes = set(compiled.get_graph().nodes)
    assert {"planner", "search_tool", "calculator_tool", "citation_verifier", "evaluator"} <= graph_nodes


def test_planner_selects_calculator_for_arithmetic(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")
    result = planner(make_initial_state("12*12", "t-test-002-calc", "offline"))

    assert result["selected_tool"] == "calculator"


def test_planner_selects_search_for_factual(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")
    result = planner(make_initial_state("Who invented LangGraph?", "t-test-002-search", "offline"))

    assert result["selected_tool"] == "search"


def test_offline_run_terminates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")
    graph = build_graph(mode="offline")
    thread_id = "t-test-002-run"
    result = graph.invoke(
        make_initial_state("12*12", thread_id, "offline"),
        {"configurable": {"thread_id": thread_id}},
    )

    assert result["draft_answer"] == "12*12 = 144"
    assert result["decision"] == "publish"
    assert result["human_decision"] == "pending"
