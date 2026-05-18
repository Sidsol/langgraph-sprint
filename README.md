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

## Node analysis

The parent graph has **9 executable nodes** plus **3 conditional-edge routers** plus **1 subgraph** (which itself contains 3 internal nodes). All node specs live in [`architecture.md §5`](crispy-docs/projects/001-langgraph-week6-labs/architecture.md); the table below is a fast operational summary keyed to the files you'll actually open.

### Parent-graph nodes

| Node | File | Reads (state) | Writes (state) | Why it exists |
|---|---|---|---|---|
| `planner` | `src/agent/nodes/planner.py` | `question`, `attempt`, `max_attempts`, `retry_log`, `mode` | `attempt` (+1), `plan`, `selected_tool`, `research_depth`, `research_plan` | Single entry point. Increments the attempt counter, decides search vs calculator, and (for search) decides shallow vs deep research and generates the sub-query plan. Retry-aware: on a retry it inspects the most recent `retry_log` entry's mitigation to bias its next move (e.g., revised query, switched tool). |
| `search_tool` | `src/agent/nodes/search_tool.py` | `question`, `mode`, `research_plan`, `research_depth` | `sources`, `research_report`, `draft_answer`, `confidence`, `tool_calls`, `tool_results`, `tool_error` | Runs `Searcher.multi_search()` across all sub-queries, dedupes by URL, then builds a structured `ResearchReport` (direct answer + key facts + perspectives + unknowns + glossary). Live mode forces JSON-mode synthesis through the LLM; offline mode returns deterministic stubs. Any live-mode parse failure emits a `tool_error` JSONL event naming the exact stage that failed. |
| `calculator_tool` | `src/agent/nodes/calculator_tool.py` | `question`, `mode` | `draft_answer`, `confidence`, `tool_calls`, `tool_results`, `tool_error` | Safe arithmetic evaluator via AST allowlist (rejects `__import__`, function calls, attribute access). Skips the sources/citation path because calculator answers are self-evident. |
| `citation_verifier` | `src/agent/subgraphs/citation_verifier.py` (subgraph) | `draft_answer`, `sources`, `research_report` (if present), `mode`, `attempt` | `citation_verdict`, `confidence` | Runs as a labeled parent-graph node but is internally a 3-node LangGraph subgraph: `extract_claims` → `check_alignment` → `emit_verdict`. When `research_report.key_facts` is present, it validates each fact against its claimed source indices and applies a source-diversity boost (1.15× when ≥2 distinct domains support a claim). Synthesized facts with no citations force a `weak` verdict — the architecture's "blind-synthesis guardrail." |
| `evaluator` | `src/agent/nodes/evaluator.py` | `draft_answer`, `tool_error`, `citation_verdict`, `attempt`, `max_attempts`, `mode` | `evaluator_verdict`, `decision`, `unsafe_to_publish`, `retry_log` (append), `evaluator_history` (append) | **The only writer of `retry_log` and `unsafe_to_publish`.** Computes `unsafe_to_publish` from citation/tool-error/confidence per architecture §4 formula, then chooses publish / retry / fallback / escalate. On retry/fallback/escalate decisions, appends exactly one structured `{attempt, reason, mitigation}` entry. Mitigation is a closed `Literal` enum (no ad-hoc strings allowed). |
| `hitl_gate` | `src/agent/nodes/hitl_gate.py` | `draft_answer`, `sources`, `citation_verdict`, `attempt`, `mode`, `thread_id` | `human_decision`, `edited_text`, `decision` | Fires the **approval interrupt** (`kind: "approval"`) via `langgraph.types.interrupt()`. Strictly **no side effects before `interrupt()`** — the node restarts on resume per LangGraph semantics, so any file/network write here would double-execute. All real writes live in `publisher`. |
| `publisher` | `src/agent/nodes/publisher.py` (orchestration) + `src/publisher/publisher.py` (writer) | `thread_id`, `draft_answer` or `edited_text`, `sources`, `research_report`, `mode`, `published_path` | `published_path`, `decision` | **Entry-guard dedupe:** first line is `if state["published_path"] is not None: return {}` — makes the node a strict no-op on any re-entry (resume, replay, operator restart). On first execution: atomically writes `outbox/answers/<thread_id>.md` + `outbox/sent/<thread_id>.eml` via `os.replace`, then prints the SMTP envelope to stdout. Renders the structured `ResearchReport` as multi-section markdown when present; falls back to a plain-text format for legacy shallow-mode runs. |
| `fallback` | `src/agent/nodes/fallback.py` | `question`, `tool_results`, `retry_log`, `attempt`, `mode` | `draft_answer`, `confidence`, `decision`, `messages` | Safe terminal when the system can return a bounded answer but shouldn't claim certainty (`unsafe_to_publish == False` and retries exhausted). Pure text generation, no retries, no interrupts. |
| `escalate_to_human` | `src/agent/nodes/escalate_to_human.py` | `question`, `draft_answer`, `sources`, `retry_log`, `attempt`, `mode`, `thread_id` | `human_decision` (`acknowledged` or `edited`), `edited_text`, `decision` | The **second interrupt** (`kind: "escalation"`). Fires only when retries are exhausted AND `unsafe_to_publish == True`. Same idempotency rule as `hitl_gate` — no side effects before `interrupt()`. The escalation path **never** reaches `publisher`; the human takeover ends the run. |

### Conditional-edge routers (pure functions, no state writes)

| Router | File | Where it runs | Predicate (informal) | Possible destinations |
|---|---|---|---|---|
| `route_planner_output` | `src/agent/routers.py` | After `planner` | `selected_tool == "search"` → `search_tool`; `"calculator"` → `calculator_tool`; otherwise → `fallback` | `search_tool` · `calculator_tool` · `fallback` |
| `route_after_evaluator` | `src/agent/routers.py` | After `evaluator` | `pass` + safe → `hitl_gate`; `retry` + budget left → `planner`; unsafe + budget exhausted → `escalate_to_human`; else → `fallback` | `hitl_gate` · `planner` · `fallback` · `escalate_to_human` |
| `route_after_hitl` | `src/agent/routers.py` | After `hitl_gate` resume | `human_decision in {approved, edited}` → `publisher`; `rejected` → `END` | `publisher` · `END` |

Every router writes a `branch_decision` JSONL event so the grader can grep the log to verify Lab 6.2 coverage in any run.

### Citation Verifier internals (the subgraph)

| Internal node | What it does | Offline behavior | Live behavior |
|---|---|---|---|
| `extract_claims` | Parses the draft into atomic factual claims | Regex sentence splitter | LLM prompt asking for a JSON list of claims (with regex fallback if parse fails) |
| `check_alignment` | Scores each claim against its cited sources | Word-overlap heuristic (Jaccard-like) on snippet text | LLM scores each (claim, sources) pair Yes/Partial/No → 1.0/0.5/0.0 with graceful per-claim fallback |
| `emit_verdict` | Aggregates per-claim scores into a `CitationVerdict` | `confidence = mean(scores)`; `grounded` if ≥ 0.70 else `weak`; `not_applicable` when sources is empty (calculator path). Synthesized-fact override always forces `weak` regardless of mean. |

### Node-by-rubric crosswalk

| Week 6 lab | Nodes that satisfy it |
|---|---|
| **6.1** — 3+ stateful nodes | `planner`, `search_tool`, `calculator_tool`, `evaluator`, `hitl_gate`, `publisher`, `fallback`, `escalate_to_human`, plus the `citation_verifier` subgraph (which itself has 3 nodes) — well over the minimum |
| **6.2** — conditional routing on runtime state | All three routers above; the evaluator branch is the rubric's "routes on tool output quality or confidence" requirement |
| **6.3** — self-correction with retry | `evaluator` (writes retry log + chooses mitigation) + retry edge from `evaluator → planner` + `fallback` and `escalate_to_human` terminals |
| **6.4** — HITL before high-impact action | `hitl_gate` (approval interrupt) is placed **strictly before** `publisher` (the high-impact node); `escalate_to_human` is the second interrupt for retry-exhausted cases |
| **Sub-agent integration** | `citation_verifier` as a labeled subgraph node in the parent graph; its internal 3-node workflow demonstrates nested orchestration without changing the parent's state contract |

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
