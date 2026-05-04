"""Render `chart` JSON specs to inline SVG for PDF export.

The same ChartSpec format the frontend uses — parsed straight from
```chart {...}``` fenced blocks in section markdown.

No external dependencies — hand-rolled SVG. Matches the frontend palette.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Frontend palette (gradient top + bottom). Hex equivalents of the oklch values
# used in the React ChartBlock so PDFs match the dashboard visually.
COLORS = [
    ("#5BD0C0", "#2E8B7D"),  # teal
    ("#5C8FE0", "#2D5BA8"),  # blue
    ("#76C58A", "#3F8554"),  # green
    ("#A77BD6", "#6840A1"),  # purple
    ("#7281C2", "#3E4A85"),  # indigo
    ("#E0A569", "#9D6731"),  # amber
    ("#E07A5F", "#9D3D24"),  # rust
]
TEXT = "#0F172A"
MUTED = "#64748B"
GRID = "#E2E8F0"
AXIS = "#94A3B8"
BG = "#FFFFFF"


# Match ```chart fences whether the JSON starts on a new line or inline on the
# same line as the opener. The LLM occasionally collapses ```chart\n{...} into
# ```chart {...} on a single line; the previous \s*\n required a literal
# newline and silently let the whole block fall through to the markdown parser.
CHART_FENCE_RE = re.compile(r"```chart\b[ \t]*\n?([\s\S]*?)```", re.IGNORECASE)


def _normalize_source_note(raw: str) -> str:
    """Collapse multi-source attributions to just Orionmano when present.

    Policy: paid/external sources sit behind Orionmano-imprinted articles
    and shouldn't co-attribute on chart source notes. If "Orionmano" appears
    anywhere in the note, return the canonical Orionmano line and drop the
    rest. Otherwise leave the note unchanged.
    """
    if not raw:
        return raw
    if re.search(r"orionmano", raw, re.IGNORECASE):
        return "Source: Orionmano Industries"
    return raw


def _clean_label(s: Any) -> str:
    if s is None:
        return ""
    text = str(s)
    text = re.sub(r"<br\s*/?>", " · ", text, flags=re.IGNORECASE)
    text = re.sub(r"<cite[^>]*/?>", "", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\[\^\d+\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _esc(s: Any) -> str:
    return (
        _clean_label(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt_num(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v:,.1f}".rstrip("0").rstrip(".")
    if abs(v) >= 1:
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:.2f}"


def _series_keys(spec: dict) -> list[str]:
    series = spec.get("series") or []
    if series:
        return [_clean_label(s) for s in series]
    if not spec.get("data"):
        return []
    first = spec["data"][0]
    return [k for k, v in first.items() if k != "x" and isinstance(v, (int, float))]


def _normalize_data(spec: dict) -> list[dict]:
    """Apply cleaning to x labels and re-key series with cleaned names."""
    rows = []
    for raw in spec.get("data") or []:
        out: dict = {"x": _clean_label(raw.get("x"))}
        for k, v in raw.items():
            if k == "x":
                continue
            out[_clean_label(k)] = v
        rows.append(out)
    return rows


def _label_px(label: str) -> float:
    """Approximate rendered width of a label at font-size 10 (Inter, sans).
    A flat 5.6 px/char is close enough for layout decisions; the real width
    depends on the glyph mix but rotation-vs-flat is a coarse choice."""
    return len(_clean_label(label)) * 5.6


def _xaxis_label_metrics(rotate: bool, max_label_px: float, base_h: int) -> tuple[int, int]:
    """Return (pad_b, total_h) for an x-axis given rotation + longest label.
    Rotated labels at -28° need vertical room ≈ sin(28°) × label_px ≈ 0.47×.
    Grow the SVG height when bottom padding balloons so the plot stays tall."""
    if not rotate:
        return 56, base_h
    pad_b = 28 + int(0.5 * max_label_px) + 8
    pad_b = min(pad_b, 140)
    h = base_h if pad_b <= 60 else base_h + (pad_b - 60)
    return pad_b, h


def _xaxis_label(cx: float, y: float, text: str, rotate: bool) -> str:
    """Render one x-axis tick label, centred or tilted -28° from its anchor."""
    if rotate:
        return (
            f'<text x="{cx:.1f}" y="{y:.1f}" text-anchor="end" font-size="10" '
            f'fill="{MUTED}" transform="rotate(-28 {cx:.1f} {y:.1f})">{_esc(text)}</text>'
        )
    return (
        f'<text x="{cx:.1f}" y="{(y + 2):.1f}" text-anchor="middle" '
        f'font-size="10" fill="{MUTED}">{_esc(text)}</text>'
    )


def _gradient_defs(prefix: str, count: int, vertical: bool = True) -> str:
    parts: list[str] = ["<defs>"]
    for i in range(count):
        top, bot = COLORS[i % len(COLORS)]
        x2, y2 = (0, 1) if vertical else (1, 0)
        parts.append(
            f'<linearGradient id="{prefix}-{i}" x1="0" y1="0" x2="{x2}" y2="{y2}">'
            f'<stop offset="0%" stop-color="{top}" stop-opacity="0.95"/>'
            f'<stop offset="100%" stop-color="{bot}" stop-opacity="0.85"/>'
            f"</linearGradient>"
        )
    parts.append("</defs>")
    return "".join(parts)


# ─── individual chart renderers ──────────────────────────────────────────


def _render_vertical_bar(spec: dict, prefix: str, stacked: bool = False) -> str:
    W = 720
    pad_l, pad_r, pad_t = 56, 24, 28

    data = _normalize_data(spec)
    series = _series_keys(spec)
    if not data or not series:
        return _empty(W, 360, "No data")

    # Decide x-axis label rotation up front: when any label is wider than its
    # bar slot, we tilt to -28° to stop adjacent labels from overlapping.
    plot_w = W - pad_l - pad_r
    group_w = plot_w / max(len(data), 1)
    labels_px = [_label_px(str(d.get("x", ""))) for d in data]
    max_label_px = max(labels_px, default=0)
    rotate_labels = max_label_px > group_w - 6
    pad_b, H = _xaxis_label_metrics(rotate_labels, max_label_px, base_h=360)
    plot_h = H - pad_t - pad_b

    # Compute max
    if stacked:
        max_v = max(sum(float(d.get(s, 0) or 0) for s in series) for d in data) or 1
    else:
        max_v = max(
            (float(d.get(s, 0) or 0) for d in data for s in series),
            default=1,
        ) or 1

    n = len(data)
    inner_pad = 0.18 * group_w
    if stacked:
        bar_w = group_w - 2 * inner_pad
    else:
        bar_w = (group_w - 2 * inner_pad) / max(len(series), 1)

    parts = [_svg_open(W, H), _gradient_defs(prefix, len(series))]
    parts.append(_grid_y(W, H, pad_l, pad_r, pad_t, pad_b, max_v))

    for i, d in enumerate(data):
        x_left = pad_l + i * group_w + inner_pad
        if stacked:
            y_cursor = pad_t + plot_h
            for si, s in enumerate(series):
                v = float(d.get(s, 0) or 0)
                if v <= 0:
                    continue
                bh = (v / max_v) * plot_h
                parts.append(
                    f'<rect x="{x_left:.1f}" y="{(y_cursor - bh):.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="url(#{prefix}-{si})"/>'
                )
                y_cursor -= bh
        else:
            for si, s in enumerate(series):
                v = float(d.get(s, 0) or 0)
                bh = max(0, (v / max_v) * plot_h)
                bx = x_left + si * bar_w
                by = pad_t + plot_h - bh
                parts.append(
                    f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="url(#{prefix}-{si})"/>'
                )
                # value label above each bar (only when non-stacked, single-series)
                if len(series) == 1 and bh > 6:
                    parts.append(
                        f'<text x="{(bx + bar_w/2):.1f}" y="{(by - 4):.1f}" text-anchor="middle" font-size="9" fill="{TEXT}">{_fmt_num(v)}</text>'
                    )
        # x label
        cx = pad_l + i * group_w + group_w / 2
        parts.append(_xaxis_label(cx, pad_t + plot_h + 14, d["x"], rotate_labels))

    if len(series) > 1:
        parts.append(_legend(W, H - 20, prefix, series))

    parts.append("</svg>")
    return "".join(parts)


def _render_horizontal_bar(spec: dict, prefix: str) -> str:
    W, H = 720, max(220, 28 * len(spec.get("data") or []) + 80)
    pad_l, pad_r, pad_t, pad_b = 160, 56, 20, 36
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b

    data = _normalize_data(spec)
    series = _series_keys(spec)
    if not data or not series:
        return _empty(W, H, "No data")
    primary = series[0]
    max_v = max((float(d.get(primary, 0) or 0) for d in data), default=1) or 1

    n = len(data)
    row_h = plot_h / n
    bar_h = row_h * 0.65

    parts = [_svg_open(W, H), _gradient_defs(prefix, 1, vertical=False)]
    parts.append(_grid_x(W, H, pad_l, pad_r, pad_t, pad_b, max_v))

    for i, d in enumerate(data):
        v = float(d.get(primary, 0) or 0)
        bw = (v / max_v) * plot_w if max_v > 0 else 0
        y = pad_t + i * row_h + (row_h - bar_h) / 2
        parts.append(
            f'<rect x="{pad_l:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bar_h:.1f}" fill="url(#{prefix}-0)"/>'
        )
        # category label (truncate)
        label = _esc(d["x"])
        if len(label) > 24:
            label = label[:23] + "…"
        parts.append(
            f'<text x="{(pad_l - 8):.1f}" y="{(y + bar_h/2 + 3):.1f}" text-anchor="end" font-size="10" fill="{MUTED}">{label}</text>'
        )
        # value
        unit = spec.get("y_unit") or ""
        parts.append(
            f'<text x="{(pad_l + bw + 6):.1f}" y="{(y + bar_h/2 + 3):.1f}" font-size="10" fill="{TEXT}">{_fmt_num(v)}{_esc(unit)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _render_line(spec: dict, prefix: str) -> str:
    W = 720
    pad_l, pad_r, pad_t = 56, 24, 28

    data = _normalize_data(spec)
    series = _series_keys(spec)
    if not data or not series:
        return _empty(W, 360, "No data")

    plot_w = W - pad_l - pad_r
    n = len(data)
    step_x = plot_w / max(n - 1, 1)
    labels_px = [_label_px(str(d.get("x", ""))) for d in data]
    max_label_px = max(labels_px, default=0)
    rotate_labels = max_label_px > step_x - 6
    pad_b, H = _xaxis_label_metrics(rotate_labels, max_label_px, base_h=360)
    plot_h = H - pad_t - pad_b

    max_v = max(
        (float(d.get(s, 0) or 0) for d in data for s in series),
        default=1,
    ) or 1

    parts = [_svg_open(W, H), _gradient_defs(prefix, len(series))]
    parts.append(_grid_y(W, H, pad_l, pad_r, pad_t, pad_b, max_v))

    for si, s in enumerate(series):
        top, _ = COLORS[si % len(COLORS)]
        pts: list[str] = []
        for i, d in enumerate(data):
            v = float(d.get(s, 0) or 0)
            x = pad_l + i * step_x
            y = pad_t + plot_h - (v / max_v) * plot_h
            pts.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<polyline fill="none" stroke="{top}" stroke-width="2" points="{ " ".join(pts) }"/>'
        )
        # dots
        for p in pts:
            x, y = p.split(",")
            parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{top}"/>')

    # x labels
    for i, d in enumerate(data):
        cx = pad_l + i * step_x
        parts.append(_xaxis_label(cx, pad_t + plot_h + 14, d["x"], rotate_labels))

    if len(series) > 1:
        parts.append(_legend(W, H - 20, prefix, series))

    parts.append("</svg>")
    return "".join(parts)


def _render_pie(spec: dict, prefix: str) -> str:
    import math
    W, H = 720, 360
    cx, cy = 230, H / 2
    r_outer = 130
    r_inner = 72

    data = _normalize_data(spec)
    series = _series_keys(spec)
    if not data or not series:
        return _empty(W, H, "No data")
    valuekey = series[0]
    pairs = [(_clean_label(d["x"]), float(d.get(valuekey, 0) or 0)) for d in data]
    pairs = [(n, v) for n, v in pairs if v > 0]
    total = sum(v for _, v in pairs) or 1

    parts = [_svg_open(W, H), _gradient_defs(prefix, len(pairs))]

    angle = -math.pi / 2  # start at top
    for i, (name, v) in enumerate(pairs):
        sweep = (v / total) * 2 * math.pi
        a0 = angle
        a1 = angle + sweep
        large = 1 if sweep > math.pi else 0
        # outer arc
        x0o = cx + r_outer * math.cos(a0)
        y0o = cy + r_outer * math.sin(a0)
        x1o = cx + r_outer * math.cos(a1)
        y1o = cy + r_outer * math.sin(a1)
        x0i = cx + r_inner * math.cos(a1)
        y0i = cy + r_inner * math.sin(a1)
        x1i = cx + r_inner * math.cos(a0)
        y1i = cy + r_inner * math.sin(a0)
        d = (
            f"M {x0o:.1f} {y0o:.1f} "
            f"A {r_outer} {r_outer} 0 {large} 1 {x1o:.1f} {y1o:.1f} "
            f"L {x0i:.1f} {y0i:.1f} "
            f"A {r_inner} {r_inner} 0 {large} 0 {x1i:.1f} {y1i:.1f} Z"
        )
        parts.append(f'<path d="{d}" fill="url(#{prefix}-{i})" stroke="{BG}" stroke-width="2"/>')
        # percentage label centered in the slice
        mid = (a0 + a1) / 2
        lr = (r_outer + r_inner) / 2
        lx = cx + lr * math.cos(mid)
        ly = cy + lr * math.sin(mid)
        pct = (v / total) * 100
        if pct >= 4:
            parts.append(
                f'<text x="{lx:.1f}" y="{(ly + 3):.1f}" text-anchor="middle" font-size="10" font-weight="600" fill="{BG}">{round(pct)}%</text>'
            )
        angle = a1

    # legend on the right
    legend_x = 410
    legend_y0 = cy - len(pairs) * 12
    parts.append(_legend_block(legend_x, legend_y0, prefix, [name for name, _ in pairs], pairs, total))

    parts.append("</svg>")
    return "".join(parts)


# ─── helpers ──────────────────────────────────────────────────────────────


def _svg_open(w: int, h: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="100%" font-family="Inter, sans-serif">'
    )


def _empty(w: int, h: int, msg: str) -> str:
    return (
        _svg_open(w, h)
        + f'<text x="{w/2}" y="{h/2}" text-anchor="middle" fill="{MUTED}" font-size="11">{_esc(msg)}</text>'
        + "</svg>"
    )


def _grid_y(W: int, H: int, pl: int, pr: int, pt: int, pb: int, max_v: float) -> str:
    plot_w = W - pl - pr
    plot_h = H - pt - pb
    parts = []
    ticks = 4
    for k in range(ticks + 1):
        v = max_v * k / ticks
        y = pt + plot_h - (v / max_v) * plot_h if max_v > 0 else pt + plot_h
        parts.append(
            f'<line x1="{pl}" y1="{y:.1f}" x2="{pl + plot_w}" y2="{y:.1f}" stroke="{GRID}" stroke-dasharray="3 3" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{pl - 8}" y="{(y + 3):.1f}" text-anchor="end" font-size="9" fill="{MUTED}">{_fmt_num(v)}</text>'
        )
    return "".join(parts)


def _grid_x(W: int, H: int, pl: int, pr: int, pt: int, pb: int, max_v: float) -> str:
    plot_w = W - pl - pr
    plot_h = H - pt - pb
    parts = []
    ticks = 4
    for k in range(ticks + 1):
        v = max_v * k / ticks
        x = pl + (v / max_v) * plot_w if max_v > 0 else pl
        parts.append(
            f'<line x1="{x:.1f}" y1="{pt}" x2="{x:.1f}" y2="{pt + plot_h}" stroke="{GRID}" stroke-dasharray="3 3" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{(pt + plot_h + 14):.1f}" text-anchor="middle" font-size="9" fill="{MUTED}">{_fmt_num(v)}</text>'
        )
    return "".join(parts)


def _legend(W: int, y: int, prefix: str, series: list[str]) -> str:
    parts: list[str] = []
    item_w = 140
    total_w = item_w * len(series)
    x0 = (W - total_w) / 2
    for i, s in enumerate(series):
        top, _ = COLORS[i % len(COLORS)]
        x = x0 + i * item_w
        parts.append(f'<rect x="{x:.1f}" y="{(y - 8):.1f}" width="10" height="10" fill="{top}"/>')
        parts.append(
            f'<text x="{(x + 14):.1f}" y="{(y + 1):.1f}" font-size="10" fill="{MUTED}">{_esc(s)}</text>'
        )
    return "".join(parts)


def _legend_block(x: int, y: int, prefix: str, names: list[str], pairs: list, total: float) -> str:
    parts: list[str] = []
    for i, (name, v) in enumerate(pairs):
        top, _ = COLORS[i % len(COLORS)]
        row_y = y + i * 22
        pct = (v / total) * 100 if total else 0
        parts.append(f'<rect x="{x}" y="{row_y - 8}" width="11" height="11" fill="{top}"/>')
        parts.append(
            f'<text x="{x + 18}" y="{row_y + 1}" font-size="10" fill="{TEXT}">{_esc(name)}</text>'
        )
        parts.append(
            f'<text x="{x + 18}" y="{row_y + 13}" font-size="9" fill="{MUTED}">{round(pct)}% · {_fmt_num(v)}</text>'
        )
    return "".join(parts)


# ─── public api ──────────────────────────────────────────────────────────


def render_chart_spec(spec: dict, prefix: str = "g") -> str:
    """Return inline SVG for a single ChartSpec dict."""
    t = (spec.get("type") or "bar").lower()
    if t == "pie":
        return _render_pie(spec, prefix)
    if t == "horizontal-bar":
        return _render_horizontal_bar(spec, prefix)
    if t == "line":
        return _render_line(spec, prefix)
    if t == "stacked-bar":
        return _render_vertical_bar(spec, prefix, stacked=True)
    return _render_vertical_bar(spec, prefix, stacked=False)


def replace_chart_blocks(markdown_text: str) -> str:
    """Find every ```chart {...}``` fenced block and replace with an HTML
    figure containing inline SVG. Invalid JSON falls back to a fenced code
    block (visible) so prompt drift is debuggable.
    """
    counter = {"i": 0}

    def _sub(m: re.Match) -> str:
        raw = m.group(1).strip()
        try:
            spec = json.loads(raw)
        except Exception:
            return f"<pre class=\"chart-error\">[invalid chart spec]\n{_esc(raw[:400])}</pre>"
        counter["i"] += 1
        prefix = f"c{counter['i']}"
        title = _esc(spec.get("title") or "")
        source = _esc(_normalize_source_note(spec.get("source_note") or ""))
        svg = render_chart_spec(spec, prefix)
        title_html = f'<figcaption class="chart-title">{title}</figcaption>' if title else ""
        source_html = f'<div class="chart-source">{source}</div>' if source else ""
        return (
            f'<figure class="chart">{title_html}<div class="chart-body">{svg}</div>{source_html}</figure>'
        )

    return CHART_FENCE_RE.sub(_sub, markdown_text)
