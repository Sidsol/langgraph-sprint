from __future__ import annotations

import json
import re
from typing import Any, cast

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, GlossaryEntry, KeyFact, ResearchReport, SourceRecord, ToolCallRecord, ToolResultRecord
from tools import make_chat, make_searcher
from tools.searcher import domain_of


def _build_legacy_answer(question: str, sources: list[SourceRecord]) -> str:
    if not sources:
        return f"No sources found for '{question}'."
    lead = sources[0]
    source_titles = ", ".join(source["title"] for source in sources)
    return f"For '{question}', the strongest evidence says: {lead['snippet']} Sources: {source_titles}."


def _coerce_sources(results: list[SourceRecord]) -> list[SourceRecord]:
    return [
        {
            "title": str(result["title"]),
            "url": str(result["url"]),
            "snippet": str(result["snippet"]),
        }
        for result in results
    ]


def _sources_by_domain(sources: list[SourceRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        host = domain_of(source["url"]) or "(unknown)"
        counts[host] = counts.get(host, 0) + 1
    return counts


def _offline_direct_answer(question: str, sources: list[SourceRecord], research_plan: list[str], research_depth: str) -> str:
    if not sources:
        return f"No sources found for '{question}'."
    if research_depth == "shallow":
        return _build_legacy_answer(question, sources)
    lead = sources[0]["snippet"]
    follow_up = sources[1]["snippet"] if len(sources) > 1 else "No additional corroborating snippets were retrieved."
    return (
        f"For '{question}', a deep research sweep across {len(research_plan)} sub-queries found that {lead} "
        f"Related evidence also covered {follow_up}"
    )


def _offline_key_facts(sources: list[SourceRecord], *, shallow: bool) -> list[KeyFact]:
    limit = 1 if shallow else 6
    facts: list[KeyFact] = []
    for index, source in enumerate(sources[:limit]):
        snippet_preview = source["snippet"][:40].rstrip(" .") or source["title"]
        facts.append(
            {
                "claim": f"Source {index + 1} mentions {snippet_preview}.",
                "citations": [index],
                "confidence": 0.8,
                "synthesized": False,
            }
        )
    return facts


def _strip_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_citation_indices(raw: object, source_count: int) -> list[int]:
    raw_items = raw if isinstance(raw, list) else [raw]
    citations: list[int] = []
    for item in raw_items:
        matches: list[int] = []
        if isinstance(item, int):
            matches = [item]
        else:
            matches = [int(match) for match in re.findall(r"\[source\s+(\d+)\]", str(item), flags=re.IGNORECASE)]
            if not matches and str(item).strip().isdigit():
                matches = [int(str(item).strip())]
        for match in matches:
            index = match - 1 if 1 <= match <= source_count else match
            if 0 <= index < source_count and index not in citations:
                citations.append(index)
    return citations


def _parse_source_idx(raw: object, source_count: int) -> int | None:
    indices = _parse_citation_indices(raw, source_count)
    return indices[0] if indices else None


def _build_live_report(question: str, sources: list[SourceRecord], research_plan: list[str], research_depth: str) -> ResearchReport | None:
    numbered_sources = "\n\n".join(
        f"[source {index}] {source['title']} — {source['url']}\n{source['snippet']}"
        for index, source in enumerate(sources, start=1)
    )
    prompt = (
        "Produce a structured research report from the numbered sources. Return JSON only with keys "
        "direct_answer, key_facts, perspectives, unknowns, glossary. "
        "direct_answer must be 1-3 sentences. key_facts must be 3-6 objects with keys claim, citations, confidence, synthesized. "
        "Use explicit '[source N]' citation markers inside the citations field. perspectives and unknowns should each contain at most 3 strings. "
        "glossary should contain objects with keys term, definition, and source_idx (use '[source N]' or null).\n\n"
        f"Question: {question}\n"
        f"Research depth: {research_depth}\n"
        f"Sub-queries: {json.dumps(research_plan)}\n\n"
        f"Sources:\n{numbered_sources}"
    )
    try:
        raw = make_chat("live").complete(
            prompt,
            system="You synthesize grounded research reports and respond with JSON only.",
            max_tokens=900,
        )
        payload = json.loads(_strip_fences(raw))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    direct_answer = str(payload.get("direct_answer") or "").strip()
    key_facts_payload = payload.get("key_facts")
    if not direct_answer or not isinstance(key_facts_payload, list):
        return None

    key_facts: list[KeyFact] = []
    for item in key_facts_payload[:6]:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        key_facts.append(
            {
                "claim": claim,
                "citations": _parse_citation_indices(item.get("citations") or item.get("citation_markers") or [], len(sources)),
                "confidence": max(0.0, min(1.0, confidence)),
                "synthesized": bool(item.get("synthesized", False)),
            }
        )

    if not key_facts:
        return None

    perspectives = [str(item).strip() for item in payload.get("perspectives", []) if str(item).strip()][:3]
    unknowns = [str(item).strip() for item in payload.get("unknowns", []) if str(item).strip()][:3]

    glossary: list[GlossaryEntry] = []
    for item in payload.get("glossary", []):
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        definition = str(item.get("definition") or "").strip()
        if not term or not definition:
            continue
        glossary.append(
            {
                "term": term,
                "definition": definition,
                "source_idx": _parse_source_idx(item.get("source_idx") or item.get("source") or item.get("citation"), len(sources)),
            }
        )

    return {
        "direct_answer": direct_answer,
        "key_facts": key_facts,
        "perspectives": perspectives,
        "unknowns": unknowns,
        "glossary": glossary,
        "sources_by_domain": _sources_by_domain(sources),
        "sub_queries_run": list(research_plan),
    }


def _offline_report(
    question: str,
    sources: list[SourceRecord],
    research_plan: list[str],
    research_depth: str,
    mode: str,
) -> ResearchReport:
    shallow = research_depth == "shallow"
    perspectives = [] if "FORCE_PERSPECTIVES" not in question else ["Perspective A: <stub>", "Perspective B: <stub>"]
    if shallow:
        perspectives = []
    unknowns = [] if shallow or mode != "offline" else ["Source diversity limited to fake-search results."]
    return {
        "direct_answer": _offline_direct_answer(question, sources, research_plan, research_depth),
        "key_facts": _offline_key_facts(sources, shallow=shallow),
        "perspectives": perspectives[:3],
        "unknowns": unknowns[:3],
        "glossary": [],
        "sources_by_domain": _sources_by_domain(sources),
        "sub_queries_run": list(research_plan),
    }


def _build_report(state: AgentState, sources: list[SourceRecord], research_plan: list[str], research_depth: str) -> ResearchReport:
    if state["mode"] == "live":
        live_report = _build_live_report(state["question"], sources, research_plan, research_depth)
        if live_report is not None:
            return live_report
    return _offline_report(state["question"], sources, research_plan, research_depth, state["mode"])


def search_tool(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"]
    question = state["question"]
    research_plan = list(state.get("research_plan") or [question])
    research_depth = cast(str, state.get("research_depth", "shallow"))
    write_event(
        state["thread_id"],
        attempt,
        "search_tool",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={"question": question, "plan": state["plan"], "research_plan": research_plan},
    )

    tool_call: ToolCallRecord = {
        "tool": "search",
        "input": question,
        "attempt": attempt,
        "mode": state["mode"],
    }

    try:
        results = make_searcher(state["mode"]).multi_search(research_plan, max_per_query=3)
        if not results:
            raise RuntimeError("search returned no results")

        sources = _coerce_sources(results)
        if not sources:
            raise RuntimeError("search returned no normalized sources")
        report = _build_report(state, sources, research_plan, research_depth)
        confidence = 0.85 if state["mode"] == "offline" else 0.8
        tool_result: ToolResultRecord = {
            "tool": "search",
            "ok": True,
            "summary": f"Retrieved {len(sources)} search result(s) across {len(research_plan)} sub-query/queries.",
            "error": None,
        }
        update: dict[str, Any] = {
            "sources": sources,
            "research_report": report,
            "draft_answer": report["direct_answer"],
            "confidence": confidence,
            "tool_calls": [tool_call],
            "tool_results": [tool_result],
            "tool_error": None,
        }
    except Exception as exc:
        error = str(exc)
        tool_result = {
            "tool": "search",
            "ok": False,
            "summary": "Search execution failed.",
            "error": error,
        }
        update = {
            "sources": [],
            "research_report": None,
            "draft_answer": "",
            "confidence": 0.0,
            "tool_calls": [tool_call],
            "tool_results": [tool_result],
            "tool_error": error,
        }

    write_event(
        state["thread_id"],
        attempt,
        "search_tool",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff={
            "sources": len(update["sources"]),
            "confidence": update["confidence"],
            "tool_error": update["tool_error"],
            "research_report": bool(update.get("research_report")),
        },
    )
    return update
