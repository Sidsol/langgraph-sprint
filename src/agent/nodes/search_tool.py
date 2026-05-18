from __future__ import annotations

import json
import re
from typing import Any, cast

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, EVENT_TOOL_ERROR, write_event
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


def _build_live_report(
    question: str,
    sources: list[SourceRecord],
    research_plan: list[str],
    research_depth: str,
    *,
    thread_id: str,
    attempt: int,
    mode: str,
) -> ResearchReport | None:
    numbered_sources = "\n\n".join(
        f"[source {index}] {source['title']} — {source['url']}\n{source['snippet']}"
        for index, source in enumerate(sources, start=1)
    )

    # Scale length expectations with research_depth — shallow questions want concise answers,
    # deep questions want a thorough synthesis with paragraph structure.
    if research_depth == "deep":
        answer_length_rule = (
            "3-6 well-developed paragraphs (target 300-600 words). Use blank lines between paragraphs (\\n\\n). "
            "Organise the answer into a logical flow: (a) a 1-2 sentence direct response, (b) the core "
            "mechanisms or reasons backed by sources, (c) important nuances, tradeoffs, or competing "
            "considerations, (d) historical context or examples if relevant, and (e) practical implications."
        )
        key_facts_rule = "5-7 distinct claims"
        glossary_rule = "up to 8 domain terms"
        perspectives_rule = "up to 4 strings"
        unknowns_rule = "up to 4 explicit limitations or gaps"
        example_direct_answer = (
            "<3-6 paragraphs of substantive synthesis (300-600 words) with [source N] citations inline. "
            "Use \\n\\n between paragraphs. Cover mechanisms, nuances, examples, and implications.>"
        )
    else:
        answer_length_rule = (
            "2-4 substantive sentences directly addressing the question. "
            "Synthesise across sources. Cite inline as [source N]."
        )
        key_facts_rule = "3-5 distinct claims"
        glossary_rule = "up to 5 domain terms"
        perspectives_rule = "up to 2 strings"
        unknowns_rule = "up to 2 explicit limitations or gaps"
        example_direct_answer = "<2-4 sentences synthesising the answer, citing [source N] inline>"

    schema_example = (
        '{\n'
        f'  "direct_answer": "{example_direct_answer}",\n'
        '  "key_facts": [\n'
        '    {"claim": "<one factual sentence>", "citations": ["[source 1]", "[source 3]"], "confidence": 0.85, "synthesized": false},\n'
        '    {"claim": "<another fact>", "citations": ["[source 2]"], "confidence": 0.7, "synthesized": false}\n'
        '  ],\n'
        '  "perspectives": ["<divergent viewpoint, if any>"],\n'
        '  "unknowns": ["<explicit limitation or gap>"],\n'
        '  "glossary": [{"term": "<term>", "definition": "<def>", "source_idx": "[source 2]"}]\n'
        '}'
    )
    prompt = (
        "You are producing a structured research report from numbered sources. "
        "Return ONLY a single JSON object matching this schema (no prose, no markdown fences):\n\n"
        f"{schema_example}\n\n"
        "Rules:\n"
        f"- direct_answer: {answer_length_rule}\n"
        f"- key_facts: {key_facts_rule}. Each claim is one sentence. Each citations entry is a list of '[source N]' markers (use only source indices that actually support the claim).\n"
        "- Mark synthesized=true ONLY for claims that are background knowledge not directly supported by any cited source.\n"
        f"- perspectives: {perspectives_rule}, only if sources actually disagree.\n"
        f"- unknowns: {unknowns_rule} in the evidence.\n"
        f"- glossary: {glossary_rule} that appear in the answer; definitions must be grounded in sources.\n"
        "- Confidence values are floats in [0.0, 1.0].\n\n"
        f"Question: {question}\n"
        f"Research depth: {research_depth}\n"
        f"Sub-queries run: {json.dumps(research_plan)}\n\n"
        f"Sources ({len(sources)} total):\n{numbered_sources}\n\n"
        "Return ONLY the JSON object. JSON strings must use \\n\\n for paragraph breaks within direct_answer."
    )

    # Stage 1 — LLM call
    raw: str = ""
    try:
        raw = make_chat("live").complete(
            prompt,
            system="You synthesise grounded research reports. Respond with a single JSON object only — no prose, no markdown fences.",
            max_tokens=6000 if research_depth == "deep" else 3000,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        write_event(
            thread_id,
            attempt,
            "search_tool",
            EVENT_TOOL_ERROR,
            mode,
            error=f"live_report.llm_call_failed: {type(exc).__name__}: {str(exc)[:300]}",
        )
        return None

    raw_preview = (raw or "")[:300]

    # Stage 2 — JSON parse
    try:
        payload = json.loads(_strip_fences(raw))
    except Exception as exc:
        write_event(
            thread_id,
            attempt,
            "search_tool",
            EVENT_TOOL_ERROR,
            mode,
            error=f"live_report.json_parse_failed: {type(exc).__name__}: {str(exc)[:200]}",
            state_diff={"raw_preview": raw_preview, "raw_len": len(raw or "")},
        )
        return None

    # Stage 3 — schema validation
    if not isinstance(payload, dict):
        write_event(
            thread_id,
            attempt,
            "search_tool",
            EVENT_TOOL_ERROR,
            mode,
            error="live_report.schema_validation_failed: payload_not_dict",
            state_diff={"raw_preview": raw_preview, "type": type(payload).__name__},
        )
        return None

    direct_answer = str(payload.get("direct_answer") or "").strip()
    key_facts_payload = payload.get("key_facts")
    if not direct_answer or not isinstance(key_facts_payload, list):
        write_event(
            thread_id,
            attempt,
            "search_tool",
            EVENT_TOOL_ERROR,
            mode,
            error=(
                "live_report.schema_validation_failed: "
                f"direct_answer={'present' if direct_answer else 'missing'}, "
                f"key_facts={'list' if isinstance(key_facts_payload, list) else type(key_facts_payload).__name__}"
            ),
            state_diff={"raw_preview": raw_preview},
        )
        return None

    key_facts: list[KeyFact] = []
    for item in key_facts_payload[:7]:
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
        write_event(
            thread_id,
            attempt,
            "search_tool",
            EVENT_TOOL_ERROR,
            mode,
            error="live_report.schema_validation_failed: no_valid_key_facts",
            state_diff={"raw_preview": raw_preview, "raw_count": len(key_facts_payload)},
        )
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
        live_report = _build_live_report(
            state["question"],
            sources,
            research_plan,
            research_depth,
            thread_id=state["thread_id"],
            attempt=state["attempt"],
            mode=state["mode"],
        )
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
