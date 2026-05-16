from __future__ import annotations

from typing import Literal

from .graph import build_graph, derive_thread_id, make_checkpointer, resume_pause
from .state import AgentState, initial_state


def make_initial_state(question: str, thread_id: str, mode: Literal["live", "offline"]) -> AgentState:
    return initial_state(question=question, thread_id=thread_id, mode=mode)


__all__ = [
    "AgentState",
    "build_graph",
    "derive_thread_id",
    "make_checkpointer",
    "make_initial_state",
    "resume_pause",
]
