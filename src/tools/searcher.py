from __future__ import annotations

import os
from typing import Any, Protocol, TypedDict, runtime_checkable


class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str


@runtime_checkable
class Searcher(Protocol):
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]: ...


class TavilySearcher:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("TavilySearcher requires a non-empty api_key")

        try:
            from tavily import TavilyClient
        except ImportError as exc:
            raise RuntimeError("tavily-python is required for TavilySearcher") from exc

        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        try:
            response = self._client.search(query=query, max_results=max_results)
        except TypeError:
            try:
                response = self._client.search(query, max_results=max_results)
            except Exception as exc:
                raise RuntimeError(f"Tavily search failed: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Tavily search failed: {exc}") from exc

        results = response.get("results") if isinstance(response, dict) else None
        if not isinstance(results, list):
            raise RuntimeError("Tavily search returned an invalid response shape")

        normalized: list[SearchResult] = []
        for item in results:
            normalized.append(_normalize_result(item))

        return normalized


class FakeSearcher:
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        canned_results: list[SearchResult] = [
            {
                "title": "Offline search result 1",
                "url": "https://offline.local/search/1",
                "snippet": f"Offline evidence packet 1 for '{query}' with deterministic sample support.",
            },
            {
                "title": "Offline search result 2",
                "url": "https://offline.local/search/2",
                "snippet": f"Offline evidence packet 2 for '{query}' with deterministic sample support.",
            },
        ]
        return canned_results[: max_results if max_results >= 0 else 0]


def _normalize_result(item: Any) -> SearchResult:
    if not isinstance(item, dict):
        raise RuntimeError("Tavily search returned a non-dict result")

    title = str(item.get("title") or "")
    url = str(item.get("url") or "")
    snippet = str(item.get("snippet") or item.get("content") or item.get("raw_content") or "")
    return {"title": title, "url": url, "snippet": snippet}


def make_searcher(mode: str) -> Searcher:
    normalized_mode = mode.lower()
    if normalized_mode == "offline":
        return FakeSearcher()
    if normalized_mode == "live":
        return TavilySearcher(api_key=os.environ["TAVILY_API_KEY"])
    raise ValueError(f"unsupported mode: {mode}")


__all__ = ["FakeSearcher", "SearchResult", "Searcher", "TavilySearcher", "make_searcher"]
