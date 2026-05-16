from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

EVENT_NODE_ENTER = "node_enter"
EVENT_NODE_EXIT = "node_exit"
EVENT_BRANCH_DECISION = "branch_decision"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_TOOL_ERROR = "tool_error"
EVENT_RETRY = "retry"
EVENT_INTERRUPT_EMITTED = "interrupt_emitted"
EVENT_INTERRUPT_RESUMED = "interrupt_resumed"
EVENT_PUBLISH = "publish"
EVENT_ESCALATE = "escalate"
EVENT_END = "end"

_ALLOWED_EVENTS: Final[frozenset[str]] = frozenset(
    {
        EVENT_NODE_ENTER,
        EVENT_NODE_EXIT,
        EVENT_BRANCH_DECISION,
        EVENT_TOOL_CALL,
        EVENT_TOOL_RESULT,
        EVENT_TOOL_ERROR,
        EVENT_RETRY,
        EVENT_INTERRUPT_EMITTED,
        EVENT_INTERRUPT_RESUMED,
        EVENT_PUBLISH,
        EVENT_ESCALATE,
        EVENT_END,
    }
)

LOGS_DIR = Path("logs")


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def write_event(thread_id: str, attempt: int, node: str, event: str, mode: str, **extra: object) -> None:
    if event not in _ALLOWED_EVENTS:
        raise ValueError(f"unsupported event: {event}")

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "thread_id": thread_id,
        "attempt": attempt,
        "node": node,
        "event": event,
        "mode": mode,
        **extra,
    }

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"run-{thread_id}.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
        handle.flush()


__all__ = [
    "EVENT_BRANCH_DECISION",
    "EVENT_END",
    "EVENT_ESCALATE",
    "EVENT_INTERRUPT_EMITTED",
    "EVENT_INTERRUPT_RESUMED",
    "EVENT_NODE_ENTER",
    "EVENT_NODE_EXIT",
    "EVENT_PUBLISH",
    "EVENT_RETRY",
    "EVENT_TOOL_CALL",
    "EVENT_TOOL_ERROR",
    "EVENT_TOOL_RESULT",
    "LOGS_DIR",
    "write_event",
]
