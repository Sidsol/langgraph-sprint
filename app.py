from __future__ import annotations

import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from agent import build_graph
from agent.graph import get_paused_payload, list_paused_threads, resume_thread

_DEFAULT_DB_PATH = ".checkpoints/agent.sqlite"
_FLASH_KEY = "_review_surface_flash"


@st.cache_resource(show_spinner=False)
def _build_review_graph(mode: str, db_path: str):
    return build_graph(mode=mode, db_path=db_path)


def _show_flash() -> None:
    flash = st.session_state.pop(_FLASH_KEY, None)
    if not flash:
        return
    level, message = flash
    getattr(st, level if level in {"success", "info", "warning", "error"} else "info")(message)


def _set_flash(level: str, message: str) -> None:
    st.session_state[_FLASH_KEY] = (level, message)


def _format_thread_label(thread: dict[str, Any]) -> str:
    node = thread.get("node") or "paused"
    kind = thread.get("kind") or "unknown"
    return f"{thread['thread_id']} — {kind} @ {node}"


def _render_footer(thread_id: str | None = None) -> None:
    thread_hint = thread_id or "<thread_id>"
    st.markdown("---")
    st.caption(f"Logs: `logs/run-{thread_hint}.jsonl`  |  Outbox: `outbox/answers/`, `outbox/sent/`")


def _resume_and_refresh(graph: Any, thread_id: str, kind: str, decision: str, edited_text: str | None = None) -> None:
    final = resume_thread(graph, thread_id, decision, edited_text=edited_text)
    published_path = final.get("published_path")

    if kind == "approval":
        if decision == "rejected":
            _set_flash("info", "Rejected; no publish.")
        elif decision == "approved":
            _set_flash("success", f"Published: {published_path}")
        else:
            _set_flash("success", f"Published edited: {published_path}")
    else:
        if decision == "acknowledged":
            _set_flash("info", "Acknowledged; run ended.")
        else:
            _set_flash("info", "Edit recorded; run ended.")

    st.rerun()


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="langgraph-week6-labs review", layout="wide")
    st.title("🧪 LangGraph Week 6 Labs — Review Surface")

    with st.sidebar:
        st.header("Configuration")
        db_path = st.text_input("Checkpoint DB", value=os.environ.get("CHECKPOINT_DB", _DEFAULT_DB_PATH))
        mode = st.selectbox("Mode", ["offline", "live"], index=0)
        if st.button("Refresh paused threads"):
            st.rerun()
        st.caption(
            "Same DB the CLI uses. Changing the DB path or mode rebuilds the graph against that shared SqliteSaver file."
        )

    graph = _build_review_graph(mode, db_path)
    _show_flash()

    st.subheader("Paused threads")
    threads = list_paused_threads(db_path)
    if not threads:
        st.info("No paused threads. Run `uv run python cli.py --offline \"...\"` and approve/reject from here.")
        _render_footer()
        return

    thread_map = {thread["thread_id"]: thread for thread in threads}
    selected_thread = st.selectbox(
        "Select a thread",
        options=list(thread_map),
        format_func=lambda thread_id: _format_thread_label(thread_map[thread_id]),
    )
    explicit_thread_id = st.text_input("Or enter a thread_id directly", value="")
    active_thread_id = explicit_thread_id.strip() or selected_thread
    payload = get_paused_payload(graph, active_thread_id)

    if not payload:
        st.warning("Thread not paused or not found in this DB.")
        _render_footer(active_thread_id)
        return

    selected_summary = thread_map.get(active_thread_id)
    if selected_summary:
        st.caption(f"Paused node: `{selected_summary.get('node') or 'unknown'}`")

    kind = str(payload.get("kind", "approval"))
    st.markdown(f"### Interrupt kind: `{kind}`")
    st.markdown(f"**Attempt:** {payload.get('attempt')}  |  **Mode:** {payload.get('mode')}")
    st.markdown("**Draft answer:**")
    st.code(str(payload.get("draft_answer", "")), language="markdown")

    sources = payload.get("sources") or []
    if sources:
        st.markdown("**Sources:**")
        st.table(sources)

    st.markdown("**Verifier verdict:**")
    st.json(payload.get("verifier_verdict") or {})

    retry_log = payload.get("retry_log") or []
    if retry_log:
        st.markdown("**Retry log:**")
        st.table(retry_log)

    if kind == "approval":
        edited = st.text_area(
            "Edited text (for Edit)",
            value=str(payload.get("draft_answer", "")),
            height=160,
            key=f"approval-edit-{active_thread_id}",
        )
        approve_col, edit_col, reject_col = st.columns(3)
        with approve_col:
            if st.button("✅ Approve", type="primary", key=f"approve-{active_thread_id}"):
                _resume_and_refresh(graph, active_thread_id, kind, "approved")
        with edit_col:
            if st.button("✏️ Edit & approve", key=f"edit-approve-{active_thread_id}"):
                _resume_and_refresh(graph, active_thread_id, kind, "edited", edited_text=edited)
        with reject_col:
            if st.button("❌ Reject", key=f"reject-{active_thread_id}"):
                _resume_and_refresh(graph, active_thread_id, kind, "rejected")
    elif kind == "escalation":
        edited = st.text_area(
            "Edit before ending",
            value=str(payload.get("draft_answer", "")),
            height=160,
            key=f"escalation-edit-{active_thread_id}",
        )
        acknowledge_col, edit_col = st.columns(2)
        with acknowledge_col:
            if st.button("🛎️ Acknowledge", type="primary", key=f"ack-{active_thread_id}"):
                _resume_and_refresh(graph, active_thread_id, kind, "acknowledged")
        with edit_col:
            if st.button("✏️ Edit & acknowledge", key=f"edit-ack-{active_thread_id}"):
                _resume_and_refresh(graph, active_thread_id, kind, "edited", edited_text=edited)
    else:
        st.warning(f"Unsupported interrupt kind: {kind}")

    _render_footer(active_thread_id)


if __name__ == "__main__":
    main()
