"""Theme catalog for deck generation.

A theme is pure data — colors, typography, page size, logo, background treatment.
Layouts are theme-agnostic; the renderer composes (theme, layout) → HTML. Adding
a theme requires no new code, just a new Theme instance (eventually a DB row).

For now the catalog lives in-process. When the frontend ships theme selection
we'll back this with a `themes` table; the in-process registry is just the seed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Theme(BaseModel):
    """Visual contract for a deck. All layouts render under any theme."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable identifier, e.g. 'orionmano_navy'.")
    name: str = Field(..., description="Human-readable label shown in the theme picker.")
    description: str = Field("", description="Short tagline shown under the name in the picker.")

    # Geometry
    page_size: Literal["16:9", "4:3"] = "16:9"

    # Colors — passed straight into the CSS variable block.
    background: str = Field(..., description="Slide background. Color, gradient, or 'linear-gradient(...)'.")
    surface: str = Field(..., description="Card background.")
    surface_teal: str = Field(..., description="Highlight/accent card background.")
    border: str = Field(..., description="Card border color (rgba allowed).")
    border_accent: str = Field(..., description="Accent card border.")
    primary: str = Field(..., description="Accent color — labels, dividers, stat numbers, bullets.")
    primary_soft: str = Field(..., description="Softer variant of primary, used in gradient ends.")
    text: str = Field(..., description="Body text color.")
    heading: str = Field(..., description="Heading color (usually near-white).")
    muted: str = Field(..., description="Muted/secondary text.")
    subtle: str = Field(..., description="Footer / least-prominent text.")
    glow_a: str = Field(..., description="Decorative glow color (top).")
    glow_b: str = Field(..., description="Decorative glow color (bottom).")

    # Typography
    heading_font: str = "Inter"
    body_font: str = "Inter"
    google_font_family: str = Field(
        "Inter:wght@300;400;500;600;700;800",
        description="Family spec for the Google Fonts @import URL.",
    )

    # Branding
    logo_uri: str | None = Field(
        None,
        description="Data URI or absolute URL. If None, the logo slot is hidden.",
    )
    brand_label: str = Field("", description="Wordmark text shown when no logo or alongside it.")
    brand_tagline: str = Field("", description="Tagline shown under the brand on the cover slide.")
    footer_label: str = Field("", description="Footer brand text on non-cover slides.")
    divider_style: Literal["gradient_bar", "solid", "hairline"] = "gradient_bar"


# ---------------------------------------------------------------------------
# Built-in themes. The first is the existing navy/teal look ported into the
# Theme model so visual output is unchanged on day one.
# ---------------------------------------------------------------------------


ORIONMANO_NAVY = Theme(
    id="orionmano_navy",
    name="Orionmano Navy",
    description="Dark navy + teal accent. The default Orionmano brand treatment.",
    page_size="16:9",
    background="#0C1929",
    surface="linear-gradient(135deg, rgba(15,23,42,0.9), rgba(12,25,41,0.6))",
    surface_teal="linear-gradient(135deg, rgba(20,184,166,0.08), rgba(20,184,166,0.02))",
    border="rgba(148,163,184,0.1)",
    border_accent="rgba(20,184,166,0.15)",
    primary="#14B8A6",
    primary_soft="#2DD4BF",
    text="#E2E8F0",
    heading="#F8FAFC",
    muted="#94A3B8",
    subtle="#475569",
    glow_a="#14B8A6",
    glow_b="#3B82F6",
    heading_font="Inter",
    body_font="Inter",
    brand_label="ORIONMANO",
    brand_tagline="Advisory · Valuation · Capital Markets",
    footer_label="ORIONMANO",
    divider_style="gradient_bar",
)


_REGISTRY: dict[str, Theme] = {
    ORIONMANO_NAVY.id: ORIONMANO_NAVY,
}


def get_theme(theme_id: str) -> Theme:
    theme = _REGISTRY.get(theme_id)
    if not theme:
        raise ValueError(f"Unknown theme: {theme_id}. Available: {list(_REGISTRY.keys())}")
    return theme


def list_themes() -> list[Theme]:
    return list(_REGISTRY.values())


def default_theme() -> Theme:
    return ORIONMANO_NAVY
