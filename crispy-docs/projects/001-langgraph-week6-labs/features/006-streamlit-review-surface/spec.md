---
feature: 006-streamlit-review-surface
project: 001-langgraph-week6-labs
document: spec
status: complete
updated: 2026-05-16
---

# Spec: streamlit-review-surface

## Goal
Add a Streamlit secondary review surface that opens the same SQLite checkpointer as the CLI, lists paused threads, shows the interrupt payload, and resumes with the same payload schema.

## Scope
- replace `app.py` with a screenshot-friendly Streamlit review panel backed by the shared `CHECKPOINT_DB`
- add `src/agent/graph.py` helpers for paused-thread enumeration, paused-payload lookup, and CLI-compatible resume submission
- keep every approve/reject/edit/ack decision routed through the existing LangGraph interrupt resume path with no alternate publish logic
- add focused helper tests plus import/smoke verification for the secondary surface

## Acceptance criteria
- Streamlit lists paused approval/escalation threads from the same `SqliteSaver` file the CLI uses
- displayed payload fields match the CLI HITL evidence surface (`draft_answer`, `sources`, `verifier_verdict`, `attempt`, `mode`, and `retry_log` when present)
- resume actions submit the same `Command(resume={"decision": ..., "edited_text": ...})` schema as `cli.py`
- pytest coverage proves empty listing, paused listing, payload lookup, approve publish, and reject no-publish behavior
