from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


# Closed enum of mitigation strategies recorded for each retry, satisfying vision §5
# "logged mitigation strategy" requirement and SM-03 "recorded reason, mitigation,
# and retry count".
Mitigation = Literal[
    "revised_query",         # planner rewrites the search query before the retry (weak citation)
    "switched_tool",         # planner selects the other tool (search<->calculator) on retry when tool_error blocks the chosen tool
    "added_context",         # planner adds prior tool results to the retry attempt's prompt (low confidence on calculator path)
    "escalated_to_human",    # terminal: budget exhausted with unsafe_to_publish == True
    "fell_back",             # terminal: budget exhausted with a safe bounded answer available
    "none",                  # first attempt or no mitigation applicable
]


class SourceRecord(TypedDict):
    title: str
    url: str
    snippet: str


class ToolCallRecord(TypedDict):
    tool: Literal["search", "calculator"]
    input: str
    attempt: int
    mode: Literal["live", "offline"]


class ToolResultRecord(TypedDict):
    tool: Literal["search", "calculator"]
    ok: bool
    summary: str
    error: str | None


class CitationVerdict(TypedDict):
    status: Literal["grounded", "weak", "not_applicable"]
    confidence: float
    notes: list[str]


class EvaluatorVerdict(TypedDict):
    status: Literal["pass", "retry", "fallback", "escalate"]
    score: float
    reason: str


class RetryLogEntry(TypedDict):
    attempt: int            # the attempt number that just FAILED (i.e., the one being retried away from)
    reason: str             # human-readable explanation, e.g. "citation_verdict weak (confidence 0.42)"
    mitigation: Mitigation  # closed-enum strategy applied for the next attempt or terminal route


class AgentState(TypedDict):
    thread_id: str
    question: str
    plan: str
    selected_tool: Literal["search", "calculator"] | None
    draft_answer: str
    edited_text: str | None
    sources: list[SourceRecord]
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls: Annotated[list[ToolCallRecord], add]
    tool_results: Annotated[list[ToolResultRecord], add]
    evaluator_verdict: EvaluatorVerdict | None
    evaluator_history: Annotated[list[EvaluatorVerdict], add]
    citation_verdict: CitationVerdict | None
    attempt: int
    max_attempts: int
    retry_log: Annotated[list[RetryLogEntry], add]   # structured: {attempt, reason, mitigation}
    confidence: float
    decision: Literal["search", "calculate", "publish", "retry", "fallback", "escalate", "end"]
    human_decision: Literal["pending", "approved", "rejected", "edited", "acknowledged"]
    unsafe_to_publish: bool       # set by evaluator from citation_verdict + tool_error; consumed by route_after_evaluator
    published_path: str | None
    mode: Literal["live", "offline"]
    tool_error: str | None


def initial_state(question: str, thread_id: str, mode: Literal["live", "offline"]) -> AgentState:
    return {
        "thread_id": thread_id,
        "question": question,
        "plan": "",
        "selected_tool": None,
        "draft_answer": "",
        "edited_text": None,
        "sources": [],
        "messages": [],
        "tool_calls": [],
        "tool_results": [],
        "evaluator_verdict": None,
        "evaluator_history": [],
        "citation_verdict": None,
        "attempt": 0,
        "max_attempts": 2,
        "retry_log": [],
        "confidence": 0.0,
        "decision": "end",
        "human_decision": "pending",
        "unsafe_to_publish": False,
        "published_path": None,
        "mode": mode,
        "tool_error": None,
    }
