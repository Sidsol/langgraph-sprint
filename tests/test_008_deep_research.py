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


# --- Live-mode tests for the silent-fallback fix --------------------------------


class _CannedChat:
    """Test double for Chat. Returns a canned response and records call args."""

    def __init__(self, response: str = "", *, raise_exc: Exception | None = None):
        self.response = response
        self.raise_exc = raise_exc
        self.calls: list[dict[str, object]] = []

    def complete(self, prompt, *, system=None, max_tokens=512, response_format=None):
        self.calls.append(
            {
                "prompt_len": len(prompt),
                "max_tokens": max_tokens,
                "response_format": response_format,
                "system": system,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


def _live_search_state(thread_id: str, question: str = "Explain X") -> dict[str, object]:
    state = make_initial_state(question, thread_id, "live")
    state["research_plan"] = [question, "background on X", "examples of X"]
    state["research_depth"] = "deep"
    state["attempt"] = 1
    state["plan"] = "Investigate X"
    state["selected_tool"] = "search"
    return state


def _patched_search_tool(monkeypatch: pytest.MonkeyPatch, chat: _CannedChat, sources_count: int = 3):
    """Patch make_chat AND make_searcher inside search_tool to deterministic doubles.

    Returns the search_tool function ready to call.
    """
    import sys
    import importlib
    # __init__.py shadows the submodule name with the function; bypass via sys.modules.
    importlib.import_module("agent.nodes.search_tool")
    search_tool_mod = sys.modules["agent.nodes.search_tool"]
    from tools.searcher import FakeSearcher

    monkeypatch.setattr(search_tool_mod, "make_chat", lambda mode: chat)
    monkeypatch.setattr(search_tool_mod, "make_searcher", lambda mode: FakeSearcher())
    return search_tool_mod.search_tool


def test_live_report_parses_valid_json(monkeypatch: pytest.MonkeyPatch, isolated_logs: Path) -> None:
    canned = _CannedChat(
        response='{"direct_answer": "X is foo because bar [source 1]. It contrasts with baz [source 2].",'
        ' "key_facts": ['
        '{"claim": "X is foo.", "citations": ["[source 1]"], "confidence": 0.9, "synthesized": false},'
        '{"claim": "X differs from Y.", "citations": ["[source 2]"], "confidence": 0.75, "synthesized": false},'
        '{"claim": "X has gotcha Z.", "citations": ["[source 3]"], "confidence": 0.6, "synthesized": false}'
        '],'
        ' "perspectives": ["Some sources emphasise A; others emphasise B."],'
        ' "unknowns": ["Long-term behaviour is undocumented."],'
        ' "glossary": [{"term": "X", "definition": "the thing", "source_idx": "[source 1]"}]}'
    )
    tid = _thread_id("live-ok")
    search_tool_fn = _patched_search_tool(monkeypatch, canned)
    state = _live_search_state(tid, question="Explain X comprehensively")

    update = search_tool_fn(state)

    assert update["tool_error"] is None
    report = update["research_report"]
    assert report is not None
    assert report["direct_answer"].startswith("X is foo because bar")
    assert len(report["key_facts"]) == 3
    assert report["key_facts"][0]["citations"] == [0]   # [source 1] -> idx 0
    assert report["key_facts"][1]["citations"] == [1]
    assert report["perspectives"] == ["Some sources emphasise A; others emphasise B."]
    assert report["unknowns"] == ["Long-term behaviour is undocumented."]
    assert len(report["glossary"]) == 1
    # response_format was passed through
    assert canned.calls[0]["response_format"] == {"type": "json_object"}
    # No tool_error event was logged
    log_path = isolated_logs / f"run-{tid}.jsonl"
    if log_path.exists():
        content = log_path.read_text()
        assert '"event": "tool_error"' not in content


def test_live_report_logs_on_invalid_json(monkeypatch: pytest.MonkeyPatch, isolated_logs: Path) -> None:
    # LLM returns prose, not JSON
    canned = _CannedChat(response="I'm sorry, I cannot produce JSON. Here's some prose instead about X...")
    tid = _thread_id("live-bad-json")
    search_tool_fn = _patched_search_tool(monkeypatch, canned)
    state = _live_search_state(tid)

    update = search_tool_fn(state)

    # Should silently fall back to offline report (research_report is not None)
    assert update["research_report"] is not None
    # but the fallback reason must be in the log
    log_path = isolated_logs / f"run-{tid}.jsonl"
    assert log_path.exists(), "log file should exist after search_tool ran"
    content = log_path.read_text()
    assert '"event": "tool_error"' in content
    assert "live_report.json_parse_failed" in content
    assert "raw_preview" in content


def test_live_report_logs_on_llm_exception(monkeypatch: pytest.MonkeyPatch, isolated_logs: Path) -> None:
    canned = _CannedChat(raise_exc=RuntimeError("OpenAI chat failed: Unsupported parameter 'max_tokens'"))
    tid = _thread_id("live-llm-err")
    search_tool_fn = _patched_search_tool(monkeypatch, canned)
    state = _live_search_state(tid)

    update = search_tool_fn(state)

    # Offline fallback still produces a report so the rest of the graph keeps working
    assert update["research_report"] is not None
    log_path = isolated_logs / f"run-{tid}.jsonl"
    assert log_path.exists()
    content = log_path.read_text()
    assert '"event": "tool_error"' in content
    assert "live_report.llm_call_failed" in content
    assert "RuntimeError" in content


def test_live_report_logs_on_missing_direct_answer(monkeypatch: pytest.MonkeyPatch, isolated_logs: Path) -> None:
    # Valid JSON but missing required field
    canned = _CannedChat(response='{"key_facts": [{"claim": "x", "citations": []}]}')
    tid = _thread_id("live-bad-schema")
    search_tool_fn = _patched_search_tool(monkeypatch, canned)
    state = _live_search_state(tid)

    update = search_tool_fn(state)

    assert update["research_report"] is not None  # fell back to offline
    log_path = isolated_logs / f"run-{tid}.jsonl"
    assert log_path.exists()
    content = log_path.read_text()
    assert "live_report.schema_validation_failed" in content
    assert "direct_answer=missing" in content
