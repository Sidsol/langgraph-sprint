from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypedDict
from urllib.parse import urlparse


class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str


def domain_of(url: str) -> str:
    return urlparse(url).netloc


def _dedupe_by_url(results: list[SearchResult]) -> list[SearchResult]:
    deduped: list[SearchResult] = []
    seen_urls: set[str] = set()
    for result in results:
        url = str(result.get("url", ""))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(
            {
                "title": str(result.get("title", "")),
                "url": url,
                "snippet": str(result.get("snippet", "")),
            }
        )
    return deduped


class Searcher(ABC):
    @abstractmethod
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError

    def multi_search(self, queries: list[str], *, max_per_query: int = 3) -> list[SearchResult]:
        combined: list[SearchResult] = []
        for query in queries:
            if not query.strip():
                continue
            combined.extend(self.search(query, max_results=max_per_query))
        return _dedupe_by_url(combined)


class TavilySearcher(Searcher):
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

    def multi_search(self, queries: list[str], *, max_per_query: int = 3) -> list[SearchResult]:
        normalized_queries = [query for query in queries if query.strip()]
        if not normalized_queries:
            return []

        def _search_one(query: str) -> list[SearchResult]:
            try:
                return self.search(query, max_results=max_per_query)
            except Exception:
                return []

        max_workers = min(5, len(normalized_queries)) or 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            grouped_results = list(executor.map(_search_one, normalized_queries))

        combined: list[SearchResult] = []
        for query_results in grouped_results:
            combined.extend(query_results)
        return _dedupe_by_url(combined)


class FakeSearcher(Searcher):
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        normalized_query = query.strip() or "query"
        slug = re.sub(r"[^a-z0-9]+", "-", normalized_query.lower()).strip("-") or "query"
        canned_results: list[SearchResult] = [
            {
                "title": "Offline search overview",
                "url": "https://offline.local/search/overview",
                "snippet": f"Offline overview evidence for '{normalized_query}' with deterministic sample support.",
            },
            {
                "title": f"Offline search detail: {slug}",
                "url": f"https://offline.local/search/{slug}",
                "snippet": f"Offline detailed evidence for '{normalized_query}' with deterministic sample support.",
            },
        ]
        return canned_results[: max_results if max_results >= 0 else 0]

    def multi_search(self, queries: list[str], *, max_per_query: int = 3) -> list[SearchResult]:
        return super().multi_search(queries, max_per_query=max_per_query)


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


__all__ = ["FakeSearcher", "SearchResult", "Searcher", "TavilySearcher", "domain_of", "make_searcher"]
