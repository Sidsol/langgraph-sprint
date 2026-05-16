---
project: 001-langgraph-week6-labs
document: domain-research
status: complete
created: 2026-05-15
blindness: vision.md not read
---

# Domain Research: LangGraph stateful agent orchestration

## Scope statement
This document surveys the domain space around LangGraph-style stateful agent orchestration, conditional routing, self-correction, and human-in-the-loop review without reading `vision.md` or any other project-specific planning files. It focuses on what exists in the domain today: the core primitives, LangGraph’s current idioms, prior art, observability needs, common failure modes, and the unresolved design questions that the architecture phase must answer.

## 1. The domain in plain terms
Stateful agent orchestration means modeling an agent as an explicit workflow over shared state rather than as a single prompt or an opaque while-loop. In LangGraph terms, the core pieces are: **state** (the shared data model), **nodes** (work units), **edges** (fixed transitions), **conditional edges** (router-driven transitions), **checkpointers** (durable state snapshots), **interrupts** (pause/resume points), and **subgraphs** (nested workflows) [LG-GraphAPI] [LG-Persistence] [LG-Subgraphs].

In practice, this exists because many useful agent systems are not one-shot. They need to:
- carry state across multiple reasoning/tool steps,
- branch based on intermediate results,
- survive failures or restarts,
- wait for humans,
- replay/debug prior executions,
- and stop or escalate when retries are no longer justified [LG-Overview] [LG-Persistence] [synth].

Compared with a single-prompt LLM call, graph-based orchestration adds explicit control flow and durable memory [synth]. Compared with classic ReAct, it keeps the “reason + act” idea but makes control flow first-class: branches are explicit, state is inspectable, checkpoints are durable, and pauses/resumes are part of the runtime rather than prompt glue [ReAct] [LG-Overview] [synth].

Useful primitive definitions:
- **State**: typed shared memory; often `TypedDict`, dataclass, or Pydantic model [LG-GraphAPI] [LG-UseGraphAPI].
- **Reducers**: per-key merge rules; without them, updates overwrite prior values [LG-GraphAPI].
- **Node**: a function that reads state and returns an update; it may also use runtime context, retries, timeouts, or error handlers [LG-UseGraphAPI] [LG-FaultTolerance].
- **Edge**: unconditional next-step connection [LG-GraphAPI].
- **Conditional edge**: router-based branching after a node; the route depends on current state [LG-GraphAPI] [LG-UseGraphAPI] [synth].
- **Checkpointer**: persistence layer that saves checkpoints per super-step/thread so execution can resume later [LG-Persistence].
- **Interrupt**: a pause that surfaces a JSON-serializable payload and waits for external input before continuing [LG-Interrupts].
- **Subgraph**: a graph embedded as a node inside a parent graph, useful for modular or multi-agent composition [LG-Subgraphs].

## 2. LangGraph as a concrete framework
LangGraph positions itself as a **low-level orchestration framework for long-running, stateful agents**, with durable execution, human-in-the-loop, memory, and LangSmith debugging as the main value proposition [LG-Overview] [LG-README].

Current core API shape:
- `StateGraph(...)` is the primary builder for graphs over typed state [LG-GraphAPI].
- `add_node(...)` attaches node functions; current docs also highlight node-level `retry_policy`, `timeout`, and `error_handler`, which means node definition is now where much of resilience policy lives [LG-UseGraphAPI] [LG-FaultTolerance].
- `add_edge(...)` defines fixed transitions [LG-GraphAPI].
- `add_conditional_edges(...)` is the standard router hook for state-dependent branching; practically, the router inspects state and selects the next node(s) [LG-GraphAPI] [LG-UseGraphAPI] [synth].
- `Command(...)` is the control-flow object used to combine state updates with routing (`goto=...`) and to resume paused graphs (`resume=...`) [LG-Interrupts] [LG-UseGraphAPI].

State idioms that appear current in the docs:
- Use `TypedDict` for simple, fast state schemas; use Pydantic only when runtime validation is worth the overhead [LG-GraphAPI] [LG-UseGraphAPI].
- Use reducers via `Annotated[..., reducer]` for append/merge semantics; otherwise updates overwrite prior values [LG-GraphAPI].
- Use `MessagesState` or `add_messages` when chat history needs append/update semantics rather than blind list overwrite [LG-GraphAPI] [LG-UseGraphAPI].

Persistence / checkpointers:
- Compiling with a checkpointer causes LangGraph to save a checkpoint at every super-step, organized by `thread_id` [LG-Persistence].
- `thread_id` is effectively the resume key; if it changes, the runtime starts a new thread rather than resuming the old one [LG-Persistence] [LG-Interrupts].
- The persistence docs show current official use of `InMemorySaver` for local/dev persistence, and source keeps `MemorySaver = InMemorySaver` as a backward-compatibility alias [LG-Persistence] [LG-MemorySource].
- `SqliteSaver` remains a lightweight persistent option; its source/docs also point to `AsyncSqliteSaver` when async support is needed [LG-SqliteSource].
- `PostgresSaver` is the durable Postgres-backed option in the current checkpoint packages [LG-PostgresSource].

Interrupt / HITL specifics:
- **Dynamic interrupts** use `interrupt()` inside node or tool code. This is the canonical product-facing HITL mechanism because it can pause at exactly the point where external input is needed and resumes with `Command(resume=...)` [LG-Interrupts].
- **Static interrupts** use `interrupt_before` / `interrupt_after` at compile time or invocation time. These act more like breakpoints and are especially useful for debugging, stepping, and fixed review pauses [LG-Interrupts].
- On resume, LangGraph restarts the interrupted node from the beginning, so any code before the `interrupt()` call runs again; this makes idempotency a first-class concern [LG-Interrupts].
- Interrupt payloads surface as `__interrupt__` in v1/default-style results and as `.interrupts` / streamed `interrupts` fields with `version="v2"`; this is an important version-drift detail when reading tutorials [LG-Interrupts].

Subgraphs:
- If parent and child share the same state keys, the compiled subgraph can be added directly as a node.
- If the schemas differ, the parent usually wraps the subgraph in a transformation node that maps state in and out [LG-Subgraphs].
- Persistence uses `checkpoint_ns` to distinguish parent vs nested subgraph checkpoints [LG-Persistence].

Version-drift notes worth carrying into architecture:
- The docs surface has moved to `docs.langchain.com/oss/python/langgraph/...`, but legacy references still appear in source/comments and older tutorials (for example, the SQLite checkpointer source still references `langchain-ai.github.io/langgraph/...`) [LG-SqliteSource].
- Current source defines `InMemorySaver` and preserves `MemorySaver` as a compatibility alias; examples and tutorials in the ecosystem may use either name [LG-MemorySource] [LG-Interrupts] [LG-Persistence].
- Interrupt examples now explicitly distinguish v1/default output shape from `version="v2"` streaming/results, so copy-pasting old examples can fail unless resume/result handling is updated [LG-Interrupts].

## 3. Prior art and patterns
- **ReAct** — Interleave reasoning traces and actions so the model can plan, act, observe, and continue; a foundational agent-loop pattern, but still basically linear without explicit graph runtime support [ReAct].
- **Planner → Executor → Evaluator** — Separate decomposition, execution, and verification into distinct roles/steps; usually easier to observe and to gate than a monolithic agent [PlanAndSolve] [synth].
- **Plan-and-Solve** — Make a plan first, then execute subtasks; motivated by reducing missing-step errors in zero-shot reasoning [PlanAndSolve].
- **Reflexion** — Use feedback plus reflective memory to retry from mistakes without fine-tuning the model weights [Reflexion].
- **Self-Refine** — Same-model generator/critic/refiner loop that iteratively improves drafts [SelfRefine].
- **LATS (Language Agent Tree Search)** — Extend agent reasoning from linear rollouts into tree search with LM-based evaluation and reflection [LATS].
- **Toolformer / tool-calling** — Treat API/tool use as a core capability rather than a post-processing hack; modern agent frameworks operationalize this with schema-defined tools [Toolformer] [OpenAI-FunctionCalling] [Anthropic-ToolUse].
- **Structured output** — Constrain model outputs to JSON Schema / typed objects so downstream control flow can route on parsed state instead of brittle string parsing [OpenAI-StructuredOutputs] [OpenAI-FunctionCalling].
- **Human approval gate** — Pause before an irreversible or high-risk action, let a human approve/edit/reject, then resume execution with that decision [LG-Interrupts].

A practical observation: LangGraph’s official examples directory mirrors these patterns directly (`react-agent-from-scratch`, `tool-calling`, `plan-and-execute`, `reflection`, `reflexion`, `lats`, `human_in_the_loop`, `subgraph.ipynb`), which makes the framework useful both as runtime and as a pattern library [LG-Examples].

## 4. Self-correction design space
There are at least five distinct retry/correction strategies in this domain:

1. **Transport retry** — Same node, same logic, transient failure handling with exponential backoff/jitter for network/API faults. LangGraph directly supports this with `RetryPolicy`, including backoff settings and exception filters [LG-FaultTolerance].
2. **Retry with reflection** — Have an evaluator/critic explain what went wrong, then let the agent try again with that critique in state or memory [Reflexion] [SelfRefine].
3. **Retry with different tool / degraded path** — If the primary tool or provider keeps failing, switch tools, models, or fallback branches on later attempts [LG-FaultTolerance] [synth].
4. **Retry with stronger structure** — Move from free-text output to structured output/tool-calling so failure becomes schema-validation or tool error rather than fuzzy parsing failure [OpenAI-StructuredOutputs] [OpenAI-FunctionCalling] [Anthropic-ToolUse].
5. **Escalate to human** — Treat repeated failure as a signal that the system is at its limit, not a prompt to keep looping [LG-Interrupts] [synth].

Good stop conditions:
- `max_attempts` / retry budget [LG-FaultTolerance]
- wall-clock or idle timeout [LG-FaultTolerance]
- explicit success invariant satisfied (e.g., schema validates, evaluator passes) [synth]
- cost/token cap [synth]
- confidence or agreement threshold [synth]
- mandatory human escalation after N failed tries [synth]

What should be logged for retries:
- node name,
- attempt number,
- exception class / evaluator failure reason,
- whether backoff was applied,
- tool/model used on that attempt,
- branch taken after retry budget exhaustion,
- final disposition: success, fallback, or human escalation [LG-FaultTolerance] [synth].

Most important architectural rule: retries should distinguish **transient failures** from **logic bugs**. LangGraph’s default retry behavior already avoids retrying many programmer-error classes; that is a useful default to preserve rather than override casually [LG-FaultTolerance].

## 5. Human-in-the-loop design space
Common interrupt placements:

| Interrupt point | Best when | Main trade-off |
|---|---|---|
| **Before tool call** | The tool is side-effectful or expensive (email, purchase, DB write, ticket update) | Prevents bad actions early, but adds friction to common paths [LG-Interrupts] |
| **After draft generation, before final write** | A human should edit language or confirm a recommendation | Better UX for review workflows, but the model may have already spent tokens on a draft [LG-Interrupts] |
| **At evaluator escalation** | Most cases should auto-resolve, but ambiguous or low-confidence ones need human judgment | Efficient for scale, but humans see harder edge cases only [synth] |
| **As static `interrupt_before` / `interrupt_after` breakpoints** | Debugging, demos, step-through review, or fixed governance checkpoints | Simpler to wire, but less expressive than dynamic `interrupt()` [LG-Interrupts] |

Resume mechanics:
- Resume always requires the **same `thread_id`** that created the checkpoint [LG-Interrupts] [LG-Persistence].
- `Command(resume=value)` feeds the human response back to the paused node as the return value of `interrupt()` [LG-Interrupts].
- Multiple simultaneous interrupts can be resumed together by mapping interrupt IDs to resume values [LG-Interrupts].
- Because the node restarts from the beginning, any pre-interrupt side effects must be idempotent or moved after the pause [LG-Interrupts].

How to surface the interrupt to a human:
- **CLI prompt** — fastest for local labs and demos; weak audit trail/context richness [synth].
- **Web UI button/form** — best for structured review, evidence display, and auditability; highest implementation cost [synth].
- **Slack/Teams approval** — convenient for operational teams, but context can be fragmented and approvals can become shallow [synth].
- **Queue/ticket system** — strongest audit/process integration, but slower turnaround [synth].

Practical guidance:
- Use **dynamic `interrupt()`** for real product review/approval flows.
- Use **static interrupts** when you want breakpoints or fixed review hooks.
- Put interrupts **before irreversible side effects**, not after them.

## 6. Observability requirements
A stateful agent is only debuggable if the runtime can answer: **what node ran, what state changed, why the branch changed, what tools were called, and where/why execution paused**.

Minimum logging envelope:
- run/thread identifiers (`thread_id`, run/checkpoint/task IDs) [LG-Persistence] [LG-FaultTolerance]
- node entry/exit timestamps [synth]
- state update written by each node; ideally a diff, not only full snapshots [LG-Persistence] [synth]
- branch/router decision and selected destination [synth]
- tool name, arguments, result, latency, and exception [OpenAI-FunctionCalling] [Anthropic-ToolUse] [synth]
- retry attempt count and retry reason [LG-FaultTolerance]
- timeout events [LG-FaultTolerance]
- interrupt emitted / interrupt resumed, including human decision payload [LG-Interrupts]
- final outcome plus cost/token metadata where available [LangSmith] [synth]

Two practical observability options:
1. **LangSmith tracing** — the official LangGraph materials position LangSmith as the main debugging/observability companion for agent trajectories, state transitions, and runtime visibility [LG-Overview] [LG-README] [LangSmith].
2. **JSONL event logs** — a dependency-free alternative where every node/interrupt/retry writes one JSON object per line. This is less polished than LangSmith but portable, grep-able, and easy to archive [synth].

A minimal JSONL event shape could be:
```json
{"ts":"2026-05-15T12:00:00Z","thread_id":"t-123","node":"tool_router","event":"branch","attempt":1,"decision":"web_search","state_diff":{"selected_tool":"web_search"}}
```
Use JSONL when the project needs low ceremony, offline review, or no hosted observability dependency [synth].

## 7. Pitfalls and anti-patterns
- **Infinite correction loops** — Always carry an attempt counter or explicit stop branch to `END`; never let evaluator failure imply unlimited retry [synth].
- **Unhandled tool exceptions blowing up the graph** — Put network/API work behind `retry_policy` and `error_handler`, and route to fallback/human nodes after exhaustion [LG-FaultTolerance].
- **State overwrite bugs** — If a field is meant to accumulate, define a reducer (`Annotated[..., operator.add]` or `add_messages`) instead of relying on defaults [LG-GraphAPI] [LG-UseGraphAPI].
- **Chat-history corruption** — Prefer `add_messages`/`MessagesState` over raw list concatenation when messages may be updated as well as appended [LG-GraphAPI].
- **Wrong `thread_id` on resume** — Reusing the wrong thread resumes the wrong conversation; generating a fresh thread on resume loses the paused state entirely [LG-Persistence] [LG-Interrupts].
- **Non-idempotent side effects before `interrupt()`** — The node will rerun from the top, so create/update/send operations before the interrupt can duplicate work; move them after approval or make them idempotent [LG-Interrupts].
- **Catching the interrupt exception accidentally** — Do not wrap `interrupt()` in a broad `try/except`, or the pause signal never reaches the runtime [LG-Interrupts].
- **Changing the order of multiple interrupts in one node** — Resume matching is order-sensitive; keep interrupt ordering deterministic [LG-Interrupts].
- **Passing non-serializable interrupt payloads** — Keep interrupt values JSON-serializable so they work across checkpointers and UIs [LG-Interrupts].
- **Blocking the event loop inside async graphs** — Sync I/O inside async nodes can stall the whole workflow; use async libraries or isolate sync work safely [LG-FaultTolerance] [synth].
- **Over-aggressive retries masking real bugs** — Do not retry validation, schema, or programmer errors as though they were transient infrastructure faults [LG-FaultTolerance] [synth].

## 8. Adjacent ecosystem
- **Raw LangChain agents** — Higher-level prebuilt agent loops on top of LangGraph; faster to start, less explicit when you need custom orchestration control [LG-Overview].
- **AutoGen** — Conversation-centric multi-agent collaboration framework; stronger agent-chat ergonomics, less graph-first control surface [synth].
- **CrewAI** — Opinionated role/crew workflow framework focused on multi-agent teamwork and business automation [synth].
- **LlamaIndex Workflows** — Event-driven workflow system with strong RAG adjacency and step/event composition rather than LangGraph’s state-graph mental model [synth].
- **PydanticAI** — Type-safe agent framework that excels at structured outputs, validation, and Pythonic tool registration, but is not primarily a durable graph runtime [synth].

## 9. Educational framing notes
This domain is usually taught best as a **walking skeleton** rather than as a full agent stack on day one [synth]:

1. Start with `START -> model node -> END` and a tiny typed state.
2. Add a tool node and a fixed edge.
3. Add conditional routing.
4. Add persistence/checkpointer plus stable `thread_id`.
5. Add retries/timeouts and an evaluator.
6. Add `interrupt()` for approval/edit flows.
7. Only then introduce subgraphs / multi-agent composition.

That sequence matches how learners build intuition: first explicit state, then routing, then failure handling, then human review. It also lines up well with LangGraph’s official learning materials: the repo README points learners to LangChain Academy, and the examples directory includes concrete notebooks for ReAct, structured output, tool calling, human-in-the-loop, plan-and-execute, reflection/reflexion, LATS, and subgraphs [LG-README] [LG-Examples].

## 10. Open research questions
The blindness constraint prevents resolving these product-specific questions here; the architecture phase should answer them after comparing this document to the vision:

1. What is the **canonical state schema**: raw message history, task-centric typed state, or a hybrid?
2. Which steps are **high-risk enough to require human approval**, and which can auto-execute?
3. Is this system expected to run as a **single-agent graph with evaluators** or as a **multi-agent/subgraph composition**?
4. What durability tier is required: **in-memory only**, **SQLite**, or **Postgres**?
5. What is the intended **human review surface**: CLI, web UI, chat approval, or back-office queue?
6. What retry ceilings are acceptable for **cost**, **latency**, and **attempt count**?
7. What evidence should an evaluator use to decide **retry vs escalate to human**?
8. Is hosted observability (e.g., LangSmith) acceptable, or must tracing stay local via JSONL / local storage only?

## Citations
- [LG-Overview] https://docs.langchain.com/oss/python/langgraph/overview
- [LG-GraphAPI] https://docs.langchain.com/oss/python/langgraph/graph-api
- [LG-UseGraphAPI] https://docs.langchain.com/oss/python/langgraph/use-graph-api
- [LG-Persistence] https://docs.langchain.com/oss/python/langgraph/persistence
- [LG-Interrupts] https://docs.langchain.com/oss/python/langgraph/interrupts
- [LG-Subgraphs] https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- [LG-FaultTolerance] https://docs.langchain.com/oss/python/langgraph/fault-tolerance
- [LG-README] https://github.com/langchain-ai/langgraph
- [LG-Examples] https://github.com/langchain-ai/langgraph/tree/main/examples
- [LG-MemorySource] https://github.com/langchain-ai/langgraph/blob/076e2a3627206f5a1aef573aaca4a01e5af897ca/libs/checkpoint/langgraph/checkpoint/memory/__init__.py
- [LG-SqliteSource] https://github.com/langchain-ai/langgraph/blob/076e2a3627206f5a1aef573aaca4a01e5af897ca/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py
- [LG-PostgresSource] https://github.com/langchain-ai/langgraph/blob/076e2a3627206f5a1aef573aaca4a01e5af897ca/libs/checkpoint-postgres/langgraph/checkpoint/postgres/__init__.py
- [ReAct] https://arxiv.org/abs/2210.03629
- [PlanAndSolve] https://arxiv.org/abs/2305.04091
- [Reflexion] https://arxiv.org/abs/2303.11366
- [SelfRefine] https://arxiv.org/abs/2303.17651
- [Toolformer] https://arxiv.org/abs/2302.04761
- [LATS] https://arxiv.org/abs/2310.04406
- [OpenAI-FunctionCalling] https://developers.openai.com/api/docs/guides/function-calling
- [OpenAI-StructuredOutputs] https://developers.openai.com/api/docs/guides/structured-outputs
- [Anthropic-ToolUse] https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview
- [LangSmith] https://www.langchain.com/langsmith
- [synth] Synthesized from general agent-engineering practice and from combining the cited sources where no single primary source states the claim directly.
