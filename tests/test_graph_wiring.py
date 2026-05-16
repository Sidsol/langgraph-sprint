from __future__ import annotations

from langgraph.checkpoint.sqlite import SqliteSaver

import agent.logging as agent_logging
from agent import make_initial_state
from agent.nodes import planner


def _extract_interrupt_payload(result: dict[str, object]) -> dict[str, object]:
    interrupts = result.get("__interrupt__", ())
    if not interrupts:
        return {}
    interrupt = interrupts[0]
    return interrupt.value if hasattr(interrupt, "value") else interrupt


def test_graph_compiles_offline(offline_graph) -> None:
    compiled, _ = offline_graph

    assert compiled is not None
    assert hasattr(compiled, "invoke")
    assert isinstance(compiled.checkpointer, SqliteSaver)


def test_graph_has_required_nodes(offline_graph) -> None:
    compiled, _ = offline_graph

    graph_nodes = set(compiled.get_graph().nodes)
    assert {
        "planner",
        "search_tool",
        "calculator_tool",
        "citation_verifier",
        "evaluator",
        "hitl_gate",
        "publisher",
    } <= graph_nodes


def test_planner_selects_calculator_for_arithmetic(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")
    result = planner(make_initial_state("12*12", "t-test-002-calc", "offline"))

    assert result["selected_tool"] == "calculator"


def test_planner_selects_search_for_factual(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")
    result = planner(make_initial_state("Who invented LangGraph?", "t-test-002-search", "offline"))

    assert result["selected_tool"] == "search"


def test_offline_run_pauses_for_approval(tmp_path, monkeypatch, offline_graph) -> None:
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")
    graph, _ = offline_graph
    thread_id = "t-test-005-run"
    result = graph.invoke(
        make_initial_state("12*12", thread_id, "offline"),
        {"configurable": {"thread_id": thread_id}},
    )
    payload = _extract_interrupt_payload(result)

    assert result["draft_answer"] == "12*12 = 144"
    assert result["decision"] == "publish"
    assert result["human_decision"] == "pending"
    assert payload["kind"] == "approval"
