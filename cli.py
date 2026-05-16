from __future__ import annotations

import argparse
import os
from typing import Any

from dotenv import load_dotenv
from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agent import build_graph, derive_thread_id, make_initial_state

console = Console()


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _extract_interrupt_payload(result: dict[str, Any], graph: Any, config: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__", ()) if isinstance(result, dict) else ()
    if interrupts:
        interrupt = interrupts[0]
        return interrupt.value if hasattr(interrupt, "value") else interrupt

    snapshot = graph.get_state(config)
    if getattr(snapshot, "interrupts", ()):
        interrupt = snapshot.interrupts[0]
        return interrupt.value if hasattr(interrupt, "value") else interrupt
    return None


def _render_sources(sources: list[dict[str, Any]]) -> Table:
    table = Table(title="Sources")
    table.add_column("#", justify="right")
    table.add_column("Title")
    table.add_column("URL")
    table.add_column("Snippet")
    for index, source in enumerate(sources, start=1):
        table.add_row(
            str(index),
            str(source.get("title", "Untitled source")),
            str(source.get("url", "")),
            str(source.get("snippet", "")),
        )
    return table


def _render_retry_log(retry_log: list[dict[str, Any]]) -> Table:
    table = Table(title="Retry Log")
    table.add_column("Attempt", justify="right")
    table.add_column("Mitigation")
    table.add_column("Reason")
    for entry in retry_log:
        table.add_row(str(entry.get("attempt", "")), str(entry.get("mitigation", "")), str(entry.get("reason", "")))
    return table


def _render_interrupt(payload: dict[str, Any]) -> None:
    kind = payload.get("kind", "unknown")
    draft_answer = str(payload.get("draft_answer", ""))
    console.print(
        Panel(
            f"kind: {kind}\nattempt: {payload.get('attempt')}\nmode: {payload.get('mode')}\n\n{draft_answer}",
            title="Paused Run",
        )
    )
    sources = payload.get("sources") or []
    if sources:
        console.print(_render_sources(sources))
    verdict = payload.get("verifier_verdict") or {}
    notes = verdict.get("notes") or []
    console.print(
        Panel(
            f"status: {verdict.get('status', 'n/a')}\nconfidence: {verdict.get('confidence', 'n/a')}\nnotes: {', '.join(notes) if notes else 'none'}",
            title="Verifier Verdict",
        )
    )
    if kind == "escalation" and payload.get("retry_log"):
        console.print(_render_retry_log(payload["retry_log"]))


def _prompt_resume_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    kind = payload.get("kind")
    if kind == "approval":
        choice = Prompt.ask("[a]pprove / [r]eject / [e]dit / [q]uit", choices=["a", "r", "e", "q"], default="a")
        if choice == "a":
            return {"decision": "approved"}
        if choice == "r":
            return {"decision": "rejected"}
        if choice == "e":
            return {"decision": "edited", "edited_text": Prompt.ask("Edited text")}
        return None
    if kind == "escalation":
        choice = Prompt.ask("[a]cknowledge / [e]dit / [q]uit", choices=["a", "e", "q"], default="a")
        if choice == "a":
            return {"decision": "acknowledged"}
        if choice == "e":
            return {"decision": "edited", "edited_text": Prompt.ask("Edited text")}
        return None
    raise ValueError(f"unsupported interrupt kind: {kind}")


def _print_final_outcome(state: dict[str, Any]) -> None:
    published_path = state.get("published_path") or "<none>"
    decision = state.get("decision") or "<unknown>"
    console.print(Panel(f"published_path: {published_path}\ndecision: {decision}", title="Final Outcome"))
    retry_log = state.get("retry_log") or []
    if retry_log:
        console.print(_render_retry_log(retry_log))
    else:
        console.print("Retry log: none")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the LangGraph Week 6 HITL agent.")
    parser.add_argument("question", help="Question to send through the agent graph.")
    parser.add_argument("--offline", action="store_true", help="Force offline mode for deterministic demos.")
    parser.add_argument("--thread-id", help="Optional thread ID. If omitted, a new one is derived.")
    parser.add_argument("--db-path", help="Optional checkpoint database path.")
    args = parser.parse_args()

    mode = "offline" if args.offline or _env_flag("OFFLINE") else "live"
    thread_id = args.thread_id or derive_thread_id()
    config = {"configurable": {"thread_id": thread_id}}
    graph = build_graph(mode=mode, db_path=args.db_path)

    console.print(f"thread_id: {thread_id}")
    if args.db_path:
        console.print(f"checkpoint_db: {args.db_path}")

    snapshot = graph.get_state(config)
    if snapshot.next:
        state = dict(snapshot.values)
        payload = _extract_interrupt_payload(state, graph, config)
    else:
        state = graph.invoke(make_initial_state(args.question, thread_id, mode), config)
        payload = _extract_interrupt_payload(state, graph, config)

    while payload is not None:
        _render_interrupt(payload)
        resume_payload = _prompt_resume_payload(payload)
        if resume_payload is None:
            console.print("Exited without resuming the paused thread.")
            return 0
        state = graph.invoke(Command(resume=resume_payload), config)
        payload = _extract_interrupt_payload(state, graph, config)

    _print_final_outcome(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
