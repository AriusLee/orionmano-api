"""Hero image lookup via Unsplash.

Unsplash API ToS we satisfy here:
  - Photographer + Unsplash credit (returned as `credit` / `credit_url`,
    rendered on every article page).
  - "Trigger download" tracking — we hit `links.download_location` whenever
    we use a photo, per https://unsplash.com/documentation#triggering-a-download.
  - UTM tagging on attribution links.
"""

from __future__ import annotations

import logging
from typing import Optional, TypedDict

import httpx

from app.config import settings


log = logging.getLogger(__name__)


UNSPLASH_API = "https://api.unsplash.com"
UTM_SUFFIX = "utm_source=om-industries&utm_medium=referral"


class HeroImage(TypedDict):
    url: str
    alt: str
    credit: str
    credit_url: str


def _attribution_url(user_html_link: str) -> str:
    sep = "&" if "?" in user_html_link else "?"
    return f"{user_html_link}{sep}{UTM_SUFFIX}"


async def _trigger_download(client: httpx.AsyncClient, download_location: str) -> None:
    """Per Unsplash ToS, ping the download endpoint when we use a photo."""
    try:
        await client.get(
            download_location,
            headers={"Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}"},
            timeout=10.0,
        )
    except Exception as e:
        log.warning("Unsplash download trigger failed: %s", e)


async def _search_one(client: httpx.AsyncClient, query: str, orientation: str) -> Optional[HeroImage]:
    params = {
        "query": query,
        "per_page": 5,
        "orientation": orientation,
        "content_filter": "high",
    }
    headers = {"Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}"}
    try:
        r = await client.get(f"{UNSPLASH_API}/search/photos", params=params, headers=headers)
        r.raise_for_status()
    except Exception as e:
        log.warning("Unsplash search failed for %r: %s", query, e)
        return None

    results = (r.json() or {}).get("results") or []
    if not results:
        return None
    photo = results[0]

    download_location = (photo.get("links") or {}).get("download_location")
    if download_location:
        await _trigger_download(client, download_location)

    user = photo.get("user") or {}
    user_name = user.get("name") or user.get("username") or "Unknown"
    user_html_link = (user.get("links") or {}).get("html") or "https://unsplash.com"
    urls = photo.get("urls") or {}
    image_url = urls.get("regular") or urls.get("full") or urls.get("raw")
    if not image_url:
        return None
    alt = photo.get("alt_description") or photo.get("description") or query
    return {
        "url": image_url,
        "alt": alt[:400],
        "credit": user_name[:200],
        "credit_url": _attribution_url(user_html_link),
    }


async def find_hero_image(
    query: str,
    *,
    orientation: str = "landscape",
    fallbacks: Optional[list[str]] = None,
) -> Optional[HeroImage]:
    """Search Unsplash for a photo. Returns None on any failure.

    `query` is the primary term. `fallbacks` is an ordered list of broader
    terms to try if the primary returns no results. Unsplash treats long
    multi-word queries as phrases — keep each candidate short (2-4 words)
    for hit-rate.
    """
    if not settings.UNSPLASH_ACCESS_KEY:
        log.info("UNSPLASH_ACCESS_KEY not set — skipping hero image lookup")
        return None

    candidates = [c.strip() for c in [query, *(fallbacks or [])] if c and c.strip()]
    if not candidates:
        return None

    async with httpx.AsyncClient(timeout=15.0) as client:
        for cand in candidates:
            hit = await _search_one(client, cand, orientation)
            if hit:
                return hit
    return None
