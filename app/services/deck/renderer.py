"""Deterministic renderer: (SlideSpec, Theme) -> HTML -> PDF.

The LLM produces SlideSpecs; this module turns them into pixel-stable PDFs.
Layout emitters are pure: (content_model, theme) -> HTML string for one slide's
inner body. The top-level `render_html` walks the spec, wraps each slide in
the standard frame (glow decorations + footer), and emits the full page.

Visual parity goal: rendering the equivalent SlideSpec for what build_sales_deck
used to produce should yield a visually identical PDF.
"""

from __future__ import annotations

from io import BytesIO
from typing import Callable

from app.services.deck.schema import (
    BulletListContent,
    BulletPoint,
    CTAContent,
    Card,
    CardGrid2x3Content,
    CardGrid3Content,
    CoverContent,
    QuoteContent,
    SectionTitleContent,
    Slide,
    SlideSpec,
    Stat,
    StatGridContent,
    TimelinePhase,
    TimelinePhasesContent,
    TwoColumnContent,
)
from app.services.deck.themes import Theme


# ---------------------------------------------------------------------------
# Geometry — derived from theme.page_size.
# ---------------------------------------------------------------------------

_PAGE_SIZES: dict[str, tuple[int, int]] = {
    "16:9": (1280, 720),
    "4:3": (1024, 768),
}


def _slide_dims(theme: Theme) -> tuple[int, int]:
    return _PAGE_SIZES.get(theme.page_size, _PAGE_SIZES["16:9"])


# ---------------------------------------------------------------------------
# HTML escaping — minimal, matches the helper the old generator used.
# ---------------------------------------------------------------------------


def _esc(val: str | None) -> str:
    if not val:
        return ""
    return (
        val.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# CSS — theme-parameterized. Mirrors the structure of the old
# services/deck/styles.py module but with all colors/typography pulled from
# the Theme model. Layout classes (.slide, .card, .g2, .g3, etc.) are
# universal across themes; only the values they reference differ.
# ---------------------------------------------------------------------------


def _theme_css(theme: Theme) -> str:
    w, h = _slide_dims(theme)
    divider_css = _divider_css(theme)
    # The @media screen block makes the same HTML usable as an in-browser
    # preview that scales to whatever viewport (iframe) width it gets, while
    # WeasyPrint keeps the fixed-pixel 16:9 layout for PDF. `zoom` is the
    # right primitive here because it affects layout (unlike transform:scale),
    # so multiple slides stacked vertically still flow correctly at any width.
    return f"""
@import url('https://fonts.googleapis.com/css2?family={theme.google_font_family}&display=swap');

@page {{ size: {w}px {h}px; margin: 0; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: '{theme.body_font}', sans-serif;
  background: {theme.background};
  color: {theme.text};
}}

.slide {{
  width: {w}px; height: {h}px; position: relative;
  overflow: hidden; background: {theme.background};
  page-break-after: always;
}}
.slide:last-child {{ page-break-after: auto; }}

@media screen {{
  html, body {{ margin: 0; padding: 0; overflow-x: hidden; }}
  body {{ scroll-snap-type: y mandatory; }}
  .slide {{
    /* Scale the entire slide so its native {w}px width fits the viewport.
       Using `zoom` (not transform:scale) so layout follows — stacked slides
       still take their proportional vertical space. */
    zoom: calc(100vw / {w}px);
    scroll-snap-align: start;
  }}
}}

.rel {{ position: relative; z-index: 2; }}
.accent {{ color: {theme.primary}; }}

.label {{
  font-size: 11px; font-weight: 700; color: {theme.primary};
  text-transform: uppercase; letter-spacing: 4px; margin-bottom: 14px;
}}

h1, h2, h3 {{ font-family: '{theme.heading_font}', sans-serif; color: {theme.heading}; }}
h1 {{ font-size: 44px; font-weight: 700; line-height: 1.15; margin-bottom: 14px; }}
h2 {{ font-size: 36px; font-weight: 700; line-height: 1.15; margin-bottom: 12px; }}
h3 {{ font-size: 18px; font-weight: 600; }}
p  {{ font-size: 15px; color: {theme.muted}; line-height: 1.7; }}

{divider_css}

.glow {{
  position: absolute; border-radius: 50%; filter: blur(80px);
  opacity: 0.12; pointer-events: none;
}}
.glow-t {{ background: {theme.glow_a}; }}
.glow-b {{ background: {theme.glow_b}; }}

.card {{
  background: {theme.surface};
  border: 1px solid {theme.border};
  border-radius: 16px; padding: 24px;
}}
.card-teal {{
  background: {theme.surface_teal};
  border: 1px solid {theme.border_accent};
  border-radius: 16px; padding: 24px;
}}

.stat-num {{
  font-size: 48px; font-weight: 800; color: {theme.primary}; line-height: 1;
}}
.stat-label {{
  font-size: 12px; font-weight: 600; color: {theme.subtle};
  text-transform: uppercase; letter-spacing: 1.5px; margin-top: 6px;
}}

.icon-box {{
  width: 48px; height: 48px;
  background: linear-gradient(135deg, {theme.border_accent}, rgba(20,184,166,0.05));
  border: 1px solid {theme.border_accent}; border-radius: 12px;
  display: flex; align-items: center; justify-content: center; margin-bottom: 12px;
  color: {theme.primary}; font-size: 20px;
}}

.g2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.g3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }}
.g4 {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 20px; }}

.footer {{
  position: absolute; bottom: 0; left: 0; right: 0; height: 44px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 60px; border-top: 1px solid {theme.border_accent}; z-index: 10;
}}
.footer span {{ font-size: 10px; color: {theme.subtle}; letter-spacing: 1px; }}
.footer .brand {{
  color: {theme.primary}; font-weight: 600; letter-spacing: 3px; text-transform: uppercase;
}}

.bullet {{ color: {theme.primary}; margin-right: 8px; }}
.bullet-item {{
  font-size: 14px; color: {theme.text}; margin-bottom: 10px;
  display: flex; align-items: flex-start;
}}
.bullet-item span {{ line-height: 1.5; }}

.brand-wordmark {{
  font-size: 16px; letter-spacing: 10px; color: {theme.primary};
  font-weight: 600; margin-bottom: 12px;
}}
.brand-tagline {{
  font-size: 11px; letter-spacing: 4px; color: {theme.subtle};
  margin-bottom: 40px;
}}
.quote-text {{
  font-size: 32px; line-height: 1.3; color: {theme.heading}; font-weight: 500;
  max-width: 900px;
}}
.quote-attribution {{
  font-size: 14px; color: {theme.primary}; margin-top: 28px;
  letter-spacing: 3px; text-transform: uppercase; font-weight: 600;
}}
""".strip()


def _divider_css(theme: Theme) -> str:
    if theme.divider_style == "solid":
        return f".divider {{ width: 50px; height: 3px; background: {theme.primary}; border-radius: 2px; margin: 14px 0; }}"
    if theme.divider_style == "hairline":
        return f".divider {{ width: 80px; height: 1px; background: {theme.primary}; margin: 14px 0; }}"
    return (
        ".divider {{ width: 50px; height: 3px; "
        "background: linear-gradient(90deg, {primary}, {primary_soft}); "
        "border-radius: 2px; margin: 14px 0; }}"
    ).format(primary=theme.primary, primary_soft=theme.primary_soft)


# ---------------------------------------------------------------------------
# Shared fragments used by multiple layouts.
# ---------------------------------------------------------------------------


def _footer_html(theme: Theme, deck_title: str) -> str:
    return (
        f'<div class="footer">'
        f'<span class="brand">{_esc(theme.footer_label or theme.brand_label)}</span>'
        f'<span>{_esc(deck_title)}</span>'
        f'</div>'
    )


def _brand_logo_img(theme: Theme, max_height_px: int = 44) -> str:
    if not theme.logo_uri:
        return ""
    return (
        f'<img src="{_esc(theme.logo_uri)}" alt="{_esc(theme.brand_label)} logo" '
        f'style="max-height:{max_height_px}px;max-width:180px;'
        f'object-fit:contain;margin-bottom:18px;" />'
    )


def _eyebrow(text: str | None) -> str:
    if not text:
        return ""
    return f'<div class="label">{_esc(text)}</div>'


def _bullets(items: list[BulletPoint]) -> str:
    out: list[str] = []
    for item in items:
        if item.emphasis:
            inner = f'<strong>{_esc(item.emphasis)}:</strong> {_esc(item.text)}'
        else:
            inner = _esc(item.text)
        out.append(
            f'<div class="bullet-item"><span class="bullet">&#9654;</span><span>{inner}</span></div>'
        )
    return "".join(out)


def _stat_card(stat: Stat, *, accent: bool = False, num_size: int = 36) -> str:
    cls = "card-teal" if accent else "card"
    return (
        f'<div class="{cls}" style="text-align:center;padding:20px;">'
        f'<div class="stat-num" style="font-size:{num_size}px;">{_esc(stat.value)}</div>'
        f'<div class="stat-label">{_esc(stat.label)}</div>'
        f'</div>'
    )


def _icon_box(icon: str | None) -> str:
    if not icon:
        return ""
    return f'<div class="icon-box">{_esc(icon)}</div>'


def _card_html(card: Card, *, padding: int = 24) -> str:
    return (
        f'<div class="card" style="padding:{padding}px;">'
        f'{_icon_box(card.icon)}'
        f'<h3 style="font-size:15px;margin-bottom:6px;">{_esc(card.heading)}</h3>'
        f'<p style="font-size:12px;">{_esc(card.body)}</p>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Layout emitters. Each returns the HTML for the slide's inner content; the
# outer <div class="slide">...</div> wrapper is added by `_render_slide`.
# ---------------------------------------------------------------------------


def _render_cover(c: CoverContent, theme: Theme) -> str:
    logo = _brand_logo_img(theme, max_height_px=48) if c.show_logo else ""
    eyebrow = (
        f'<div class="brand-tagline">{_esc(c.eyebrow)}</div>'
        if c.eyebrow
        else f'<div class="brand-tagline">{_esc(theme.brand_tagline)}</div>'
    )
    wordmark = (
        f'<div class="brand-wordmark">{_esc(theme.brand_label)}</div>'
        if theme.brand_label
        else ""
    )
    subtitle = (
        f'<p style="font-size:17px;color:{theme.muted};">{_esc(c.subtitle)}</p>'
        if c.subtitle
        else ""
    )
    footer_note = (
        f'<p style="font-size:12px;color:{theme.subtle};margin-top:50px;">{_esc(c.footer_note)}</p>'
        if c.footer_note
        else ""
    )
    return f"""
<div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
<div class="glow glow-b" style="width:300px;height:300px;bottom:-50px;left:100px;opacity:0.08;"></div>
<div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
  <div>
    {logo}
    {wordmark}
    {eyebrow}
    <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
    <h1>{_esc(c.title)}</h1>
    {subtitle}
    {footer_note}
  </div>
</div>
"""


def _render_section_title(c: SectionTitleContent, theme: Theme) -> str:
    subtitle = (
        f'<p style="font-size:16px;color:{theme.muted};max-width:700px;">{_esc(c.subtitle)}</p>'
        if c.subtitle
        else ""
    )
    return f"""
<div class="glow glow-t" style="width:400px;height:400px;top:-150px;left:-150px;opacity:0.1;"></div>
<div class="rel" style="padding:56px 70px;">
  {_eyebrow(c.eyebrow)}
  <h2>{_esc(c.title)}</h2>
  <div class="divider"></div>
  {subtitle}
</div>
"""


def _render_two_column(c: TwoColumnContent, theme: Theme) -> str:
    # Left column.
    left_parts: list[str] = []
    for p in c.left_paragraphs:
        left_parts.append(f'<p style="margin-bottom:16px;">{_esc(p)}</p>')
    if c.left_bullets:
        left_parts.append(f'<div style="margin-top:8px;">{_bullets(c.left_bullets)}</div>')
    left_html = "".join(left_parts)

    # Right column — kind determines what we draw.
    right_html = ""
    if c.right_kind == "paragraphs":
        right_html = "".join(
            f'<p style="margin-bottom:16px;">{_esc(p)}</p>' for p in c.right_paragraphs
        )
    elif c.right_kind == "stats":
        right_html = (
            '<div class="g2" style="gap:16px;">'
            + "".join(_stat_card(s, num_size=32) for s in c.right_stats)
            + "</div>"
        )
    elif c.right_kind == "cards":
        right_html = (
            '<div class="g2" style="gap:16px;">'
            + "".join(_card_html(card, padding=20) for card in c.right_cards)
            + "</div>"
        )
    elif c.right_kind == "highlight" and c.right_highlight:
        right_html = (
            '<div class="card-teal" style="display:flex;align-items:center;'
            'justify-content:center;text-align:center;height:100%;">'
            f'<div><div class="stat-num" style="font-size:42px;">{_esc(c.right_highlight.value)}</div>'
            f'<div class="stat-label">{_esc(c.right_highlight.label)}</div></div>'
            "</div>"
        )

    return f"""
<div class="glow glow-b" style="width:400px;height:400px;bottom:-100px;right:-100px;opacity:0.06;"></div>
<div class="rel" style="padding:56px 70px;">
  {_eyebrow(c.eyebrow)}
  <h2>{_esc(c.title)}</h2>
  <div class="divider"></div>
  <div class="g2" style="gap:50px;margin-top:16px;">
    <div>{left_html}</div>
    <div>{right_html}</div>
  </div>
</div>
"""


def _render_bullet_list(c: BulletListContent, theme: Theme) -> str:
    intro = (
        f'<p style="max-width:780px;margin-bottom:24px;">{_esc(c.intro)}</p>'
        if c.intro
        else ""
    )
    return f"""
<div class="glow glow-t" style="width:350px;height:350px;top:-80px;left:-80px;opacity:0.08;"></div>
<div class="rel" style="padding:56px 70px;">
  {_eyebrow(c.eyebrow)}
  <h2>{_esc(c.title)}</h2>
  <div class="divider"></div>
  {intro}
  <div style="margin-top:16px;">{_bullets(c.bullets)}</div>
</div>
"""


def _render_card_grid_3(c: CardGrid3Content, theme: Theme) -> str:
    intro = (
        f'<p style="max-width:780px;margin-bottom:24px;">{_esc(c.intro)}</p>'
        if c.intro
        else ""
    )
    cards = (
        '<div class="g3" style="gap:16px;margin-top:8px;">'
        + "".join(_card_html(card, padding=28) for card in c.cards)
        + "</div>"
    )
    return f"""
<div class="glow glow-b" style="width:400px;height:400px;bottom:-100px;left:-100px;opacity:0.06;"></div>
<div class="rel" style="padding:56px 70px;">
  {_eyebrow(c.eyebrow)}
  <h2>{_esc(c.title)}</h2>
  <div class="divider"></div>
  {intro}
  {cards}
</div>
"""


def _render_card_grid_2x3(c: CardGrid2x3Content, theme: Theme) -> str:
    cards = (
        '<div class="g3" style="gap:16px;margin-top:16px;">'
        + "".join(_card_html(card, padding=22) for card in c.cards)
        + "</div>"
    )
    return f"""
<div class="glow glow-t" style="width:350px;height:350px;top:-80px;left:-80px;opacity:0.08;"></div>
<div class="rel" style="padding:56px 70px;">
  {_eyebrow(c.eyebrow)}
  <h2>{_esc(c.title)}</h2>
  <div class="divider"></div>
  {cards}
</div>
"""


def _render_stat_grid(c: StatGridContent, theme: Theme) -> str:
    n = len(c.stats)
    grid_cls = "g4" if n == 4 else ("g3" if n == 3 else "g2")
    stats_html = "".join(_stat_card(s, num_size=42) for s in c.stats)
    intro = (
        f'<p style="max-width:780px;margin-bottom:24px;">{_esc(c.intro)}</p>'
        if c.intro
        else ""
    )
    return f"""
<div class="glow glow-b" style="width:400px;height:400px;bottom:-100px;right:-100px;opacity:0.06;"></div>
<div class="rel" style="padding:56px 70px;">
  {_eyebrow(c.eyebrow)}
  <h2>{_esc(c.title)}</h2>
  <div class="divider"></div>
  {intro}
  <div class="{grid_cls}" style="gap:16px;margin-top:8px;">{stats_html}</div>
</div>
"""


def _render_timeline_phases(c: TimelinePhasesContent, theme: Theme) -> str:
    n = len(c.phases)
    grid_cls = "g4" if n >= 4 else ("g3" if n == 3 else "g2")

    def _phase(p: TimelinePhase) -> str:
        return (
            '<div class="card" style="text-align:center;padding:24px;">'
            f'<div class="stat-num" style="font-size:32px;">{_esc(p.duration)}</div>'
            f'<div class="stat-label">{_esc(p.unit)}</div>'
            f'<h3 style="font-size:13px;margin-top:12px;">{_esc(p.phase)}</h3>'
            "</div>"
        )

    return f"""
<div class="rel" style="padding:56px 70px;">
  {_eyebrow(c.eyebrow)}
  <h2>{_esc(c.title)}</h2>
  <div class="divider"></div>
  <div class="{grid_cls}" style="gap:16px;margin-top:20px;">
    {"".join(_phase(p) for p in c.phases)}
  </div>
</div>
"""


def _render_quote(c: QuoteContent, theme: Theme) -> str:
    attribution = (
        f'<div class="quote-attribution">{_esc(c.attribution)}</div>'
        if c.attribution
        else ""
    )
    return f"""
<div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.12;"></div>
<div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;padding:56px 90px;">
  <div style="text-align:center;">
    {_eyebrow(c.eyebrow)}
    <div class="quote-text">&ldquo;{_esc(c.quote)}&rdquo;</div>
    {attribution}
  </div>
</div>
"""


def _render_cta(c: CTAContent, theme: Theme) -> str:
    subtitle = (
        f'<p style="max-width:540px;margin:0 auto 40px;font-size:16px;">{_esc(c.subtitle)}</p>'
        if c.subtitle
        else ""
    )
    steps_grid = ""
    if c.steps:
        n = len(c.steps)
        cls = "g3" if n == 3 else "g2"

        def _step(card: Card) -> str:
            body = (
                f'<p style="font-size:12px;margin-top:6px;">{_esc(card.body)}</p>'
                if card.body
                else ""
            )
            return (
                '<div class="card" style="text-align:center;padding:20px;">'
                f'<h3 style="font-size:14px;">{_esc(card.heading)}</h3>'
                f'{body}</div>'
            )

        steps_grid = (
            f'<div class="{cls}" style="max-width:600px;margin:0 auto;gap:16px;">'
            + "".join(_step(s) for s in c.steps)
            + "</div>"
        )
    footer_note = (
        f'<p style="font-size:12px;color:{theme.subtle};margin-top:50px;">{_esc(c.footer_note)}</p>'
        if c.footer_note
        else ""
    )
    return f"""
<div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
<div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
  <div>
    {_eyebrow(c.eyebrow or "Next Steps")}
    <h1 style="margin-bottom:20px;">{_esc(c.title)}</h1>
    <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
    {subtitle}
    {steps_grid}
    {footer_note}
  </div>
</div>
"""


_LAYOUT_RENDERERS: dict[str, Callable] = {
    "cover": _render_cover,
    "section_title": _render_section_title,
    "two_column": _render_two_column,
    "bullet_list": _render_bullet_list,
    "card_grid_3": _render_card_grid_3,
    "card_grid_2x3": _render_card_grid_2x3,
    "stat_grid": _render_stat_grid,
    "timeline_phases": _render_timeline_phases,
    "quote": _render_quote,
    "cta": _render_cta,
}


# ---------------------------------------------------------------------------
# Top-level: walk a SlideSpec and emit a full HTML page.
# ---------------------------------------------------------------------------

# Layouts that own the whole frame and don't take an external footer strip.
_FULL_BLEED_LAYOUTS = {"cover", "cta", "quote"}


def _render_slide(slide: Slide, theme: Theme, deck_title: str) -> str:
    renderer = _LAYOUT_RENDERERS.get(slide.layout)
    if renderer is None:
        raise ValueError(f"No renderer registered for layout: {slide.layout}")
    content_model = slide.parsed_content()
    inner = renderer(content_model, theme)
    footer = "" if slide.layout in _FULL_BLEED_LAYOUTS else _footer_html(theme, deck_title)
    return f'<div class="slide">{inner}{footer}</div>'


def render_html(spec: SlideSpec, theme: Theme) -> str:
    """Render the spec to a full HTML document. Same input -> same output."""
    if theme.id != spec.theme_id:
        # Soft warning only — callers explicitly override the theme during
        # theme-swap. Renderer trusts the theme it's handed.
        pass

    # Validate every slide's content up-front so we fail fast with a clear error
    # rather than half-render and then explode mid-page.
    spec.validate_all_content()

    slides_html = "\n".join(
        _render_slide(slide, theme, spec.title) for slide in spec.slides
    )
    css = _theme_css(theme)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<title>{_esc(spec.title)}</title>'
        f'<style>{css}</style>'
        f'</head><body>{slides_html}</body></html>'
    )


def render_pdf(spec: SlideSpec, theme: Theme) -> bytes:
    """Render the spec to a PDF via WeasyPrint."""
    # Imported lazily so module import doesn't pay WeasyPrint's startup cost
    # in contexts that only need HTML (e.g. previewing in-browser).
    from weasyprint import HTML

    html = render_html(spec, theme)
    return HTML(string=html).write_pdf()


__all__ = ["render_html", "render_pdf"]
