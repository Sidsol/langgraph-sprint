from __future__ import annotations

import re

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, ToolCallRecord, ToolResultRecord
from tools import safe_calc

_BINARY_PATTERNS = (
    (re.compile(r"sum of\s+(?P<a>-?\d+(?:\.\d+)?)\s+and\s+(?P<b>-?\d+(?:\.\d+)?)", re.IGNORECASE), "+"),
    (re.compile(r"product of\s+(?P<a>-?\d+(?:\.\d+)?)\s+and\s+(?P<b>-?\d+(?:\.\d+)?)", re.IGNORECASE), "*"),
)
_PREFIX_RE = re.compile(r"\b(?:what is|calculate|compute|how much is)\b", re.IGNORECASE)
_EXPRESSION_RE = re.compile(r"[\d\+\-\*\/\(\)\s\.x×÷\^%]+")


def _extract_expression(question: str) -> str:
    for pattern, operator in _BINARY_PATTERNS:
        match = pattern.search(question)
        if match:
            return f"{match.group('a')}{operator}{match.group('b')}"

    scrubbed = _PREFIX_RE.sub(" ", question)
    candidates = [segment.strip() for segment in _EXPRESSION_RE.findall(scrubbed) if any(char.isdigit() for char in segment)]
    if not candidates:
        raise ValueError("could not extract arithmetic expression")

    expression = max(candidates, key=len)
    expression = expression.replace("×", "*").replace("÷", "/").replace("^", "**")
    expression = expression.replace("x", "*").replace("X", "*")
    expression = re.sub(r"\s+", "", expression).rstrip("=?")
    if not expression:
        raise ValueError("could not extract arithmetic expression")
    return expression


def _format_value(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, "g")


def calculator_tool(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"]
    question = state["question"]
    write_event(
        state["thread_id"],
        attempt,
        "calculator_tool",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={"question": question, "plan": state["plan"]},
    )

    try:
        expression = _extract_expression(question)
    except ValueError as exc:
        expression = question.strip()
        error = str(exc)
        tool_call: ToolCallRecord = {
            "tool": "calculator",
            "input": expression,
            "attempt": attempt,
            "mode": state["mode"],
        }
        tool_result: ToolResultRecord = {
            "tool": "calculator",
            "ok": False,
            "summary": "Calculator expression extraction failed.",
            "error": error,
        }
        update = {
            "sources": [],
            "draft_answer": "",
            "confidence": 0.0,
            "tool_calls": [tool_call],
            "tool_results": [tool_result],
            "tool_error": error,
        }
    else:
        tool_call = {
            "tool": "calculator",
            "input": expression,
            "attempt": attempt,
            "mode": state["mode"],
        }
        try:
            value = safe_calc(expression)
        except ValueError as exc:
            error = str(exc)
            tool_result = {
                "tool": "calculator",
                "ok": False,
                "summary": f"Calculator failed for '{expression}'.",
                "error": error,
            }
            update = {
                "sources": [],
                "draft_answer": "",
                "confidence": 0.0,
                "tool_calls": [tool_call],
                "tool_results": [tool_result],
                "tool_error": error,
            }
        else:
            value_text = _format_value(value)
            tool_result = {
                "tool": "calculator",
                "ok": True,
                "summary": f"Calculated {expression} = {value_text}.",
                "error": None,
            }
            update = {
                "draft_answer": f"{expression} = {value_text}",
                "sources": [],
                "confidence": 0.95,
                "tool_calls": [tool_call],
                "tool_results": [tool_result],
                "tool_error": None,
            }

    write_event(
        state["thread_id"],
        attempt,
        "calculator_tool",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff={
            "draft_answer": update["draft_answer"],
            "confidence": update["confidence"],
            "tool_error": update["tool_error"],
        },
    )
    return update
