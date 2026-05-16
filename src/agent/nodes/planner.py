from __future__ import annotations

import re
from typing import Literal, cast

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, Mitigation
from tools import make_chat

_MATH_QUESTION_RE = re.compile(r"[\d\+\-\*\/\(\)\s\.x×÷\^%]+\s*=?\s*$", re.IGNORECASE)
_MATH_SEGMENT_RE = re.compile(r"[\d\+\-\*\/\(\)\s\.x×÷\^%]+", re.IGNORECASE)
_MATH_HINTS = ("calculate", "compute", "how much is", "sum of", "product of")
_OPERATORS = set("+-*/x×÷^%")


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

    decision = "search" if selected_tool == "search" else "calculate"
    update = {
        "attempt": attempt,
        "plan": plan,
        "selected_tool": selected_tool,
        "decision": decision,
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
        },
    )
    return update
