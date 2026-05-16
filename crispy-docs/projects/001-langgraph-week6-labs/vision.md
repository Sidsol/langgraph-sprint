---
project: 001-langgraph-week6-labs
document: vision
status: complete
created: 2026-05-15
---

# Project Vision: langgraph-week6-labs

`langgraph-week6-labs` is a single-repo Python project for Week 6 of a LangGraph course. It packages all four labs into one cohesive, runnable Research/QA agent that plans work, uses web search and calculator tools, conditionally retries when results are weak, pauses for human approval before publishing, and leaves behind clear evidence a grader can inspect.

| Field | Value |
|-------|-------|
| **Project** | `langgraph-week6-labs` |
| **Folder** | `crispy-docs/projects/001-langgraph-week6-labs` |
| **Date** | `2026-05-15` |
| **Status** | `Complete` |

---

## 1. Problem & Opportunity

Week 6 asks the student to demonstrate stateful LangGraph orchestration across four separate labs: multi-node workflow design, conditional routing, self-correction loops, and human-in-the-loop approval. If these competencies are shown in disconnected scripts, it becomes harder for the student to prove the concepts work together and harder for the grader to evaluate node transitions, failure handling, and interrupt behavior in one coherent artifact.

The opportunity is to build a single interactive project that answers real user questions while making orchestration decisions explicit and observable. A compact Research/QA agent is a good fit because it naturally combines planning, tool use, evaluation, retries, and a high-impact publish step that benefits from human review.

---

## 2. Vision Statement

Deliver a single Python repo that a student or grader can run locally to observe a LangGraph state machine with 3+ explicit nodes, runtime conditional routing, structured tool execution, logged self-correction thresholds, a human approval gate before publishing, and one bounded sub-agent behavior integrated into the broader orchestration graph. The result should be small enough to understand in one sitting and complete enough to serve as a gradable Week 6 reference implementation.

---

## 3. Target Users & Stakeholders

| Role | Description | Primary Concerns |
|------|-------------|------------------|
| **Student builder/operator** | Runs the agent, demonstrates the labs, and explains the architecture during review. | Fast setup, obvious node responsibilities, reliable demos, and artifacts that clearly map to the rubric. |
| **Grader / instructor** | Reviews the repo, runs the demo, and verifies the Week 6 competencies. | Correctness of orchestration, visibility into routing/retries/HITL, reproducibility, and clean code organization. |
| **Future learner / remixer** | Reuses the project later as a study example or starter for similar LangGraph assignments. | Readable structure, minimal dependencies, clear docs, and easy ways to swap tools or prompts. |

---

## 4. High-Level Capabilities (Feature Themes)

| ID | Theme | Priority | Notes |
|----|-------|----------|-------|
| TH-01 | Graph Core & State Model | P1 | Define explicit state, named nodes, and clear transitions for planner, tool execution, evaluation, HITL review, and a bounded sub-agent behavior nested within the larger graph. |
| TH-02 | Tooling & Structured Actions | P1 | Support web search and calculator actions through a tool node that normalizes outputs into structured success, error, and confidence fields for downstream routing. |
| TH-03 | Conditional Routing & Self-Correction | P1 | Use evaluator-driven branches to continue, retry, fallback, or escalate based on runtime quality signals, while recording retry reason, mitigation, and stop conditions. |
| TH-04 | Human-in-the-Loop Publishing Gate | P1 | Require an interrupt and explicit approve/reject decision before the agent performs the high-impact publish step for a final answer. |
| TH-05 | Observability & Evidence | P1 | Produce logs, traces, and architecture artifacts that show a successful path, a retry path, and a HITL path without needing deep code archaeology. |
| TH-06 | Demo Surface & Reproducibility | P1 | Offer a CLI-first demo plus a lightweight Streamlit panel so the project is easy to run, visualize, screenshot, and grade from a single repo. |

---

## 5. MVP Definition

**MVP includes (in scope):**
- A single-repo Python 3.11+ application with a CLI entry point and a small Streamlit panel.
- A LangGraph workflow with at least three executable nodes and the recommended planner, tool, evaluator, and HITL responsibilities.
- Explicit state transitions that can be traced from user question to final outcome.
- A structured tool invocation node that supports both web search and calculator behavior.
- At least one runtime conditional branch based on evaluator quality, confidence, or tool result state.
- A self-correction loop with a retry threshold, logged retry reason, logged mitigation strategy, and explicit stop condition.
- A fallback or escalation route after repeated failure.
- A human-in-the-loop interrupt before publishing the canonical final answer.
- LangGraph `MemorySaver` checkpoint persistence for interrupt and resume behavior.
- Deliverable artifacts: architecture diagram, short architecture write-up, state graph implementation, successful run log, retry/correction log, and HITL interrupt evidence.
- One bounded sub-agent behavior or nested workflow composed into the larger orchestration graph.

**MVP excludes:** production auth, multi-user operation, vector retrieval, long-term memory, hosted deployment, and advanced model orchestration.

**MVP success looks like:**
- A grader can install dependencies, run the app locally, and observe the graph answer a question end to end.
- The repo contains evidence of one success path, one retry/correction path, and one HITL approval path.
- Each Week 6 lab requirement maps cleanly to code, docs, and logs.

**Walking-skeleton candidate:** A minimal end-to-end slice where the Planner interprets a question, the Tool node runs web search, the Evaluator scores adequacy, a low-score branch triggers exactly one retry with a revised query, and a passing result pauses at a HITL gate before publishing an approved answer to a local canonical-answer artifact. This slice touches state, routing, retries, persistence, human approval, and evidence logging with the least implementation surface.

---

## 6. Success Metrics

| ID | Metric | Target | Measured by |
|----|--------|--------|-------------|
| SM-01 | Lab 6.1 workflow completeness | At least 3 executable graph nodes are implemented and the planner/action/evaluator pattern is visible in code and docs. | `src/agent/` implementation + `docs/architecture.md` |
| SM-02 | Lab 6.2 conditional routing | At least one runtime branch routes on evaluator quality/confidence or tool result state in every graded demo. | Execution logs + graph tests |
| SM-03 | Lab 6.3 retry evidence | At least one run shows a retry with recorded reason, mitigation, and retry count. | `logs/` retry trace |
| SM-04 | Lab 6.3 stop/fallback behavior | When retry threshold is exceeded, the graph routes to fallback or escalation 100% of the time in covered scenarios. | Unit tests + failure trace |
| SM-05 | Lab 6.4 HITL gate | 100% of publish attempts pause for explicit approve/reject input before side effects occur. | CLI transcript and/or Streamlit evidence |
| SM-06 | Evidence package completeness | README, architecture write-up, diagram, success log, retry log, and HITL evidence are all present before submission. | Repo checklist |
| SM-07 | Orchestration clarity | Each node role and transition rule can be explained in a short write-up that matches the implementation. | `docs/architecture.md` review |
| SM-08 | Reproducibility | A clean local setup on Python 3.11+ works with `pip install -r requirements.txt` and no external database. | Setup validation |
| SM-09 | Sub-agent composition | One bounded sub-agent or nested workflow is composed inside the main graph and visible in code and docs. | Implementation review + logs |

---

## 7. Constraints

- **Timeline:** Week 6 course deliverable; the project should be finishable by one student within the class schedule.
- **Budget / team size:** Single-student build with low-cost defaults; prefer free-tier services and `gpt-4o-mini` to control cost.
- **Compliance / regulatory:** No sensitive data handling is required; local demo and mock publish behavior are sufficient.
- **Tech preferences (pre-locked):** Single Python repo, Python 3.11+, LangGraph, interactive mode, CLI primary, Streamlit secondary, OpenAI via `langchain-openai`, Tavily search, and LangGraph `MemorySaver`.
- **Hard architecture constraints:** At least 3 graph nodes, at least 1 conditional branch, at least 1 structured tool invocation node, and at least 1 HITL interrupt before a high-impact action.

---

## 8. Assumptions

| ID | Assumption | Validated? | Risk if wrong |
|----|------------|------------|---------------|
| A-01 | The grader can run local Python 3.11+ and install standard pip dependencies. | Pending | Setup friction could undermine reproducibility. |
| A-02 | A deterministic fake-search fallback is acceptable when network access or API keys are unavailable. | Pending | Offline demos and tests may not satisfy the rubric. |
| A-03 | Writing an approved canonical answer to a local file is an acceptable high-impact publish action for the HITL checkpoint. | Pending | The project may need a different publish action to satisfy Lab 6.4. |
| A-04 | A Streamlit interrupt screenshot plus logs is acceptable evidence for HITL behavior. | Pending | Additional CLI or video evidence may be required. |
| A-05 | Single-user interactive execution is sufficient for the assignment. | Yes | Scope would expand significantly if concurrency were required. |
| A-06 | A bounded nested workflow counts as sub-agent integration for the learning objective. | Pending | A more explicit sub-agent pattern may need to be added later. |

---

## 9. Out of Scope (Project Level)

- Production-grade authentication, authorization, or user account management.
- Multi-user concurrency, collaboration, or shared-session orchestration.
- Vector databases, embeddings pipelines, or retrieval-augmented storage.
- Multi-LLM ensembles, provider arbitration, or advanced model routing.
- Long-term memory beyond session-scoped LangGraph `MemorySaver` checkpoints.
- Remote deployment, hosted infrastructure, or cloud-operations hardening.

---

## 10. Defaults Requiring Confirmation

| ID | Default Adopted | Why this default | Can change later? |
|----|-----------------|------------------|-------------------|
| D-01 | **Project name:** `langgraph-week6-labs` | Matches the confirmed assignment framing and keeps repo naming clear. | Yes |
| D-02 | **Mode:** Interactive | Best fit for demonstrating interrupts, approvals, and visible state transitions live. | Yes |
| D-03 | **Agent domain:** Research/QA agent | Naturally exercises planning, web search, calculator use, evaluation, and publish review. | Yes |
| D-04 | **LLM provider/model:** OpenAI via `langchain-openai`, default **`gpt-5.4`** (overridable via `OPENAI_MODEL` env var) | User-confirmed at Phase 1 gate. Professor-preferred model. Configurable so graders can swap if needed. | Yes |
| D-05 | **UI surface:** CLI primary, Streamlit secondary | CLI is the main runnable interface; Streamlit provides a clean visualization and HITL screenshot surface. | Yes |
| D-06 | **Repo shape:** single Python repo with `src/agent/`, `tools/`, `logs/`, `docs/`, `tests/`, `app.py`, `cli.py` | Keeps implementation, evidence, and docs together in one gradable artifact. | Yes |
| D-07 | **Persistence:** LangGraph `MemorySaver` only | Satisfies interrupt/resume needs without adding a database or infra burden. | Yes |
| D-08 | **Search tool:** Tavily with deterministic fake-search fallback | Supports real demos when online and reproducible tests/offline demos when not. | Yes |
| D-09 | **Dependency manager:** **`uv`** (with `pyproject.toml` + `uv.lock`) | User-confirmed at Phase 1 gate. Professor-preferred manager. Faster, reproducible installs; `uv sync` is the canonical setup command. | Yes |
| D-10 | **High-impact publish action:** write approved canonical answer to a local file/mock artifact | Demonstrates HITL gating safely without relying on external systems. | Yes |
| D-11 | **Deliverable package:** top-level `README.md` linking to `docs/architecture.md`, plus `logs/` with success, retry, and HITL traces | Directly aligns the repo structure with grading needs and required evidence. | Yes |

---

## 11. Open Questions (resolved at Phase 1 gate — see §12)

- ~~Does the grading rubric require a live Tavily/OpenAI network call during grading, or is the deterministic fallback acceptable evidence when offline?~~ → **Resolved Q1**
- ~~Is a file-based "publish" action sufficient for the HITL checkpoint, or should it mimic an external notification?~~ → **Resolved Q2**
- ~~Should the sub-agent appear as its own node, or is a nested workflow inside one node acceptable?~~ → **Resolved Q3**
- ~~Is the Streamlit approval screenshot sufficient HITL evidence, or should we also include a CLI transcript?~~ → **Resolved Q4**
- ~~Does the grader expect minimum automated test coverage?~~ → **Resolved Q5**

---

## 12. Gate Decisions (Phase 1 confirmation)

User instruction at the Phase 1 gate: *"Use your judgment for Q1–Q5. Override D-04 to OpenAI gpt-5.4 and D-09 to uv."* The architecture phase **must treat the following as decided**, not open:

| ID | Question | Decision | Implication for architecture |
|----|----------|----------|------------------------------|
| GD-01 | Live network calls vs offline fallback for grading | **Both paths shipped.** Real Tavily + real OpenAI is the primary path. A deterministic fake-search + stub-LLM mode is gated behind a `--offline` CLI flag and `OFFLINE=1` env var. Every JSONL log line records `mode: live | offline`. | Tools layer needs a `Searcher` interface with two implementations selected at construction time. LLM client is also wrapped so the offline mode can return canned responses for tests and dry-run demos. |
| GD-02 | Form of the high-impact action behind the HITL gate | **File publish + email-mock envelope.** On approval, the agent (a) writes the canonical answer to `outbox/answers/<thread_id>.md` and (b) prints a SMTP-style envelope to stdout AND writes it to `outbox/sent/<thread_id>.eml`. No real network send. | A single `Publisher` node executes both side effects atomically *after* the interrupt resume. Both actions are idempotent (write-with-overwrite keyed by thread_id). |
| GD-03 | Sub-agent shape | **Dedicated node containing a small subgraph.** A "Citation Verifier" sub-agent runs as its own node in the parent graph. Internally it is a 2–3 node subgraph (extract claims → check claim-vs-source alignment → emit verification verdict). Verdict is added to state and consumed by the Evaluator node when deciding retry vs proceed. | Architecture diagram shows the sub-agent as a labeled node. Implementation uses LangGraph `StateGraph` for the inner workflow; the compiled subgraph is added to the parent via `add_node(...)` per docs §LG-Subgraphs. |
| GD-04 | HITL evidence form | **Both CLI transcript and Streamlit screenshot.** CLI transcript is canonical (always reproducible from `logs/`); Streamlit screenshot is supplemental polish. | CLI HITL surface is the primary; Streamlit panel is read-only-plus-approve UI on the same checkpointer. Both must call the same approve/reject channel so logs are uniform. |
| GD-05 | Test coverage expectation | **Targeted pytest, not exhaustive.** Three test categories: (a) graph construction sanity (nodes wired, edges complete, no orphan nodes), (b) router/branch unit tests (each conditional edge tested with crafted state), (c) one end-to-end test using offline mode + stub-LLM that exercises planner → tool → evaluator → retry → HITL approve → publish. | Tests live in `tests/`. Provide a `conftest.py` fixture that builds the graph in offline mode for fast/deterministic runs. CI is out of scope; tests must pass via `uv run pytest`. |

### Default overrides applied at the gate

- **D-04 → `gpt-5.4`** (was `gpt-4o-mini`). Set as default in `.env.example`; configurable via `OPENAI_MODEL`.
- **D-09 → `uv`** (was `pip`+`requirements.txt`). Setup commands move to `uv sync` / `uv run`. Architecture must specify `pyproject.toml` shape and the lockfile (`uv.lock`) commit policy.

All other defaults (D-01, D-02, D-03, D-05, D-06, D-07, D-08, D-10, D-11) are confirmed as written in §10.

---

<!-- The next CRISPY project phase is DOMAIN RESEARCH. -->
<!-- Domain research must remain blind to this document. -->
