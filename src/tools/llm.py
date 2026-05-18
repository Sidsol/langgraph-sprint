from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Chat(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 512,
        response_format: dict[str, Any] | None = None,
    ) -> str: ...


class OpenAIChat:
    def __init__(self, model: str | None = None) -> None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("langchain-openai is required for OpenAIChat") from exc

        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-5.4")
        self._client = ChatOpenAI(model=self._model)

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 512,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as exc:
            raise RuntimeError("langchain-core is required for OpenAIChat") from exc

        messages: list[object] = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))

        client = self._client
        if response_format is not None:
            try:
                client = client.bind(response_format=response_format)
            except Exception:
                # If the underlying client doesn't support response_format binding,
                # continue without it — the prompt should still instruct JSON-only output.
                client = self._client

        # Try max_tokens first (older API arg). On GPT-5+ models this is rejected
        # and we must use max_completion_tokens. Retry once before giving up.
        first_err: Exception | None = None
        try:
            response = client.invoke(messages, max_tokens=max_tokens)
        except Exception as exc:
            first_err = exc
            msg = str(exc).lower()
            if "max_tokens" in msg or "max_completion_tokens" in msg or "unsupported parameter" in msg:
                try:
                    response = client.invoke(messages, max_completion_tokens=max_tokens)
                except Exception as exc2:
                    raise RuntimeError(f"OpenAI chat failed: {exc2}") from exc2
            else:
                raise RuntimeError(f"OpenAI chat failed: {exc}") from exc

        return _stringify_content(getattr(response, "content", response))


class StubChat:
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 512,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        del system, max_tokens, response_format
        return f"[STUB] {prompt[:80]}"


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "".join(parts)

    return str(content)


def make_chat(mode: str) -> Chat:
    normalized_mode = mode.lower()
    if normalized_mode == "offline":
        return StubChat()
    if normalized_mode == "live":
        return OpenAIChat(model=os.environ.get("OPENAI_MODEL", "gpt-5.4"))
    raise ValueError(f"unsupported mode: {mode}")


__all__ = ["Chat", "OpenAIChat", "StubChat", "make_chat"]
