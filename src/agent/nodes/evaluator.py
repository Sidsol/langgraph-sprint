from __future__ import annotations

from typing import cast

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, EVENT_RETRY, write_event
from agent.state import AgentState, CitationVerdict, EvaluatorVerdict, Mitigation, RetryLogEntry


def _citation_verdict(state: AgentState) -> CitationVerdict:
    return cast(
        CitationVerdict,
        state["citation_verdict"]
        or {"status": "not_applicable", "confidence": 1.0, "notes": []},
    )


def _build_reason(
    state: AgentState,
    citation_status: str,
    citation_confidence: float,
    verdict_status: str,
) -> str:
    if state["tool_error"]:
        return f"tool_error present: {state['tool_error']}"
    if citation_status == "weak":
        return f"citation_verdict weak (confidence {citation_confidence:.2f})"
    if citation_confidence < 0.70:
        return f"citation_verdict confidence {citation_confidence:.2f} below threshold"
    if state["confidence"] < 0.50:
        return f"answer confidence {state['confidence']:.2f} below threshold"
    if verdict_status == "pass":
        return f"draft answer is publishable with citation status '{citation_status}'"
    return f"routing to {verdict_status} with citation status '{citation_status}'"


def _select_mitigation(
    state: AgentState,
    decision: str,
    citation_status: str,
    citation_confidence: float,
    unsafe_to_publish: bool,
) -> Mitigation:
    if decision == "retry" and state["attempt"] < state["max_attempts"]:
        if citation_status == "weak" or citation_confidence < 0.70:
            return "revised_query"
        if state["tool_error"]:
            return "switched_tool"
        if state["selected_tool"] == "calculator" and citation_status == "not_applicable" and state["confidence"] < 0.75:
            return "added_context"
        return "revised_query"
    return "escalated_to_human" if unsafe_to_publish else "fell_back"


def evaluator(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"]
    citation_verdict = _citation_verdict(state)
    citation_status = citation_verdict["status"]
    citation_confidence = citation_verdict["confidence"]

    write_event(
        state["thread_id"],
        attempt,
        "evaluator",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={
            "draft_answer": bool(state["draft_answer"]),
            "tool_error": state["tool_error"],
            "citation_verdict": citation_verdict,
        },
    )

    unsafe_to_publish = (
        (citation_status == "weak" and citation_confidence < 0.70)
        or bool(state["tool_error"])
        or state["confidence"] < 0.50
    )
    score = min(state["confidence"], citation_confidence) if state["confidence"] > 0 else citation_confidence

    if not unsafe_to_publish and citation_status in {"grounded", "not_applicable"}:
        verdict_status = "pass"
        decision = "publish"
    elif unsafe_to_publish and attempt < state["max_attempts"]:
        verdict_status = "retry"
        decision = "retry"
    elif unsafe_to_publish and attempt >= state["max_attempts"]:
        verdict_status = "escalate"
        decision = "escalate"
    else:
        verdict_status = "fallback"
        decision = "fallback"

    reason = _build_reason(state, citation_status, citation_confidence, verdict_status)
    verdict: EvaluatorVerdict = {
        "status": cast(str, verdict_status),
        "score": score,
        "reason": reason,
    }

    update: dict[str, object] = {
        "evaluator_verdict": verdict,
        "evaluator_history": [verdict],
        "decision": decision,
        "unsafe_to_publish": unsafe_to_publish,
    }
    retry_log_state = state["retry_log"]
    if verdict_status in {"retry", "fallback", "escalate"}:
        mitigation = _select_mitigation(state, decision, citation_status, citation_confidence, unsafe_to_publish)
        retry_entry: RetryLogEntry = {
            "attempt": attempt,
            "reason": reason,
            "mitigation": mitigation,
        }
        retry_log_state = [*state["retry_log"], retry_entry]
        update["retry_log"] = [retry_entry]
        write_event(
            state["thread_id"],
            attempt,
            "evaluator",
            EVENT_RETRY,
            state["mode"],
            decision=decision,
            reason=reason,
            mitigation=mitigation,
            state_diff={"retry_log": retry_log_state},
        )

    write_event(
        state["thread_id"],
        attempt,
        "evaluator",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff={
            "evaluator_verdict": verdict,
            "decision": decision,
            "unsafe_to_publish": unsafe_to_publish,
            "retry_log": retry_log_state,
        },
    )
    return update
