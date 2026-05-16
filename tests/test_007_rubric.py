from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_CASES = {
    "01-success-calculator": "t-evidence-001-calc",
    "02-retry-then-pass": "t-evidence-002-retry",
    "03-hitl-reject": "t-evidence-003-reject",
    "04-escalate-budget-exhausted": "t-evidence-004-escalate",
}


def _evidence_log(case: str) -> Path:
    return REPO_ROOT / "docs" / "evidence" / case / f"run-{EVIDENCE_CASES[case]}.jsonl"


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_jsonl_evidence_files_exist() -> None:
    for case in EVIDENCE_CASES:
        log_path = _evidence_log(case)
        assert log_path.exists(), f"missing evidence log: {log_path}"
        assert log_path.read_text(encoding="utf-8").splitlines(), f"empty evidence log: {log_path}"


def test_evidence_retry_log_has_mitigation() -> None:
    events = _read_events(_evidence_log("02-retry-then-pass"))

    assert any(
        event.get("event") == "retry" and "reason" in event and "mitigation" in event
        for event in events
    )


def test_evidence_hitl_emitted_and_resumed() -> None:
    events = _read_events(_evidence_log("01-success-calculator"))

    assert any(event.get("event") == "interrupt_emitted" for event in events)
    assert any(event.get("event") == "interrupt_resumed" for event in events)


def test_evidence_publish_event() -> None:
    events = _read_events(_evidence_log("01-success-calculator"))

    assert any(
        event.get("event") == "publish" and "answer_path" in event and "eml_path" in event
        for event in events
    )


def test_evidence_escalate_event() -> None:
    events = _read_events(_evidence_log("04-escalate-budget-exhausted"))

    assert any(
        event.get("event") == "interrupt_emitted"
        and (
            event.get("node") == "escalate_to_human"
            or ((event.get("state_diff") or {}).get("kind") == "escalation")
        )
        for event in events
    )
