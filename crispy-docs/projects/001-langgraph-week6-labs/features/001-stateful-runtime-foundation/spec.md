---
feature: 001-stateful-runtime-foundation
document: spec
status: complete
created: 2026-05-16
---

# Spec: 001-stateful-runtime-foundation

## Purpose
Establish the shared runtime contracts for later LangGraph features: canonical state, live/offline tool adapters, JSONL event logging, and importable package wiring for the `src/` layout.

## Architecture references
- `architecture.md §4` — verified canonical `AgentState` and `initial_state()` contract.
- `architecture.md §5` — implemented search, calculator, and chat adapter behavior.
- `architecture.md §9` — implemented JSONL event constants and `write_event()` schema.
- `architecture.md §11` — verified environment knobs and offline/live mode expectations.

## Files delivered
- Verified unchanged: `src/agent/state.py`, `.env.example`
- Implemented: `src/agent/logging.py`, `src/tools/__init__.py`, `src/tools/searcher.py`, `src/tools/calculator.py`, `src/tools/llm.py`, `tests/test_001_foundation.py`
- Packaging/runtime wiring: `pyproject.toml`, `uv.lock`

## Acceptance criteria status
- `AgentState` and `initial_state()` match architecture §4: **pass**
- Tool adapters expose live/offline implementations without graph imports: **pass**
- `write_event(thread_id, attempt, node, event, mode, **kw)` plus architecture §9 event constants: **pass**
- `.env.example` documents `OPENAI_MODEL`, `OFFLINE`, `CHECKPOINT_DB`: **pass**
- `uv sync` succeeds: **pass**
- Foundation tests covering state, searcher, calculator, chat, and logging: **pass (6 tests)**

## Verification
- `uv sync` → exit code `0`
- smoke import/execution command from the feature brief → exit code `0`
- `uv run pytest tests/test_001_foundation.py -v` → exit code `0` (`6 passed`)
