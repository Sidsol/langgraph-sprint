from __future__ import annotations

from typing import Literal

from agent.logging import EVENT_BRANCH_DECISION, write_event
from agent.state import AgentState

PlannerRoute = Literal["search_tool", "calculator_tool", "fallback"]
EvaluatorRoute = Literal["END_PROVISIONAL", "planner", "fallback", "escalate_to_human"]
HitlRoute = Literal["publisher", "END"]


def route_planner_output(state: AgentState) -> PlannerRoute:
    if state["selected_tool"] == "search":
        branch: PlannerRoute = "search_tool"
    elif state["selected_tool"] == "calculator":
        branch = "calculator_tool"
    else:
        branch = "fallback"

    write_event(
        state["thread_id"],
        state["attempt"],
        "tool_router",
        EVENT_BRANCH_DECISION,
        state["mode"],
        branch=branch,
        state_diff={"selected_tool": state["selected_tool"], "decision": state["decision"]},
    )
    return branch


def route_after_evaluator(state: AgentState) -> EvaluatorRoute:
    verdict = state["evaluator_verdict"] or {"status": "fallback"}
    verdict_status = verdict["status"]

    if verdict_status == "pass" and not state["unsafe_to_publish"]:
        branch: EvaluatorRoute = "END_PROVISIONAL"
    elif verdict_status == "retry" and state["attempt"] < state["max_attempts"]:
        branch = "planner"
    elif (verdict_status == "escalate" or state["attempt"] >= state["max_attempts"]) and state["unsafe_to_publish"]:
        branch = "escalate_to_human"
    else:
        branch = "fallback"

    write_event(
        state["thread_id"],
        state["attempt"],
        "evaluator_router",
        EVENT_BRANCH_DECISION,
        state["mode"],
        branch=branch,
        state_diff={
            "verdict_status": verdict_status,
            "unsafe_to_publish": state["unsafe_to_publish"],
            "attempt": state["attempt"],
            "max_attempts": state["max_attempts"],
        },
    )
    return branch


def route_after_hitl(state: AgentState) -> HitlRoute:
    branch: HitlRoute = "publisher" if state["human_decision"] in {"approved", "edited"} else "END"
    write_event(
        state["thread_id"],
        state["attempt"],
        "hitl_router",
        EVENT_BRANCH_DECISION,
        state["mode"],
        branch=branch,
        state_diff={"human_decision": state["human_decision"], "edited_text": state["edited_text"]},
    )
    return branch


__all__ = ["route_after_evaluator", "route_after_hitl", "route_planner_output"]
