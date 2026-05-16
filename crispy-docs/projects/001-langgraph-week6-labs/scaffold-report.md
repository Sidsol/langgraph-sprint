---
project: 001-langgraph-week6-labs
document: scaffold-report
status: complete
created: 2026-05-15
uv_sync_ok: true
import_smoke_ok: true
pytest_collect_ok: true
repos_initialized: 1
repos_skipped: 0
files_created: 39
deps_added_runtime: 11
deps_added_dev: 1
python_pinned: "3.14"
---

# Scaffold Report: langgraph-week6-labs

## Environment
- Repo root: C:\repos\langgraph-sprint
- uv: 0.11.14 (pip-installed at C:\Users\jonamart\AppData\Roaming\Python\Python314\Scripts\uv.exe)
- Python: 3.14.3 (system); project pinned via .python-version to 3.14
- Git: 2.53.0

## Commands executed
1. `git --version` — exit 0
2. `python --version` — exit 0
3. `uv --version` — exit 0
4. `uv init --app --name langgraph-week6-labs` — exit 0
5. `Remove-Item -Force main.py, hello.py (if present)` — exit 0
6. `uv add "langgraph>=0.4,<0.5" "langgraph-checkpoint-sqlite>=2,<3" "langchain-openai>=0.3,<0.4" "langchain-core>=0.3,<0.4" "openai>=1,<2" "tavily-python>=0.5,<0.6" "pydantic>=2,<3" "streamlit>=1,<2" "typing-extensions>=4,<5" "python-dotenv>=1,<2" "rich>=13,<14"` — exit 0
7. `uv add --dev "pytest>=8,<9"` — exit 0
8. `python - <inline scaffold generation script>` — exit 0
9. `git --no-pager status --short --branch` — exit 0
10. `git init -b main` — exit 0
11. `git add -A` — exit 0
12. `git -c user.name="Scaffold Bot" -c user.email="scaffold@local" commit -m "chore: initial scaffold per architecture.md" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"` — exit 0
13. `uv sync` — exit 0
14. `uv run python -c "import langgraph, langchain_openai, openai, tavily, pydantic, streamlit, dotenv, rich; print('OK')"` — exit 0
15. `uv run pytest --collect-only` — exit 5 (acceptable placeholder result: no tests collected, no import errors)
16. `git --no-pager status --short` — exit 0
17. `git --no-pager diff -- uv.lock crispy-docs/projects/001-langgraph-week6-labs/scaffold-report.md` — exit 0
18. `git --no-pager diff --stat -- uv.lock crispy-docs/projects/001-langgraph-week6-labs/scaffold-report.md` — exit 0

## Files created
- Repo root
  - `.env.example`
  - `.gitignore`
  - `.python-version`
  - `README.md`
  - `app.py`
  - `cli.py`
  - `pyproject.toml`
  - `uv.lock`
- `.checkpoints/`
  - `.gitkeep`
- `docs/`
  - `architecture.md`
- `logs/`
  - `.gitkeep`
- `outbox/answers/`
  - `.gitkeep`
- `outbox/sent/`
  - `.gitkeep`
- `src/agent/`
  - `__init__.py`
  - `graph.py`
  - `logging.py`
  - `routers.py`
  - `state.py` (copied from architecture §4)
- `src/agent/nodes/`
  - `__init__.py`
  - `planner.py`
  - `search_tool.py`
  - `calculator_tool.py`
  - `evaluator.py`
  - `hitl_gate.py`
  - `publisher.py`
  - `fallback.py`
  - `escalate_to_human.py`
- `src/agent/subgraphs/`
  - `__init__.py`
  - `citation_verifier.py`
- `src/tools/`
  - `__init__.py`
  - `searcher.py`
  - `calculator.py`
  - `llm.py`
- `src/publisher/`
  - `__init__.py`
  - `publisher.py`
- `tests/`
  - `conftest.py`
  - `test_graph_wiring.py`
  - `test_routers.py`
  - `test_e2e_offline.py`

## Files left untouched
- `crispy-docs/` project planning docs were preserved; only this `scaffold-report.md` placeholder was overwritten as requested.

## Deviations from architecture
None.

## Verification results
- `uv sync`: pass — resolved 86 packages and checked 85 packages successfully.
- import smoke test: pass — `OK`
- `pytest --collect-only`: acceptable placeholder result — exit 5 with `collected 0 items`; no import errors.

## Open follow-ups for feature-level CRISPY runs
- Implement the CLI and Streamlit entry points in `cli.py` and `app.py`.
- Implement graph assembly, routing, logging, parent nodes, and the citation-verifier subgraph under `src/agent/`.
- Implement live/offline tool adapters in `src/tools/` and atomic publish helpers in `src/publisher/`.
- Replace placeholder pytest modules with the graph wiring, router, and offline end-to-end coverage defined in architecture §12.
- Complete every remaining Python module marked with `# TODO: implement per architecture ...`; only `src/agent/state.py` is fully scaffolded.
