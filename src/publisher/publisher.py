from __future__ import annotations

import os
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

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
) -> tuple[str, str]:
    timestamp = datetime.now(timezone.utc)
    timestamp_text = timestamp.isoformat()
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
    markdown_body = "\n".join(markdown_lines)

    message = EmailMessage()
    message["From"] = "agent@local"
    message["To"] = "reviewer@local"
    message["Subject"] = f"Published answer for {thread_id}"
    message["Date"] = format_datetime(timestamp)
    message.set_content(
        "\n".join(
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
    )
    eml_body = message.as_string()

    answer_path = OUTBOX_ROOT / "answers" / f"{thread_id}.md"
    eml_path = OUTBOX_ROOT / "sent" / f"{thread_id}.eml"
    _write_atomic(answer_path, markdown_body)
    _write_atomic(eml_path, eml_body)
    print(eml_body)
    return str(answer_path), str(eml_path)
