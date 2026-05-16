from __future__ import annotations

from agent.logging import EVENT_NODE_ENTER, EVENT_NODE_EXIT, write_event
from agent.state import AgentState, EvaluatorVerdict


def evaluator(state: AgentState) -> dict[str, object]:
    attempt = state["attempt"]
    write_event(
        state["thread_id"],
        attempt,
        "evaluator",
        EVENT_NODE_ENTER,
        state["mode"],
        state_diff={
            "draft_answer": bool(state["draft_answer"]),
            "tool_error": state["tool_error"],
            "citation_verdict": state["citation_verdict"],
        },
    )

    if state["tool_error"]:
        verdict: EvaluatorVerdict = {
            "status": "escalate",
            "score": 0.0,
            "reason": f"Tool execution failed: {state['tool_error']}",
        }
        decision = "escalate"
        unsafe_to_publish = True
    else:
        citation_status = state["citation_verdict"]["status"] if state["citation_verdict"] else "not_applicable"
        score = state["confidence"] if state["confidence"] > 0 else 1.0
        verdict = {
            "status": "pass",
            "score": score,
            "reason": f"Draft answer is available with citation status '{citation_status}'.",
        }
        decision = "publish"
        unsafe_to_publish = False

    write_event(
        state["thread_id"],
        attempt,
        "evaluator",
        EVENT_NODE_EXIT,
        state["mode"],
        state_diff={"evaluator_verdict": verdict, "decision": decision, "unsafe_to_publish": unsafe_to_publish},
    )
    return {
        "evaluator_verdict": verdict,
        "evaluator_history": [verdict],
        "decision": decision,
        "unsafe_to_publish": unsafe_to_publish,
    }
