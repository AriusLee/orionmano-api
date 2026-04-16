"""Brand configuration for report/deck generation.

Maps report/deck types to the correct company brand (Orionmano vs MVPI)
and centralises the header/letterhead/footer strings used in PDFs.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOGO_DIR = _REPO_ROOT / "frontend" / "public"


@dataclass(frozen=True)
class Brand:
    key: str
    name: str                 # wordmark (all caps)
    subtitle: str             # letterhead subtitle
    legal_name: str           # used in disclaimer / "prepared by"
    website: str
    footer_tag: str           # footer brand tag
    logo_path: str | None


ORIONMANO = Brand(
    key="orionmano",
    name="ORIONMANO",
    subtitle="Assurance Services",
    legal_name="Orionmano Assurance Services",
    website="omassurance.com",
    footer_tag="ORIONMANO ASSURANCE SERVICES",
    logo_path=str(_LOGO_DIR / "logo-orionmano.avif"),
)

MVPI = Brand(
    key="mvpi",
    name="MVPI",
    subtitle="Capital",
    legal_name="MVPI Capital",
    website="mvpicapital.com",
    footer_tag="MVPI CAPITAL",
    logo_path=str(_LOGO_DIR / "logo-mvpi.webp"),
)


# Orionmano owns the expert advisory reports; everything else is MVPI.
_BRAND_BY_TYPE: dict[str, Brand] = {
    # Orionmano
    "industry_report": ORIONMANO,
    "dd_report": ORIONMANO,
    "valuation_report": ORIONMANO,
    # MVPI
    "gap_analysis": MVPI,
    "sales_deck": MVPI,
    "kickoff_deck": MVPI,
    "company_deck": MVPI,
    "teaser": MVPI,
    "ir_release": MVPI,
    "engagement_letter": MVPI,
}


def brand_for(report_or_deck_type: str) -> Brand:
    return _BRAND_BY_TYPE.get(report_or_deck_type, MVPI)


_LOGO_MIME = {
    "avif": "image/avif",
    "webp": "image/webp",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
}


def brand_logo_data_uri(brand: Brand) -> str | None:
    """Return an inline data URI for the brand logo, or None if missing."""
    if not brand.logo_path or not os.path.exists(brand.logo_path):
        return None
    ext = brand.logo_path.rsplit(".", 1)[-1].lower()
    mime = _LOGO_MIME.get(ext, "image/png")
    with open(brand.logo_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"
