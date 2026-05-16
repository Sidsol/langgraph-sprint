from __future__ import annotations

from uuid import uuid4

import pytest
from langgraph.graph.state import CompiledStateGraph

from agent import make_initial_state
from agent import logging as agent_logging
from agent.state import SourceRecord
from agent.subgraphs.citation_verifier import citation_verifier


def _invoke_subgraph(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    question: str,
    draft_answer: str,
    sources: list[SourceRecord],
    attempt: int = 1,
):
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")
    thread_id = f"t-test-004-{uuid4().hex}"
    state = make_initial_state(question, thread_id, "offline")
    state.update({"attempt": attempt, "draft_answer": draft_answer, "sources": sources})
    return citation_verifier.invoke(state)


def test_subgraph_compiles() -> None:
    assert isinstance(citation_verifier, CompiledStateGraph)


def test_subgraph_internal_nodes() -> None:
    graph_nodes = set(citation_verifier.get_graph().nodes)

    assert {"extract_claims", "check_alignment", "emit_verdict"} <= graph_nodes


def test_grounded_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    result = _invoke_subgraph(
        monkeypatch,
        tmp_path,
        question="Tell me about LangGraph",
        draft_answer="LangGraph is a graph orchestration library. LangGraph supports stateful workflows.",
        sources=[
            {
                "title": "LangGraph docs",
                "url": "https://example.com/langgraph",
                "snippet": "LangGraph is a graph orchestration library built for stateful workflows.",
            }
        ],
    )

    assert result["citation_verdict"]["status"] == "grounded"
    assert result["citation_verdict"]["confidence"] >= 0.70
    assert result["_verifier_claims"] is None
    assert result["_verifier_scores"] is None
    assert result["_verifier_notes"] is None


def test_weak_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    result = _invoke_subgraph(
        monkeypatch,
        tmp_path,
        question="Tell me about LangGraph",
        draft_answer="LangGraph is a graph orchestration library.",
        sources=[
            {
                "title": "Fruit facts",
                "url": "https://example.com/fruit",
                "snippet": "Bananas are yellow fruit that grow in tropical climates.",
            }
        ],
    )

    assert result["citation_verdict"]["status"] == "weak"
    assert result["citation_verdict"]["confidence"] < 0.70


def test_not_applicable_when_no_sources(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    result = _invoke_subgraph(
        monkeypatch,
        tmp_path,
        question="What is 12*12?",
        draft_answer="12*12 = 144",
        sources=[],
    )

    assert result["citation_verdict"]["status"] == "not_applicable"
    assert result["citation_verdict"]["confidence"] == pytest.approx(1.0)


def test_force_weak_marker_still_works(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    result = _invoke_subgraph(
        monkeypatch,
        tmp_path,
        question="FORCE_WEAK tell me about LangGraph",
        draft_answer="LangGraph is a graph orchestration library.",
        sources=[
            {
                "title": "LangGraph docs",
                "url": "https://example.com/langgraph",
                "snippet": "LangGraph is a graph orchestration library.",
            }
        ],
    )

    assert result["citation_verdict"]["status"] == "weak"
    assert result["citation_verdict"]["confidence"] == pytest.approx(0.30)


def test_force_retry_marker_attempt_aware(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    common_kwargs = {
        "question": "FORCE_RETRY tell me about LangGraph",
        "draft_answer": "LangGraph is a graph orchestration library.",
        "sources": [
            {
                "title": "LangGraph docs",
                "url": "https://example.com/langgraph",
                "snippet": "LangGraph is a graph orchestration library.",
            }
        ],
    }

    first_attempt = _invoke_subgraph(monkeypatch, tmp_path, attempt=1, **common_kwargs)
    second_attempt = _invoke_subgraph(monkeypatch, tmp_path, attempt=2, **common_kwargs)

    assert first_attempt["citation_verdict"]["status"] == "weak"
    assert first_attempt["citation_verdict"]["confidence"] == pytest.approx(0.30)
    assert second_attempt["citation_verdict"]["status"] == "grounded"
    assert second_attempt["citation_verdict"]["confidence"] == pytest.approx(0.85)
