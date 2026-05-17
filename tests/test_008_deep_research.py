from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from agent import logging as agent_logging
from agent import make_initial_state, resume_pause
from agent.nodes.planner import planner
from agent.subgraphs.citation_verifier import check_alignment, citation_verifier, extract_claims
from tools.searcher import FakeSearcher


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_logging, "LOGS_DIR", tmp_path / "logs")
    return tmp_path / "logs"


def _thread_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _invoke(graph, question: str, thread_id: str) -> tuple[dict[str, object], dict[str, object]]:
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(make_initial_state(question, thread_id, "offline"), config)
    return config, result


def _fact_report(claim: str, citations: list[int], *, synthesized: bool = False) -> dict[str, object]:
    return {
        "direct_answer": claim,
        "key_facts": [
            {
                "claim": claim,
                "citations": citations,
                "confidence": 0.8,
                "synthesized": synthesized,
            }
        ],
        "perspectives": [],
        "unknowns": [],
        "glossary": [],
        "sources_by_domain": {},
        "sub_queries_run": ["q"],
    }


def test_planner_chooses_deep_for_compare_question() -> None:
    result = planner(make_initial_state("compare A vs B", _thread_id("deep"), "offline"))

    assert result["selected_tool"] == "search"
    assert result["research_depth"] == "deep"


def test_planner_chooses_shallow_for_short_factual() -> None:
    result = planner(make_initial_state("What is 12*12?", _thread_id("shallow"), "offline"))

    assert result["selected_tool"] == "calculator"
    assert result["research_depth"] == "shallow"
    assert result["research_plan"] == []


def test_planner_research_plan_deterministic_offline() -> None:
    question = "Explain LangGraph agent orchestration patterns"
    first = planner(make_initial_state(question, _thread_id("plan-a"), "offline"))
    second = planner(make_initial_state(question, _thread_id("plan-b"), "offline"))

    assert first["research_depth"] == "deep"
    assert first["research_plan"] == second["research_plan"]
    assert len(first["research_plan"]) <= 5


def test_multi_search_dedupes_by_url() -> None:
    results = FakeSearcher().multi_search(["q1", "q2", "q1"])
    urls = [result["url"] for result in results]

    assert len(urls) == len(set(urls))


def test_research_report_has_all_sections(offline_graph) -> None:
    graph, _ = offline_graph
    thread_id = _thread_id("report")
    _, result = _invoke(graph, "Compare LangGraph and LangChain agent abstractions", thread_id)
    report = result["research_report"]

    assert result["research_depth"] == "deep"
    assert report is not None
    assert report["direct_answer"]
    assert len(report["key_facts"]) >= 1
    assert isinstance(report["sources_by_domain"], dict)
    assert report["sub_queries_run"] == result["research_plan"]


def test_synthesized_fact_triggers_weak_verdict() -> None:
    state = make_initial_state("Explain a topic", _thread_id("synth"), "offline")
    state.update(
        {
            "attempt": 1,
            "research_report": _fact_report("Unsupported synthesis.", [], synthesized=True),
            "sources": [
                {
                    "title": "Example",
                    "url": "https://example.com/source",
                    "snippet": "Grounded source text that does not support the synthesis.",
                }
            ],
        }
    )

    result = citation_verifier.invoke(state)

    assert result["citation_verdict"]["status"] == "weak"


def test_source_diversity_boost() -> None:
    claim = "Topology mismatch claim"
    same_domain_state = make_initial_state(claim, _thread_id("same-domain"), "offline")
    same_domain_state.update(
        {
            "attempt": 1,
            "research_report": _fact_report(claim, [0, 1]),
            "sources": [
                {"title": "A", "url": "https://docs.example.com/one", "snippet": "agent memory planning"},
                {"title": "B", "url": "https://docs.example.com/two", "snippet": "tool routing retries"},
            ],
        }
    )
    same_claims = {**same_domain_state, **extract_claims(same_domain_state)}
    same_score = check_alignment(same_claims)["_verifier_scores"][0]

    cross_domain_state = make_initial_state(claim, _thread_id("cross-domain"), "offline")
    cross_domain_state.update(
        {
            "attempt": 1,
            "research_report": _fact_report(claim, [0, 1]),
            "sources": [
                {"title": "A", "url": "https://docs.example.com/one", "snippet": "agent memory planning"},
                {"title": "B", "url": "https://blog.example.org/two", "snippet": "tool routing retries"},
            ],
        }
    )
    cross_claims = {**cross_domain_state, **extract_claims(cross_domain_state)}
    cross_score = check_alignment(cross_claims)["_verifier_scores"][0]

    assert cross_score > same_score


def test_e2e_deep_publish_structured_markdown(offline_graph, temp_outbox) -> None:
    graph, _ = offline_graph
    thread_id = _thread_id("deep-publish")
    _invoke(graph, "Compare LangGraph and LangChain agent abstractions", thread_id)
    final_state = resume_pause(graph, thread_id, "approved")
    answer_path = temp_outbox / "answers" / f"{thread_id}.md"
    published = answer_path.read_text(encoding="utf-8")

    assert final_state["published_path"] is not None
    assert "## Direct Answer" in published
    assert "## Key Facts" in published
    assert "## Sources" in published


def test_legacy_shallow_path_still_works(offline_graph, temp_outbox) -> None:
    graph, _ = offline_graph
    thread_id = _thread_id("legacy")
    _invoke(graph, "What is 7*8?", thread_id)
    final_state = resume_pause(graph, thread_id, "approved")
    answer_path = temp_outbox / "answers" / f"{thread_id}.md"
    published = answer_path.read_text(encoding="utf-8")

    assert final_state["published_path"] is not None
    assert "7*8 = 56" in published
    assert "## Direct Answer" not in published
    assert "## Key Facts" not in published


def test_force_retry_still_works_with_deep_mode(offline_graph) -> None:
    graph, _ = offline_graph
    thread_id = _thread_id("force-retry")
    _, result = _invoke(graph, "FORCE_RETRY tell me about LangGraph subgraphs", thread_id)

    assert result["research_depth"] == "deep"
    assert result["attempt"] == 2
    assert len(result["retry_log"]) == 1
