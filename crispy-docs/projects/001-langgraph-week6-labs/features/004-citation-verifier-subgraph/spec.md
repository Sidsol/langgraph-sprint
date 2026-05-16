---
feature: 004-citation-verifier-subgraph
project: 001-langgraph-week6-labs
document: spec
status: complete
created: 2026-05-15
updated: 2026-05-16
---

# Spec: citation-verifier-subgraph

Feature 004 replaces the citation verifier stub with a real shared-state LangGraph subgraph.

## Delivered scope
- `src/agent/subgraphs/citation_verifier.py` now compiles `extract_claims -> check_alignment -> emit_verdict` with `RetryPolicy(max_attempts=2)` on the extraction and alignment nodes.
- The subgraph keeps the parent `AgentState` contract, adds `_verifier_claims`, `_verifier_scores`, and `_verifier_notes` scratch fields, and narrows the compiled output to verifier-owned fields so reducer-backed parent lists do not duplicate on re-entry.
- Offline verification uses regex claim splitting plus token-overlap scoring; live verification uses `make_chat("live")` with graceful claim parsing fallback and per-claim degradation to `0.0` / `"unable to verify"` when an alignment response cannot be parsed.
- `emit_verdict` implements the architecture aggregation rule, preserves `FORCE_WEAK` / `FORCE_RETRY` marker behavior, and keeps calculator/no-source runs `not_applicable`.
- `src/agent/subgraphs/__init__.py` re-exports the compiled subgraph and a wrapper node helper.
- `tests/test_004_citation_verifier.py` adds 7 tests for compilation, internal nodes, grounded/weak/not_applicable paths, and marker behavior.

## Deferred scope
- Streamlit reviewer workflows remain in feature 006.
- Evidence packaging hardening remains in feature 007.
