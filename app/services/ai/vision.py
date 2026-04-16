"""Vision-based document classification.

Used for image uploads (photos, screenshots) and scanned PDFs where the text
layer is empty. Returns a list of matching taxonomy slugs — one doc can satisfy
multiple slots (e.g. an org chart image that also shows the cap table).
"""
import base64
import json
import io
from typing import Iterable

import fitz  # pymupdf
from anthropic import AsyncAnthropic

from app.config import settings


VISION_MODEL = "claude-haiku-4-5-20251001"

VALID_CATEGORIES = {
    "audit_report",
    "management_accounts",
    "tax_return",
    "org_chart",
    "cap_table",
    "board_minutes",
    "shareholder_agreement",
    "material_contract",
    "company_profile",
    "projections",
    "legal",
    "prospectus",
    "interview",
    "other",
}

_SYSTEM = """You are a corporate document classifier. Inspect the image and return
a JSON object with the taxonomy slugs that apply. A single image can match
multiple categories — for example, an organization chart that also lists
shareholders with percentages satisfies BOTH org_chart and cap_table. Be
generous but accurate: only include a category when the visual evidence
clearly supports it.

Taxonomy:
- audit_report — auditor's opinion, audited financial statements
- management_accounts — interim/unaudited P&L or balance sheet
- tax_return — tax filings, CP204, LHDN forms, tax certificates
- org_chart — organization chart, group/corporate structure, holding diagram
- cap_table — shareholder register, shareholding breakdown, share ledger
- board_minutes — board minutes, directors resolutions
- shareholder_agreement — SHA, investment agreement, term sheet
- material_contract — customer/supplier/licensing/franchise contracts
- company_profile — pitch deck, corporate profile, company overview slides
- projections — financial projections, budgets, forecasts
- legal — legal opinion, incorporation certificate, SSM filings, regulatory
- prospectus — prospectus, offering memorandum, S-1/F-1
- interview — management interview transcripts, Q&A notes
- other — anything that does not clearly match the above

Return strictly this JSON shape:
{"categories": ["slug1", "slug2"], "summary": "one-line description of what the image shows"}

If nothing matches, return {"categories": ["other"], "summary": "..."}.
"""


def _get_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=60.0)


def _sanitize(slugs: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for s in slugs:
        if not isinstance(s, str):
            continue
        s = s.strip().lower()
        if s in VALID_CATEGORIES and s not in seen:
            seen.append(s)
    return seen


async def _classify_image_bytes(image_bytes: bytes, media_type: str) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        return {"categories": [], "summary": "", "error": "ANTHROPIC_API_KEY not configured"}

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    client = _get_client()
    msg = await client.messages.create(
        model=VISION_MODEL,
        max_tokens=512,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": "Classify this document image."},
                ],
            }
        ],
    )
    # Extract text
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
    cleaned = text
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {"categories": [], "summary": text[:200], "error": "parse_error"}

    cats = _sanitize(parsed.get("categories") or [])
    return {
        "categories": cats or ["other"],
        "summary": parsed.get("summary") or "",
    }


def _guess_media_type(file_path: str) -> str:
    lower = file_path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


async def classify_image_file(file_path: str) -> dict:
    with open(file_path, "rb") as f:
        data = f.read()
    return await _classify_image_bytes(data, _guess_media_type(file_path))


async def classify_pdf_via_vision(file_path: str, max_pages: int = 2) -> dict:
    """Render the first N pages of a PDF to PNG and classify via vision.

    Used as a fallback for scanned/image PDFs where fitz.get_text() returns
    nothing. Concatenates page classifications into a single deduped list.
    """
    doc = fitz.open(file_path)
    all_cats: list[str] = []
    summaries: list[str] = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=150)
            png_bytes = pix.tobytes("png")
            result = await _classify_image_bytes(png_bytes, "image/png")
            for c in result.get("categories", []):
                if c not in all_cats:
                    all_cats.append(c)
            if result.get("summary"):
                summaries.append(result["summary"])
    finally:
        doc.close()

    # If all we got is "other" from multiple pages, keep it as-is
    if not all_cats:
        all_cats = ["other"]
    return {
        "categories": all_cats,
        "summary": " | ".join(summaries),
    }
