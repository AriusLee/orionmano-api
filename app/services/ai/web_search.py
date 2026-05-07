"""Tavily web-search client with cached responses.

Cache key is (sha256(normalized_query + max_results), freshness_bucket).
Freshness bucket = floor(unix_days / 90), so the cache naturally invalidates
once per quarter — same window as ARTICLE_REUSE_DAYS in config.

Pattern mirrors translation/cache.py: short-lived session per cache op so
parallel callers don't race the request session."""
import hashlib
import re
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.database import async_session
from app.models.web_search_cache import WebSearchCache

DEFAULT_FRESHNESS_DAYS = 90


def _normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def _cache_key(query: str, max_results: int) -> str:
    return hashlib.sha256(f"{_normalize_query(query)}::n={max_results}".encode("utf-8")).hexdigest()


def _current_bucket(freshness_days: int) -> int:
    return int(time.time() / 86400) // freshness_days


async def _cache_get(query_hash: str, bucket: int) -> list[dict] | None:
    async with async_session() as db:
        row = (await db.execute(
            select(WebSearchCache.results).where(
                WebSearchCache.query_hash == query_hash,
                WebSearchCache.freshness_bucket == bucket,
            )
        )).scalar_one_or_none()
        return row


async def _cache_store(query_hash: str, bucket: int, query: str, results: list[dict]) -> None:
    try:
        async with async_session() as db:
            stmt = insert(WebSearchCache).values(
                query_hash=query_hash,
                freshness_bucket=bucket,
                results=results,
                query_preview=query[:300],
            ).on_conflict_do_nothing(
                index_elements=["query_hash", "freshness_bucket"],
            )
            await db.execute(stmt)
            await db.commit()
    except Exception:
        # Cache is a perf optimization, never block the caller
        pass


async def _tavily_call(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
                "search_depth": "advanced",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

    results: list[dict] = []
    if data.get("answer"):
        results.append({
            "title": "AI Summary",
            "content": data["answer"],
            "url": "",
        })
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "content": r.get("content", ""),
            "url": r.get("url", ""),
        })
    return results


async def web_search(
    query: str,
    max_results: int = 5,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    use_cache: bool = True,
) -> list[dict]:
    """Search Tavily, hitting the local cache first.

    Args:
        freshness_days: Bucket size. Same query within the same N-day window
            returns the cached result. Set lower (e.g. 7) for fast-moving topics.
        use_cache: Set False to force a fresh fetch (e.g. when you suspect
            stale data and want to refresh the cache row).
    """
    if use_cache:
        bucket = _current_bucket(freshness_days)
        qhash = _cache_key(query, max_results)
        hit = await _cache_get(qhash, bucket)
        if hit is not None:
            return hit

    results = await _tavily_call(query, max_results)

    if use_cache and results:
        await _cache_store(qhash, bucket, query, results)

    return results


def format_search_results(results: list[dict]) -> str:
    """Format search results as context string for LLM prompts."""
    if not results:
        return ""
    parts = ["## Web Research Results\n"]
    for i, r in enumerate(results, 1):
        parts.append(f"### Source {i}: {r['title']}")
        if r["url"]:
            parts.append(f"URL: {r['url']}")
        parts.append(r["content"])
        parts.append("")
    return "\n".join(parts)
