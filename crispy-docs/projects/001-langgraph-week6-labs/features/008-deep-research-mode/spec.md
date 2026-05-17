---
feature: 008-deep-research-mode
project: 001-langgraph-week6-labs
document: spec
status: complete
created: 2026-05-17
updated: 2026-05-17
---

# Spec: deep-research-mode

## Goal
Mirror crispy-plugin domain-research structure inside the existing search path without breaking any shallow-mode runtime or test contract.

## Delivered scope
- add additive state fields for `research_report`, `research_depth`, and `research_plan`
- let `planner` choose shallow vs deep search and derive deterministic offline sub-queries
- extend `Searcher` with `multi_search()` plus URL-domain helpers and dedupe-by-URL behavior
- build structured `ResearchReport` payloads in `search_tool` and mirror `direct_answer` into `draft_answer`
- validate per-fact cited sources inside `citation_verifier`, including source-diversity boosts and synthesized-claim penalties
- render structured markdown/email output for deep mode while preserving legacy publishing for shallow answers
- add deterministic tests, docs updates, and a committed deep-research evidence scenario

## Guardrails
- keep all pre-existing tests unchanged and passing
- keep offline behavior deterministic for the same input question
- add no new dependencies and preserve `FORCE_RETRY` / `FORCE_WEAK` compatibility
