"""Slide-spec schema for AI-driven deck generation.

A deck = (theme_id, list[Slide]) where each Slide has a layout from the catalog
and a content payload validated against that layout's pydantic class.

Design contract: the LLM emits these JSON shapes. The renderer (services/deck/renderer.py)
walks them and produces HTML. The LLM never writes HTML — that keeps brand/layout
consistency airtight while content stays freely promptable. Adding a layout = one
content class here + one render function there.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared building blocks — reused inside multiple layout content classes.
# ---------------------------------------------------------------------------


class Stat(BaseModel):
    """A single metric card: big number + uppercase label."""
    model_config = ConfigDict(extra="forbid")
    value: str = Field(..., description="Display value, e.g. '42%', 'IFRS 13', '$12M'. Keep short — renders large.")
    label: str = Field(..., description="Uppercase tracking-spaced label under the value.")


class Card(BaseModel):
    """An icon + heading + body block, used in card grids."""
    model_config = ConfigDict(extra="forbid")
    icon: str | None = Field(None, description="Single emoji or short glyph (e.g. '📈', '🎯'). Optional.")
    heading: str
    body: str


class TimelinePhase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration: str = Field(..., description="e.g. '1-2', '3-6'. Renders as the big number.")
    unit: str = Field("Weeks", description="Unit label under the number, e.g. 'Weeks', 'Months'.")
    phase: str = Field(..., description="Phase name, e.g. 'Data Collection'.")


class BulletPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    emphasis: str | None = Field(
        None,
        description="Optional bold lead-in, rendered as '<emphasis>:</emphasis> <text>'.",
    )


# ---------------------------------------------------------------------------
# Layout content payloads. Each class corresponds to one named layout in the
# catalog. Layout = how it draws; content = what's drawn.
# ---------------------------------------------------------------------------


class CoverContent(BaseModel):
    """Full-bleed title slide. Used as opener and section dividers."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = Field(None, description="Small uppercase tracking-spaced label above the title.")
    title: str
    subtitle: str | None = None
    footer_note: str | None = Field(
        None,
        description="Small footer text, e.g. 'Strictly Private and Confidential'. Optional.",
    )
    show_logo: bool = True


class SectionTitleContent(BaseModel):
    """Lighter-weight divider between sections within a deck."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    title: str
    subtitle: str | None = None


class TwoColumnContent(BaseModel):
    """Two-column layout: prose on the left, prose/stats/cards on the right."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    title: str
    left_paragraphs: list[str] = Field(default_factory=list, description="One <p> per item.")
    left_bullets: list[BulletPoint] = Field(default_factory=list)
    right_kind: Literal["paragraphs", "stats", "cards", "highlight"] = "paragraphs"
    right_paragraphs: list[str] = Field(default_factory=list)
    right_stats: list[Stat] = Field(
        default_factory=list,
        description="Used when right_kind='stats'. Rendered as a 2x2 grid. 2-4 items.",
    )
    right_cards: list[Card] = Field(
        default_factory=list,
        description="Used when right_kind='cards'. 2-4 items in a stacked grid.",
    )
    right_highlight: Stat | None = Field(
        None,
        description="Used when right_kind='highlight'. Single hero stat in a teal card.",
    )


class BulletListContent(BaseModel):
    """Single-column bulleted slide."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    title: str
    intro: str | None = Field(None, description="Optional paragraph before the bullets.")
    bullets: list[BulletPoint] = Field(..., min_length=2, max_length=8)


class CardGrid3Content(BaseModel):
    """Three-card row. Used for value props, pillars, process steps."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    title: str
    intro: str | None = None
    cards: list[Card] = Field(..., min_length=3, max_length=3)


class CardGrid2x3Content(BaseModel):
    """6-card grid (2 rows x 3 cols). For richer scope/service breakdowns."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    title: str
    cards: list[Card] = Field(..., min_length=4, max_length=6)


class StatGridContent(BaseModel):
    """Hero stats slide — 2-4 big numbers with labels."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    title: str
    intro: str | None = None
    stats: list[Stat] = Field(..., min_length=2, max_length=4)


class TimelinePhasesContent(BaseModel):
    """Engagement timeline as 3-4 duration cards."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    title: str
    phases: list[TimelinePhase] = Field(..., min_length=2, max_length=5)


class QuoteContent(BaseModel):
    """Pull quote with attribution. Big text, minimal chrome."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    quote: str
    attribution: str | None = None


class CTAContent(BaseModel):
    """Closing slide with up to 3 next-step cards."""
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = Field("Next Steps", description="Defaults to 'Next Steps' if unset.")
    title: str
    subtitle: str | None = None
    steps: list[Card] = Field(default_factory=list, max_length=3)
    footer_note: str | None = None


# ---------------------------------------------------------------------------
# Discriminated union: each Slide carries a `layout` tag and a `content` payload
# whose type is determined by that tag. Pydantic validates the right shape
# automatically when parsing JSON from the LLM.
# ---------------------------------------------------------------------------


LayoutName = Literal[
    "cover",
    "section_title",
    "two_column",
    "bullet_list",
    "card_grid_3",
    "card_grid_2x3",
    "stat_grid",
    "timeline_phases",
    "quote",
    "cta",
]


SlideContent = Annotated[
    Union[
        CoverContent,
        SectionTitleContent,
        TwoColumnContent,
        BulletListContent,
        CardGrid3Content,
        CardGrid2x3Content,
        StatGridContent,
        TimelinePhasesContent,
        QuoteContent,
        CTAContent,
    ],
    Field(discriminator=None),  # We dispatch on Slide.layout, not a content tag.
]


class Slide(BaseModel):
    """One slide in a deck. The renderer dispatches on `layout`; the content
    type must match the layout (validated via _validate_content_shape)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    layout: LayoutName
    content: dict = Field(
        ...,
        description=(
            "Content payload. Shape must match the layout's pydantic class — "
            "see app.services.deck.schema for each layout's fields."
        ),
    )
    notes: str | None = Field(None, description="Optional speaker notes / generation rationale.")

    def parsed_content(self) -> SlideContent:
        """Parse `content` into the typed model for this layout. Raises ValidationError on mismatch."""
        cls = _LAYOUT_TO_MODEL[self.layout]
        return cls.model_validate(self.content)


class SlideSpec(BaseModel):
    """Top-level deck spec. Persisted as JSONB on the decks table."""

    model_config = ConfigDict(extra="forbid")

    theme_id: str
    title: str = Field(..., description="Internal deck title — also used as PDF filename / browser tab.")
    slides: list[Slide] = Field(..., min_length=1)
    # Free-form notes from the AI about its outline choices. Helpful for debugging
    # and for the amend pass to know why the original generator picked this shape.
    outline_rationale: str | None = None

    def validate_all_content(self) -> None:
        """Force-parse every slide's content against its layout schema. Call this
        after loading an LLM response — Pydantic only validates the wrapper type
        (dict) at top-level, so we have to walk the slides ourselves to catch
        shape mismatches early."""
        for slide in self.slides:
            slide.parsed_content()


_LAYOUT_TO_MODEL: dict[str, type[BaseModel]] = {
    "cover": CoverContent,
    "section_title": SectionTitleContent,
    "two_column": TwoColumnContent,
    "bullet_list": BulletListContent,
    "card_grid_3": CardGrid3Content,
    "card_grid_2x3": CardGrid2x3Content,
    "stat_grid": StatGridContent,
    "timeline_phases": TimelinePhasesContent,
    "quote": QuoteContent,
    "cta": CTAContent,
}


def layout_catalog_for_prompt() -> str:
    """Render a compact human/LLM-readable catalog of all available layouts and
    their content schemas. Injected into the outline-pass system prompt so the
    LLM knows what it can pick from."""
    lines = ["Available slide layouts (pick from these only):", ""]
    for name, cls in _LAYOUT_TO_MODEL.items():
        schema = cls.model_json_schema()
        props = schema.get("properties", {})
        field_list = ", ".join(
            f"{k}: {v.get('type', v.get('anyOf', [{}])[0].get('type', '?'))}"
            for k, v in props.items()
        )
        doc = (cls.__doc__ or "").strip().split("\n")[0]
        lines.append(f"- {name} — {doc}")
        lines.append(f"    fields: {field_list}")
    return "\n".join(lines)
