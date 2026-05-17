from __future__ import annotations

import os
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.state import ResearchReport

OUTBOX_ROOT = Path("outbox")


def _render_markdown_sources(sources: list[dict[str, Any]]) -> list[str]:
    if not sources:
        return ["- None"]

    lines: list[str] = []
    for source in sources:
        title = str(source.get("title", "Untitled source"))
        url = str(source.get("url", ""))
        snippet = str(source.get("snippet", "")).strip()
        lines.append(f"- [{title}]({url})")
        if snippet:
            lines.append(f"  - Snippet: {snippet}")
    return lines


def _render_text_sources(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "- None"

    lines: list[str] = []
    for source in sources:
        title = str(source.get("title", "Untitled source"))
        url = str(source.get("url", ""))
        snippet = str(source.get("snippet", "")).strip()
        lines.append(f"- {title} ({url})")
        if snippet:
            lines.append(f"  Snippet: {snippet}")
    return "\n".join(lines)


def _format_citation_list(citations: list[int]) -> str:
    if not citations:
        return "none"
    ordered: list[int] = []
    for citation in citations:
        if citation not in ordered:
            ordered.append(citation)
    return ", ".join(f"[{citation + 1}]" for citation in ordered)


def _format_source_idx(source_idx: int | None) -> str:
    return f"[{source_idx + 1}]" if source_idx is not None else "—"


def _markdown_escape(text: str) -> str:
    return text.replace("|", "\\|")


def _should_render_structured(research_report: ResearchReport | None, research_depth: str) -> bool:
    return research_report is not None and research_depth == "deep"


def _render_structured_markdown(
    thread_id: str,
    question: str,
    mode: str,
    timestamp_text: str,
    final_text: str,
    research_report: ResearchReport,
    sources: list[dict[str, Any]],
) -> str:
    direct_answer = final_text or research_report["direct_answer"]
    lines = [f"# Answer to: {question}", "", "## Direct Answer", "", direct_answer, ""]

    if research_report["key_facts"]:
        lines.extend(["## Key Facts", ""])
        for index, fact in enumerate(research_report["key_facts"], start=1):
            synth_suffix = " [synth]" if fact["synthesized"] else ""
            lines.append(
                f"{index}. {fact['claim']}  *(sources: {_format_citation_list(fact['citations'])}; confidence: {fact['confidence']:.2f})*{synth_suffix}"
            )
        lines.append("")

    if research_report["perspectives"]:
        lines.extend(["## Different Perspectives", ""])
        lines.extend(f"- {perspective}" for perspective in research_report["perspectives"])
        lines.append("")

    if research_report["unknowns"]:
        lines.extend(["## Open Questions / Unknowns", ""])
        lines.extend(f"- {unknown}" for unknown in research_report["unknowns"])
        lines.append("")

    if research_report["glossary"]:
        lines.extend(["## Glossary", "", "| Term | Definition | Source |", "|---|---|---|"])
        for entry in research_report["glossary"]:
            lines.append(
                f"| {_markdown_escape(entry['term'])} | {_markdown_escape(entry['definition'])} | {_format_source_idx(entry['source_idx'])} |"
            )
        lines.append("")

    if sources:
        lines.extend(["## Sources", ""])
        for index, source in enumerate(sources, start=1):
            title = str(source.get("title", "Untitled source"))
            url = str(source.get("url", ""))
            lines.append(f"{index}. {title} — {url}")
        lines.append("")

    if research_report["sources_by_domain"]:
        lines.extend(["## Source Diversity", ""])
        for domain, count in sorted(research_report["sources_by_domain"].items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {domain}: {count}")
        lines.append("")

    lines.extend(["---", f"*thread_id: {thread_id} · mode: {mode} · timestamp: {timestamp_text}*"])
    return "\n".join(lines)


def _render_structured_text(
    thread_id: str,
    question: str,
    mode: str,
    timestamp_text: str,
    final_text: str,
    research_report: ResearchReport,
    sources: list[dict[str, Any]],
) -> str:
    direct_answer = final_text or research_report["direct_answer"]
    lines = [f"Answer to: {question}", "", "Direct Answer:", direct_answer, ""]

    if research_report["key_facts"]:
        lines.extend(["Key Facts:", ""])
        for index, fact in enumerate(research_report["key_facts"], start=1):
            synth_suffix = " [synth]" if fact["synthesized"] else ""
            lines.append(
                f"{index}. {fact['claim']} (sources: {_format_citation_list(fact['citations'])}; confidence: {fact['confidence']:.2f}){synth_suffix}"
            )
        lines.append("")

    if research_report["perspectives"]:
        lines.extend(["Different Perspectives:", ""])
        lines.extend(f"- {perspective}" for perspective in research_report["perspectives"])
        lines.append("")

    if research_report["unknowns"]:
        lines.extend(["Open Questions / Unknowns:", ""])
        lines.extend(f"- {unknown}" for unknown in research_report["unknowns"])
        lines.append("")

    if research_report["glossary"]:
        lines.extend(["Glossary:", ""])
        for entry in research_report["glossary"]:
            lines.append(f"- {entry['term']}: {entry['definition']} (Source: {_format_source_idx(entry['source_idx'])})")
        lines.append("")

    if sources:
        lines.extend(["Sources:", ""])
        for index, source in enumerate(sources, start=1):
            title = str(source.get("title", "Untitled source"))
            url = str(source.get("url", ""))
            lines.append(f"{index}. {title} — {url}")
        lines.append("")

    if research_report["sources_by_domain"]:
        lines.extend(["Source Diversity:", ""])
        for domain, count in sorted(research_report["sources_by_domain"].items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {domain}: {count}")
        lines.append("")

    lines.append(f"thread_id: {thread_id} · mode: {mode} · timestamp: {timestamp_text}")
    return "\n".join(lines)


def _render_legacy_markdown(
    thread_id: str,
    final_text: str,
    sources: list[dict[str, Any]],
    question: str,
    mode: str,
    timestamp_text: str,
) -> str:
    markdown_lines = [
        "# Published Answer",
        "",
        f"- Thread ID: `{thread_id}`",
        f"- Timestamp: {timestamp_text}",
        f"- Mode: {mode}",
        "",
        "## Question",
        "",
        question,
        "",
        "## Answer",
        "",
        final_text,
        "",
        "## Sources",
        "",
        *_render_markdown_sources(sources),
        "",
    ]
    return "\n".join(markdown_lines)


def _render_legacy_text(
    thread_id: str,
    final_text: str,
    sources: list[dict[str, Any]],
    question: str,
    mode: str,
    timestamp_text: str,
) -> str:
    return "\n".join(
        [
            f"Thread ID: {thread_id}",
            f"Mode: {mode}",
            f"Timestamp: {timestamp_text}",
            "",
            "Question:",
            question,
            "",
            "Answer:",
            final_text,
            "",
            "Sources:",
            _render_text_sources(sources),
            "",
        ]
    )


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def publish_atomic(
    thread_id: str,
    final_text: str,
    sources: list[dict[str, Any]],
    question: str,
    mode: str,
    research_report: ResearchReport | None = None,
    research_depth: str = "shallow",
) -> tuple[str, str]:
    timestamp = datetime.now(timezone.utc)
    timestamp_text = timestamp.isoformat()
    if _should_render_structured(research_report, research_depth):
        markdown_body = _render_structured_markdown(
            thread_id,
            question,
            mode,
            timestamp_text,
            final_text,
            research_report,
            sources,
        )
        text_body = _render_structured_text(
            thread_id,
            question,
            mode,
            timestamp_text,
            final_text,
            research_report,
            sources,
        )
    else:
        markdown_body = _render_legacy_markdown(thread_id, final_text, sources, question, mode, timestamp_text)
        text_body = _render_legacy_text(thread_id, final_text, sources, question, mode, timestamp_text)

    message = EmailMessage()
    message["From"] = "agent@local"
    message["To"] = "reviewer@local"
    message["Subject"] = f"Published answer for {thread_id}"
    message["Date"] = format_datetime(timestamp)
    message.set_content(text_body)
    eml_body = message.as_string()

    answer_path = OUTBOX_ROOT / "answers" / f"{thread_id}.md"
    eml_path = OUTBOX_ROOT / "sent" / f"{thread_id}.eml"
    _write_atomic(answer_path, markdown_body)
    _write_atomic(eml_path, eml_body)
    print(eml_body)
    return str(answer_path), str(eml_path)
