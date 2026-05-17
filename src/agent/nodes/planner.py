from __future__ import annotations

import json
import re
from typing import Literal, cast

from agent.logging import EVENT_BRANCH_DECISION, EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, Mitigation
from tools import make_chat

_MATH_QUESTION_RE = re.compile(r"[\d\+\-\*\/\(\)\s\.x×÷\^%]+\s*=?\s*$", re.IGNORECASE)
_MATH_SEGMENT_RE = re.compile(r"[\d\+\-\*\/\(\)\s\.x×÷\^%]+", re.IGNORECASE)
_MATH_HINTS = ("calculate", "compute", "how much is", "sum of", "product of")
_OPERATORS = set("+-*/x×÷^%")
_QUERY_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*")
_DEEP_HINTS = (
    "compare",
    " vs ",
    "versus",
    "tradeoff",
    "pros and cons",
    "how does",
    "explain",
    "differences between",
    "overview of",
    "survey",
)
_DEEP_FORCE_MARKERS = ("force_deep", "force_retry")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "between",
    "by",
    "compare",
    "cons",
    "differences",
    "does",
    "explain",
    "for",
    "from",
    "how",
    "in",
    "is",
    "me",
    "of",
    "on",
    "or",
    "overview",
    "pros",
    "survey",
    "tell",
    "the",
    "this",
    "to",
    "tradeoff",
    "versus",
    "vs",
    "what",
}


def _select_tool(question: str) -> Literal["search", "calculator"]:
    normalized = question.strip().rstrip("?!=").strip()
    lower_question = normalized.lower()
    if _MATH_QUESTION_RE.fullmatch(normalized) and any(char.isdigit() for char in normalized):
        return "calculator"
    if any(hint in lower_question for hint in _MATH_HINTS):
        return "calculator"

    for segment in _MATH_SEGMENT_RE.findall(normalized):
        compact = segment.strip()
        if any(char.isdigit() for char in compact) and any(operator in compact for operator in _OPERATORS):
            return "calculator"

    return "search"


def _latest_mitigation(state: AgentState) -> Mitigation:
    if state["attempt"] >= 1 and state["retry_log"]:
        return cast(Mitigation, state["retry_log"][-1]["mitigation"])
    return "none"


def _flip_tool(selected_tool: Literal["search", "calculator"]) -> Literal["search", "calculator"]:
    return "calculator" if selected_tool == "search" else "search"


def _offline_plan(
    selected_tool: Literal["search", "calculator"],
    question: str,
    mitigation: Mitigation,
    prior_tool_summary: str | None,
) -> str:
    if selected_tool == "calculator":
        plan = f"Use the calculator tool to solve the arithmetic request: {question.strip()}"
    else:
        plan = f"Use the search tool to gather evidence for: {question.strip()}"

    if mitigation == "revised_query":
        return f"Revised query: {plan}"
    if mitigation == "added_context" and prior_tool_summary:
        return f"{plan} Prior tool context: {prior_tool_summary}"
    return plan


def _word_count(question: str) -> int:
    return len(_QUERY_TOKEN_RE.findall(question))


def _research_depth(question: str) -> Literal["shallow", "deep"]:
    lower_question = f" {question.lower()} "
    if any(marker in lower_question for marker in _DEEP_FORCE_MARKERS):
        return "deep"
    if any(hint in lower_question for hint in _DEEP_HINTS):
        return "deep"
    return "deep" if _word_count(question) > 10 else "shallow"


def _topic_from_question(question: str) -> str:
    tokens = [
        token
        for token in _QUERY_TOKEN_RE.findall(question.lower())
        if token not in _STOPWORDS and not token.startswith("force_")
    ]
    return " ".join(tokens) or question.strip()


def _longest_noun_like_span(question: str) -> str | None:
    spans: list[str] = []
    current: list[str] = []
    for token in _QUERY_TOKEN_RE.findall(question):
        normalized = token.lower()
        if normalized in _STOPWORDS or normalized.startswith("force_"):
            if current:
                spans.append(" ".join(current))
                current = []
            continue
        current.append(token)
    if current:
        spans.append(" ".join(current))
    if not spans:
        return None
    spans.sort(key=lambda span: (len(span.split()), len(span)), reverse=True)
    return spans[0]


def _dedupe_queries(queries: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = re.sub(r"\s+", " ", query).strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _offline_research_plan(question: str) -> list[str]:
    topic = _topic_from_question(question)
    plan = [
        question.strip(),
        f"reference architectures for {topic}",
        f"common failure modes in {topic}",
        f"prior art and competing approaches for {topic}",
    ]
    noun_phrase = _longest_noun_like_span(question)
    if noun_phrase:
        plan.append(f"{noun_phrase} glossary terminology")
    return _dedupe_queries(plan)[:5]


def _parse_sub_queries(raw: str) -> list[str] | None:
    candidates = [raw.strip()]
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        candidates.append(cleaned.strip())

    array_match = re.search(r"\[[\s\S]*\]", raw)
    if array_match:
        candidates.append(array_match.group(0))

    dict_match = re.search(r"\{[\s\S]*\}", raw)
    if dict_match:
        candidates.append(dict_match.group(0))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            queries = [str(item).strip() for item in payload if str(item).strip()]
            return queries or None
        if isinstance(payload, dict) and isinstance(payload.get("queries"), list):
            queries = [str(item).strip() for item in payload["queries"] if str(item).strip()]
            return queries or None
    return None


def _live_research_plan(question: str) -> list[str]:
    prompt = (
        "Decompose the question into 3-5 distinct web-search queries that together cover the topic comprehensively. "
        "Return JSON only as an array of strings. Keep the queries concise and non-overlapping.\n\n"
        f"Question: {question}"
    )
    try:
        raw = make_chat("live").complete(
            prompt,
            system="You plan structured research by returning only JSON arrays of search queries.",
            max_tokens=200,
        )
    except Exception:
        return _offline_research_plan(question)

    parsed = _parse_sub_queries(raw)
    if not parsed:
        return _offline_research_plan(question)

    deduped = _dedupe_queries(parsed)
    if len(deduped) < 3:
        return _offline_research_plan(question)
    return deduped[:5]


def planner(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"] + 1
    retry_mitigation = _latest_mitigation(state)
    selected_tool = _select_tool(state["question"])
    if retry_mitigation == "switched_tool":
        selected_tool = _flip_tool(selected_tool)

    prior_tool_summary = state["tool_results"][-1]["summary"] if state["tool_results"] else None

    write_event(
        state["thread_id"],
        attempt,
        "planner",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={"question": state["question"], "retry_mitigation": retry_mitigation},
    )

    if state["mode"] == "offline":
        plan = _offline_plan(selected_tool, state["question"], retry_mitigation, prior_tool_summary)
    else:
        prompt = (
            "Write one short execution plan sentence for this question. "
            f"Question: {state['question']} Selected tool: {selected_tool}."
        )
        if retry_mitigation == "added_context" and prior_tool_summary:
            prompt += f" Prior tool context: {prior_tool_summary}."
        plan = make_chat("live").complete(
            prompt,
            system="You write concise one-line execution plans for a LangGraph agent.",
            max_tokens=40,
        ).strip()
        plan = plan.splitlines()[0] if plan else f"Use the {selected_tool} tool."
        if retry_mitigation == "revised_query":
            plan = f"Revised query: {plan}"
        elif retry_mitigation == "added_context" and prior_tool_summary:
            plan = f"{plan} Prior tool context: {prior_tool_summary}"

    if selected_tool == "search":
        research_depth = _research_depth(state["question"])
        research_plan = (
            _live_research_plan(state["question"])
            if research_depth == "deep" and state["mode"] == "live"
            else _offline_research_plan(state["question"])
            if research_depth == "deep"
            else [state["question"]]
        )
    else:
        research_depth = "shallow"
        research_plan = []

    write_event(
        state["thread_id"],
        attempt,
        "planner",
        EVENT_BRANCH_DECISION,
        state["mode"],
        branch=research_depth,
        state_diff={"research_plan": research_plan},
    )

    decision = "search" if selected_tool == "search" else "calculate"
    update = {
        "attempt": attempt,
        "plan": plan,
        "selected_tool": selected_tool,
        "decision": decision,
        "research_depth": research_depth,
        "research_plan": research_plan,
        "tool_error": None,
    }

    write_event(
        state["thread_id"],
        attempt,
        "planner",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff={
            "plan": plan,
            "selected_tool": selected_tool,
            "decision": decision,
            "retry_mitigation": retry_mitigation,
            "research_depth": research_depth,
            "research_plan": research_plan,
        },
    )
    return update
