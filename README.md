# langgraph-week6-labs

Deliver a single Python repo that a student or grader can run locally to observe a LangGraph state machine with 3+ explicit nodes, runtime conditional routing, structured tool execution, logged self-correction thresholds, a human approval gate before publishing, and one bounded sub-agent behavior integrated into the broader orchestration graph. The result is intentionally small enough to understand in one sitting and complete enough to serve as a gradable Week 6 reference implementation.

## Prerequisites
- `uv`
- Python 3.11+ (managed through `uv`; this scaffold currently pins the interpreter via `.python-version`)
- `OPENAI_API_KEY`
- `TAVILY_API_KEY`

## Setup
```bash
uv sync
```

## Run commands
```bash
uv run python cli.py "question"
uv run python cli.py --offline "question"
uv run streamlit run app.py
uv run pytest
uv run pytest -k routers
```

## Architecture docs
- Full project architecture: [`crispy-docs/projects/001-langgraph-week6-labs/architecture.md`](crispy-docs/projects/001-langgraph-week6-labs/architecture.md)
- Repo-local summary: [`docs/architecture.md`](docs/architecture.md)
