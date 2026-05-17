from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

from langgraph.types import Command

from agent import build_graph, make_initial_state


@dataclass(frozen=True)
class Scenario:
    slug: str
    thread_id: str
    question: str
    resume_payload: dict[str, str] | None


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_EVIDENCE_ROOT = REPO_ROOT / "docs" / "evidence"
LOGS_DIR = REPO_ROOT / "logs"
OUTBOX_ANSWERS_DIR = REPO_ROOT / "outbox" / "answers"
OUTBOX_SENT_DIR = REPO_ROOT / "outbox" / "sent"
CHECKPOINTS_DIR = REPO_ROOT / ".checkpoints"

SCENARIOS: dict[str, Scenario] = {
    "01-success-calculator": Scenario(
        slug="01-success-calculator",
        thread_id="t-evidence-001-calc",
        question="What is 12*12?",
        resume_payload={"decision": "approved"},
    ),
    "02-retry-then-pass": Scenario(
        slug="02-retry-then-pass",
        thread_id="t-evidence-002-retry",
        question="FORCE_RETRY tell me about LangGraph subgraphs",
        resume_payload={"decision": "approved"},
    ),
    "03-hitl-reject": Scenario(
        slug="03-hitl-reject",
        thread_id="t-evidence-003-reject",
        question="What is 7*8?",
        resume_payload={"decision": "rejected"},
    ),
    "04-escalate-budget-exhausted": Scenario(
        slug="04-escalate-budget-exhausted",
        thread_id="t-evidence-004-escalate",
        question="FORCE_WEAK ungroundable claim",
        resume_payload={"decision": "acknowledged"},
    ),
    "05-deep-research-compare": Scenario(
        slug="05-deep-research-compare",
        thread_id="t-evidence-005-deep",
        question="Compare LangGraph and LangChain agent abstractions",
        resume_payload={"decision": "approved"},
    ),
}


def _scenario_paths(scenario: Scenario) -> dict[str, Path]:
    target_dir = DOCS_EVIDENCE_ROOT / scenario.slug
    return {
        "target_dir": target_dir,
        "db": CHECKPOINTS_DIR / f"{scenario.thread_id}.sqlite",
        "db_shm": CHECKPOINTS_DIR / f"{scenario.thread_id}.sqlite-shm",
        "db_wal": CHECKPOINTS_DIR / f"{scenario.thread_id}.sqlite-wal",
        "log": LOGS_DIR / f"run-{scenario.thread_id}.jsonl",
        "answer": OUTBOX_ANSWERS_DIR / f"{scenario.thread_id}.md",
        "eml": OUTBOX_SENT_DIR / f"{scenario.thread_id}.eml",
        "doc_log": target_dir / f"run-{scenario.thread_id}.jsonl",
        "doc_answer": target_dir / "published-answer.md",
        "doc_eml": target_dir / "published-envelope.eml",
    }


def _remove_if_exists(path: Path) -> None:
    path.unlink(missing_ok=True)


def _clean_previous_outputs(scenario: Scenario) -> dict[str, Path]:
    paths = _scenario_paths(scenario)
    paths["target_dir"].mkdir(parents=True, exist_ok=True)
    for key in ("db", "db_shm", "db_wal", "log", "answer", "eml", "doc_log", "doc_answer", "doc_eml"):
        _remove_if_exists(paths[key])
    return paths


def run_scenario(scenario: Scenario) -> None:
    paths = _clean_previous_outputs(scenario)
    graph = build_graph(mode="offline", db_path=str(paths["db"]))
    config = {"configurable": {"thread_id": scenario.thread_id}}
    graph.invoke(make_initial_state(scenario.question, scenario.thread_id, "offline"), config)
    if scenario.resume_payload is not None:
        graph.invoke(Command(resume=scenario.resume_payload), config)

    shutil.copy2(paths["log"], paths["doc_log"])
    if paths["answer"].exists():
        shutil.copy2(paths["answer"], paths["doc_answer"])
    if paths["eml"].exists():
        shutil.copy2(paths["eml"], paths["doc_eml"])

    print(f"generated {scenario.slug} -> {paths['doc_log']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate committed docs/evidence scenarios.")
    parser.add_argument(
        "scenario",
        nargs="?",
        default="all",
        choices=["all", *SCENARIOS],
        help="Scenario slug to regenerate (default: all).",
    )
    args = parser.parse_args()

    selected = SCENARIOS.values() if args.scenario == "all" else [SCENARIOS[args.scenario]]
    for scenario in selected:
        run_scenario(scenario)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
