---
feature: 002-graph-core-orchestration
project: 001-langgraph-week6-labs
document: spec
status: complete
created: 2026-05-15
updated: 2026-05-16
---

# Spec: graph-core-orchestration

Feature 002 delivers the first runnable Lab 6.1 parent graph for the Week 6 LangGraph repo.

## Delivered scope
- `src/agent/graph.py` compiles a parent graph with `planner -> tool_router -> {search_tool|calculator_tool} -> citation_verifier -> evaluator -> END` and an `InMemorySaver()` default checkpointer.
- `src/agent/__init__.py` exports `build_graph()` and `make_initial_state()` for smoke tests and downstream callers.
- `planner` increments `attempt`, chooses `search` vs `calculator` deterministically, writes node enter/exit events, and emits a stable offline plan.
- `search_tool` and `calculator_tool` normalize tool call/result records, populate draft answer state, and preserve the shared `AgentState` contract.
- `citation_verifier` is a feature-002 stub that returns `grounded` when sources exist and `not_applicable` otherwise, keeping the parent-graph contract stable for feature 004.
- `evaluator` implements the initial scoring contract for feature 002 by passing successful tool runs straight to `END` without retry/HITL logic.
- `tests/test_graph_wiring.py` now covers graph compilation, node registration, planner tool selection, and an offline end-to-end termination path.

## Deferred scope
- Retry routing, real fallback/escalation behavior, and router-module predicates move to `003-routing-and-retry-loop`.
- The real citation verifier subgraph moves to `004-citation-verifier-subgraph`.
- HITL interrupts and publisher side effects stay deferred to feature 005.
