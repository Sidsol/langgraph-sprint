# Repository Architecture Summary

This repository scaffolds the Week 6 LangGraph Research/QA agent described in the project architecture. The source of truth remains [`crispy-docs/projects/001-langgraph-week6-labs/architecture.md`](../crispy-docs/projects/001-langgraph-week6-labs/architecture.md).

## System shape
- Parent graph flow: `planner -> tool_router -> (search_tool | calculator_tool | fallback) -> citation_verifier -> evaluator -> (hitl_gate | planner | fallback | escalate_to_human)`.
- `citation_verifier` is a dedicated subgraph node that extracts claims, checks source alignment, and emits a verdict.
- `publisher` writes approved Markdown and mock email artifacts only after a human approval interrupt resumes.

## Shared state and persistence
- Canonical typed state lives in `src/agent/state.py`.
- CLI and Streamlit share a file-backed `SqliteSaver` at `.checkpoints/agent.sqlite`.
- Run evidence is written as JSONL logs under `logs/`.

## Key directories
- `src/agent/` — graph assembly, routers, nodes, subgraphs, and logging helpers.
- `src/tools/` — live/offline search, calculator, and LLM adapters.
- `src/publisher/` — artifact publication helpers.
- `tests/` — graph wiring, router, and offline end-to-end coverage.

## Canonical commands
```bash
uv sync
uv run python cli.py "question"
uv run python cli.py --offline "question"
uv run streamlit run app.py
uv run pytest
```
