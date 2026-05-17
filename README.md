# LangGraph Week 6 Labs — Submission Bundle

This repository is a grader-ready Week 6 LangGraph submission: a single Python agent that plans, conditionally routes to calculator or search, runs a bounded `citation_verifier` subgraph, retries once when evidence is weak, pauses at a human-in-the-loop approval gate before side effects, and publishes only after approval. The repo ships both runnable surfaces (CLI + Streamlit), committed evidence logs, rubric-trace tests, and CRISPY planning artifacts so the grader can inspect the workflow without code archaeology.

## Quick demo
```powershell
uv sync
uv run python cli.py --offline "What is 12*12?"  # then press 'a' to approve
uv run pytest
```

## Prerequisites
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Optional for live mode: `OPENAI_API_KEY` and `TAVILY_API_KEY`

## Setup
```powershell
git clone <your-copy-of-this-repo>
cd langgraph-sprint
uv sync
```

If `uv` is not installed yet:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv sync
```

## Configuration
Copy `.env.example` to `.env` if you want to override defaults.

| Key | Purpose |
|---|---|
| `OPENAI_API_KEY` | Required only for live LLM calls. |
| `OPENAI_MODEL` | Defaults to `gpt-5.4`; override if your account needs a different compatible model. |
| `TAVILY_API_KEY` | Required only for live Tavily search. |
| `OFFLINE` | Set `1` to prefer deterministic offline mode by default. |
| `CHECKPOINT_DB` | SQLite checkpoint path shared by CLI and Streamlit; defaults to `.checkpoints/agent.sqlite`. |

## Running the agent
- **CLI offline (no API keys):** `uv run python cli.py --offline "What is 12*12?"`
- **CLI live:** `uv run python cli.py "Tell me about LangGraph subgraphs"`
- **Streamlit panel:** `uv run streamlit run app.py` then open <http://localhost:8501>
- **Tests:** `uv run pytest`

## Deep research mode
```powershell
uv run python cli.py --offline "Compare LangGraph and LangChain agent abstractions"
# then approve; observe the published markdown with Direct Answer / Key Facts / Sources sections
```

When `planner` detects a broader research prompt, it switches the search path into `deep` mode: 3–5 sub-queries run through `Searcher.multi_search(...)`, the search node emits a structured `ResearchReport`, `citation_verifier` scores per-fact cited sources, and `publisher` writes a sectioned answer with source-diversity notes.

## Architecture
The parent graph starts at `planner`, routes to `search_tool` or `calculator_tool`, always passes through the `citation_verifier` subgraph, and lets `evaluator` choose between publish, retry, fallback, or escalation. On search questions, `planner` also chooses `research_depth`; deep mode fans out into multiple sub-queries and ends in a structured markdown publish, while shallow mode preserves the original single-query runtime contract. The canonical detailed write-up lives in [`crispy-docs/projects/001-langgraph-week6-labs/architecture.md`](crispy-docs/projects/001-langgraph-week6-labs/architecture.md); the repo-local summary lives in [`docs/architecture.md`](docs/architecture.md).

```mermaid
flowchart TD
    START([START]) --> planner[planner]
    planner --> tool_router{tool_router}
    tool_router -->|selected_tool == "search"| search_tool[search_tool]
    tool_router -->|selected_tool == "calculator"| calculator_tool[calculator_tool]
    tool_router -->|invalid selection| fallback[fallback]

    subgraph citation_verifier["citation_verifier (subgraph node)"]
        extract_claims[extract_claims] --> check_alignment[check_alignment] --> emit_verdict[emit_verdict]
    end

    search_tool -->|always| citation_verifier
    calculator_tool -->|always| citation_verifier
    citation_verifier -->|always| evaluator[evaluator]

    evaluator -->|decision == "publish"| hitl_gate[hitl_gate / interrupt()]
    evaluator -->|decision == "retry" and attempt < max_attempts| planner
    evaluator -->|decision == "fallback"| fallback
    evaluator -->|decision == "escalate" or attempt >= max_attempts| escalate_to_human[escalate_to_human / interrupt()]

    hitl_gate -->|human_decision in {approved, edited}| publisher[publisher]
    hitl_gate -->|human_decision == rejected| END([END])

    publisher -->|publish complete| END
    fallback -->|safe fallback returned| END
    escalate_to_human -->|manual takeover logged| END
```

## How the rubric maps

| Artifact name | Where it lives in this repo | Command to regenerate it |
|---|---|---|
| Architecture diagram of your graph (nodes + transitions) | `README.md`, `docs/architecture.md`, `crispy-docs/projects/001-langgraph-week6-labs/architecture.md` | `Get-Content .\docs\architecture.md` |
| Code implementation with conditional routing | `src/agent/graph.py`, `src/agent/routers.py`, `tests/test_graph_wiring.py`, `tests/test_routers.py` | `uv run pytest tests\test_graph_wiring.py tests\test_routers.py -q` |
| Execution log showing at least one retry or correction flow | `docs/evidence/02-retry-then-pass/run-t-evidence-002-retry.jsonl` | `uv run python scripts\regenerate_evidence.py 02-retry-then-pass` |
| Evidence of one human-in-the-loop interrupt in action | `docs/evidence/01-success-calculator/run-t-evidence-001-calc.jsonl` | `uv run python scripts\regenerate_evidence.py 01-success-calculator` |
| Short architecture write-up (node roles and routing logic) | `docs/architecture.md` | `Get-Content .\docs\architecture.md` |
| State graph implementation (3+ nodes, conditional branch included) | `src/agent/graph.py`, `tests/test_graph_wiring.py` | `uv run pytest tests\test_graph_wiring.py -q` |
| Self-correction loop evidence with retry/fallback behavior | `docs/evidence/02-retry-then-pass/run-t-evidence-002-retry.jsonl`, `docs/evidence/04-escalate-budget-exhausted/run-t-evidence-004-escalate.jsonl`, `tests/test_e2e_offline.py` | `uv run python scripts\regenerate_evidence.py all` |
| Human-in-the-loop checkpoint evidence (screenshot or log) | `docs/evidence/03-hitl-reject/run-t-evidence-003-reject.jsonl`, `app.py` | `uv run python scripts\regenerate_evidence.py 03-hitl-reject` |

## Generated evidence
Committed example runs live under [`docs/evidence/`](docs/evidence/). Each scenario folder contains a short README plus the canonical JSONL log, and published scenarios also include `published-answer.md` and `published-envelope.eml`. Fresh runs always append runtime evidence to `logs/run-<thread_id>.jsonl`; refresh the committed bundle with `uv run python scripts\regenerate_evidence.py all`.

## Project structure
```text
.
├── app.py          # Streamlit review surface over the shared SQLite checkpointer
├── cli.py          # Canonical CLI demo and HITL resume loop
├── crispy-docs/    # CRISPY planning artifacts and feature-level manifests
├── docs/           # Repo-local architecture summary and committed evidence bundle
├── logs/           # Runtime JSONL logs generated on every run
├── outbox/         # Published markdown answers and mock email envelopes
├── scripts/        # Evidence regeneration helper
├── src/            # Agent graph, nodes, subgraph, tools, and publisher
└── tests/          # Wiring, router, end-to-end, Streamlit, and rubric-trace tests
```

## CRISPY planning artifacts
All project planning artifacts live in [`crispy-docs/projects/001-langgraph-week6-labs/`](crispy-docs/projects/001-langgraph-week6-labs/):
- [`vision.md`](crispy-docs/projects/001-langgraph-week6-labs/vision.md)
- [`domain-research.md`](crispy-docs/projects/001-langgraph-week6-labs/domain-research.md)
- [`architecture.md`](crispy-docs/projects/001-langgraph-week6-labs/architecture.md)
- [`feature-map.md`](crispy-docs/projects/001-langgraph-week6-labs/feature-map.md)
- [`roadmap.md`](crispy-docs/projects/001-langgraph-week6-labs/roadmap.md)
- [`project-checklist.md`](crispy-docs/projects/001-langgraph-week6-labs/project-checklist.md)
- [`project-manifest.yaml`](crispy-docs/projects/001-langgraph-week6-labs/project-manifest.yaml)
