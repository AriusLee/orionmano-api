"""Fetch company logos from their website or logo APIs."""

import os
import re
import hashlib
from urllib.parse import urlparse, urljoin

import httpx

from app.config import settings


async def fetch_logo(company_name: str, website: str | None = None) -> str | None:
    """Try multiple strategies to find and download a company logo.

    Users sometimes paste more than one URL (comma/semicolon/whitespace
    separated). Each candidate is tried in order through the full strategy
    chain; the first hit wins.

    Returns the local file path if successful, None otherwise.
    """
    logo_bytes = None
    logo_ext = "png"

    candidates = _candidate_websites(website) or [website]

    for candidate in candidates:
        strategies = [
            lambda c=candidate: _from_clearbit(c),
            lambda c=candidate: _from_google_favicon(c),
            lambda c=candidate: _from_og_image(c),
            lambda c=candidate: _from_favicon(c),
        ]
        for strategy in strategies:
            try:
                result = await strategy()
                if result:
                    logo_bytes, logo_ext = result
                    break
            except Exception:
                continue
        if logo_bytes:
            break

    if not logo_bytes:
        return None

    # Save to uploads/logos/
    logo_dir = os.path.join(settings.UPLOAD_DIR, "logos")
    os.makedirs(logo_dir, exist_ok=True)

    name_hash = hashlib.md5(company_name.encode()).hexdigest()[:12]
    filename = f"{name_hash}.{logo_ext}"
    filepath = os.path.join(logo_dir, filename)

    with open(filepath, "wb") as f:
        f.write(logo_bytes)

    return filepath


def _extract_domain(website: str | None) -> str | None:
    if not website:
        return None
    website = website.strip().strip(",;").strip()
    if not website:
        return None
    if not website.startswith("http"):
        website = "https://" + website
    parsed = urlparse(website)
    # Strip any trailing punctuation that slipped past split (e.g. "example.com,")
    netloc = (parsed.netloc or "").rstrip(",;/ ").strip()
    return netloc or None


def _candidate_websites(raw: str | None) -> list[str]:
    """Split a user-entered website field into individual URL candidates.

    Handles comma/semicolon/whitespace-separated lists. Preserves order so the
    first one the user typed is tried first.
    """
    if not raw:
        return []
    parts = re.split(r"[,;\s]+", raw.strip())
    seen: list[str] = []
    for p in parts:
        p = p.strip().strip(",;").strip()
        if p and p not in seen:
            seen.append(p)
    return seen


async def _from_clearbit(website: str | None) -> tuple[bytes, str] | None:
    """Use Clearbit Logo API (free, no key required)."""
    domain = _extract_domain(website)
    if not domain:
        return None

    url = f"https://logo.clearbit.com/{domain}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200 and len(resp.content) > 500:
            ct = resp.headers.get("content-type", "")
            ext = "png" if "png" in ct else "jpg" if "jpeg" in ct or "jpg" in ct else "png"
            return resp.content, ext
    return None


async def _from_google_favicon(website: str | None) -> tuple[bytes, str] | None:
    """Use Google's favicon service for high-res favicons."""
    domain = _extract_domain(website)
    if not domain:
        return None

    url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200 and len(resp.content) > 500:
            return resp.content, "png"
    return None


async def _from_og_image(website: str | None) -> tuple[bytes, str] | None:
    """Scrape og:image or logo from the company's website HTML."""
    if not website:
        return None
    if not website.startswith("http"):
        website = "https://" + website

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(website, timeout=10.0)
        if resp.status_code != 200:
            return None

        html = resp.text[:50000]

        # Try og:image first
        og_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if not og_match:
            og_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)

        # Try logo in img tags
        if not og_match:
            og_match = re.search(r'<img[^>]+(?:class|id|alt)[^>]*logo[^>]*src=["\']([^"\']+)["\']', html, re.I)
        if not og_match:
            og_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*(?:class|id|alt)[^>]*logo', html, re.I)

        if not og_match:
            return None

        img_url = og_match.group(1)
        if not img_url.startswith("http"):
            img_url = urljoin(website, img_url)

        img_resp = await client.get(img_url, timeout=10.0)
        if img_resp.status_code == 200 and len(img_resp.content) > 500:
            ct = img_resp.headers.get("content-type", "")
            ext = "svg" if "svg" in ct else "png" if "png" in ct else "jpg"
            if ext == "svg":
                return None  # WeasyPrint SVG support is limited
            return img_resp.content, ext

    return None


async def _from_favicon(website: str | None) -> tuple[bytes, str] | None:
    """Fallback: grab /favicon.ico from the website."""
    if not website:
        return None
    if not website.startswith("http"):
        website = "https://" + website

    parsed = urlparse(website)
    favicon_url = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(favicon_url, timeout=10.0)
        if resp.status_code == 200 and len(resp.content) > 500:
            return resp.content, "ico"
    return None
