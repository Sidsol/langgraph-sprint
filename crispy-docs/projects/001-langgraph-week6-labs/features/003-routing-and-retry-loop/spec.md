---
feature: 003-routing-and-retry-loop
project: 001-langgraph-week6-labs
document: spec
status: complete
created: 2026-05-15
updated: 2026-05-16
---

# Spec: routing-and-retry-loop

Feature 003 delivers Labs 6.2 and 6.3 for the Week 6 LangGraph parent graph.

## Delivered scope
- `src/agent/routers.py` adds `route_planner_output()`, `route_after_evaluator()`, and `route_after_hitl()` with `branch_decision` event logging.
- `src/agent/graph.py` replaces the linear planner/evaluator edges with conditional routing, loop-back to `planner`, and terminal `fallback` / `escalate_to_human` nodes.
- `planner` is retry-aware: it preserves deterministic offline planning, prefixes revised-query retries, and flips tools on `switched_tool`.
- `evaluator` now owns `unsafe_to_publish`, bounded retry/fallback/escalate decisions, structured `retry_log` entries, and `retry` JSONL events with `reason` plus `mitigation`.
- `fallback` returns a bounded safe answer and final `end` log; `escalate_to_human` emits a real LangGraph `interrupt()` for manual takeover.
- `citation_verifier` remains a stub, but it is now attempt-aware for `FORCE_RETRY` and `FORCE_WEAK` markers so retry-loop tests are deterministic.
- `tests/test_routers.py` and `tests/test_e2e_offline.py` cover router predicates, pass-through, retry-then-pass, escalation interrupts, and retry-log JSONL evidence.

## Deferred scope
- Real `hitl_gate` / `publisher` wiring stays deferred to feature 005.
- The full citation-verifier subgraph remains deferred to feature 004.
