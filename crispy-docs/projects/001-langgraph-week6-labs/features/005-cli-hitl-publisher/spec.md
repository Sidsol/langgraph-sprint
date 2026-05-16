---
feature: 005-cli-hitl-publisher
project: 001-langgraph-week6-labs
document: spec
status: complete
updated: 2026-05-16
---

# Spec: cli-hitl-publisher

## Goal
Complete the M3 walking skeleton by adding a shared SQLite-backed checkpointer, a real CLI human-approval loop, and an idempotent publisher that writes local artifacts only after approval.

## Scope
- switch `src/agent/graph.py` to `SqliteSaver` with WAL mode and a shared `CHECKPOINT_DB` path
- add `hitl_gate` as the approval `interrupt()` node and `publisher` as the post-approval side-effect node
- replace the placeholder `cli.py` with a `rich`-based pause/resume surface for approval and escalation flows
- publish approved answers atomically to markdown and `.eml` artifacts with a strict dedupe guard on node re-entry
- extend offline end-to-end tests for approve, reject, edit, dedupe, and interrupt-log evidence

## Acceptance criteria
- publishable runs pause with an approval payload instead of ending immediately
- `approved` and `edited` resumes write answer and sent artifacts; `rejected` ends without publishing
- resume uses the same `thread_id` against the same SQLite checkpoint file
- publisher re-entry is a no-op after `published_path` is set
- offline pytest coverage proves pause-then-publish plus interrupt log evidence
