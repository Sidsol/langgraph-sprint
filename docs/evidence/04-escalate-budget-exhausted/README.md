# 04-escalate-budget-exhausted

This committed run forces weak evidence on both attempts so the evaluator exhausts the retry budget and hands off through the escalation interrupt. Thread ID: `t-evidence-004-escalate`. Question: `FORCE_WEAK ungroundable claim`.

## Regenerate
```powershell
uv run python scripts\regenerate_evidence.py 04-escalate-budget-exhausted
```

## Rubric artifact satisfied
- Self-correction loop evidence with retry/fallback behavior
- Evidence of one human-in-the-loop interrupt in action
