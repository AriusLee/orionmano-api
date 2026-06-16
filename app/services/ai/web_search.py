"""DuckDuckGo web-search client with cached responses.

Cache key is (sha256(normalized_query + max_results), freshness_bucket).
Freshness bucket = floor(unix_days / 90), so the cache naturally invalidates
once per quarter — same window as ARTICLE_REUSE_DAYS in config.

Pattern mirrors translation/cache.py: short-lived session per cache op so
parallel callers don't race the request session.

Provider note: search runs through the keyless `ddgs` library (no API key,
no billing). The provider is isolated to `_ddg_call`; swapping back to Tavily
or over to Serper/Brave/etc. is a single-function change — everything else
(cache, web_search, format_search_results) is provider-agnostic and returns a
normalized list of {title, content, url} dicts."""
import asyncio
import hashlib
import re
import time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

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


def _ddg_search_sync(query: str, max_results: int) -> list[dict]:
    """Blocking DuckDuckGo call. ddgs' text() is synchronous, so callers must
    run this in a thread (see _ddg_call) to avoid blocking the event loop."""
    from ddgs import DDGS

    hits = DDGS().text(query, max_results=max_results) or []
    results: list[dict] = []
    for r in hits:
        results.append({
            "title": r.get("title", ""),
            "content": r.get("body", ""),
            "url": r.get("href", ""),
        })
    return results


async def _ddg_call(query: str, max_results: int) -> list[dict]:
    """Run the keyless DuckDuckGo search off the event loop. On any failure
    (rate-limit, network, library error) return [] so report generation
    degrades to no web context rather than erroring out."""
    try:
        return await asyncio.to_thread(_ddg_search_sync, query, max_results)
    except Exception:
        return []


async def web_search(
    query: str,
    max_results: int = 5,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    use_cache: bool = True,
) -> list[dict]:
    """Search DuckDuckGo, hitting the local cache first.

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

    results = await _ddg_call(query, max_results)

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
