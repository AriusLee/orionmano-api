"""Render chart spec dicts to PNG files (matplotlib-based, for DOCX export).

Eric 2026-05-22 — the SVG renderer in chart_renderer.py is used by the PDF
export. Pandoc can't embed inline SVG in .docx in a reliable way, so DOCX
export needs raster PNGs. This module is dedicated to that path: matplotlib
+ headless Agg backend → PNG file → pandoc-embeddable `![](file.png)`.

Supported spec types match the schema declared in the industry-report
prompt: `bar`, `stacked-bar`, `line`, `pie`, `horizontal-bar`.

Defensive: malformed specs return False so the caller can fall back to
the markdown-table conversion path declared in generator._chart_block_to_table.
"""
from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402

# Orionmano brand palette — teal primary + neutral support tones so charts
# match the dashboard / PDF chart visuals rather than matplotlib defaults.
_PALETTE = [
    "#14B8A6",  # teal-500 (primary)
    "#0F766E",  # teal-700
    "#64748B",  # slate-500
    "#94A3B8",  # slate-400
    "#0EA5E9",  # sky-500
    "#F59E0B",  # amber-500
    "#A855F7",  # purple-500
    "#EF4444",  # red-500
]


def _style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.tick_params(colors="#475569", labelsize=9)
    ax.title.set_color("#0F172A")
    ax.yaxis.label.set_color("#475569")
    ax.xaxis.label.set_color("#475569")
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.5, zorder=0)


def _series_keys(spec: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    series = spec.get("series")
    if isinstance(series, list) and series:
        return [str(s) for s in series]
    if rows:
        return [k for k in rows[0].keys() if k != "x"]
    return []


def _y_formatter():
    def _fmt(x, _pos):
        if abs(x) >= 1000:
            return f"{x:,.0f}"
        if abs(x) >= 100:
            return f"{x:.0f}"
        return f"{x:.1f}"
    return mticker.FuncFormatter(_fmt)


def render_chart_spec_to_png(spec: dict[str, Any], output_path: str) -> bool:
    """Render a single chart spec dict to a PNG file.

    Returns True on success. Returns False if the spec is malformed or the
    chart type is unsupported — the caller should fall back to a markdown
    table so the DRS doc still ships.
    """
    if not isinstance(spec, dict):
        return False
    rows = spec.get("data") or []
    if not isinstance(rows, list) or not rows:
        return False

    chart_type = (spec.get("type") or "bar").lower()
    title = spec.get("title", "")
    x_label = spec.get("x_label", "")
    y_label = spec.get("y_label", "")
    y_unit = spec.get("y_unit")
    annotations = spec.get("annotations") or []

    try:
        fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=140)
    except Exception:
        return False

    try:
        if chart_type == "pie":
            labels = [str(r.get("x", "")) for r in rows]
            series_keys = _series_keys(spec, rows)
            value_key = series_keys[0] if series_keys else "Share"
            values = [float(r.get(value_key, 0) or 0) for r in rows]
            if sum(values) <= 0:
                plt.close(fig)
                return False
            colors = _PALETTE[: len(values)]
            wedges, _texts, autotexts = ax.pie(
                values,
                labels=labels,
                colors=colors,
                autopct="%1.1f%%",
                startangle=90,
                textprops={"fontsize": 9, "color": "#0F172A"},
            )
            for at in autotexts:
                at.set_color("white")
                at.set_fontweight("bold")
            ax.axis("equal")

        elif chart_type == "horizontal-bar":
            series_keys = _series_keys(spec, rows)
            if not series_keys:
                plt.close(fig)
                return False
            value_key = series_keys[0]
            labels = [str(r.get("x", "")) for r in rows]
            values = [float(r.get(value_key, 0) or 0) for r in rows]
            ax.barh(labels, values, color=_PALETTE[0], zorder=2)
            ax.set_xlabel(value_key + (f" ({y_unit})" if y_unit else ""))
            _style_axes(ax)
            ax.invert_yaxis()

        elif chart_type == "line":
            x_vals = [str(r.get("x", "")) for r in rows]
            series_keys = _series_keys(spec, rows)
            for i, s in enumerate(series_keys):
                y_vals = [float(r.get(s, 0) or 0) for r in rows]
                ax.plot(
                    x_vals, y_vals,
                    marker="o", linewidth=2,
                    color=_PALETTE[i % len(_PALETTE)],
                    label=s, zorder=3,
                )
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label + (f" ({y_unit})" if y_unit else ""))
            if len(series_keys) > 1:
                ax.legend(frameon=False, fontsize=9)
            ax.yaxis.set_major_formatter(_y_formatter())
            _style_axes(ax)

        elif chart_type == "stacked-bar":
            x_vals = [str(r.get("x", "")) for r in rows]
            series_keys = _series_keys(spec, rows)
            bottoms = [0.0] * len(rows)
            for i, s in enumerate(series_keys):
                y_vals = [float(r.get(s, 0) or 0) for r in rows]
                ax.bar(
                    x_vals, y_vals, bottom=bottoms,
                    color=_PALETTE[i % len(_PALETTE)],
                    label=s, zorder=2,
                )
                bottoms = [b + v for b, v in zip(bottoms, y_vals)]
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label + (f" ({y_unit})" if y_unit else ""))
            ax.legend(frameon=False, fontsize=9, ncol=min(len(series_keys), 3))
            ax.yaxis.set_major_formatter(_y_formatter())
            _style_axes(ax)

        else:  # "bar" + fallback for typos / unknown types
            x_vals = [str(r.get("x", "")) for r in rows]
            series_keys = _series_keys(spec, rows)
            if len(series_keys) == 1:
                s = series_keys[0]
                y_vals = [float(r.get(s, 0) or 0) for r in rows]
                ax.bar(x_vals, y_vals, color=_PALETTE[0], zorder=2)
            else:
                import numpy as np
                n_groups = len(rows)
                n_series = len(series_keys)
                width = 0.8 / max(n_series, 1)
                positions = np.arange(n_groups)
                for i, s in enumerate(series_keys):
                    y_vals = [float(r.get(s, 0) or 0) for r in rows]
                    ax.bar(
                        positions + i * width, y_vals, width=width,
                        color=_PALETTE[i % len(_PALETTE)],
                        label=s, zorder=2,
                    )
                ax.set_xticks(positions + width * (n_series - 1) / 2)
                ax.set_xticklabels(x_vals)
                ax.legend(frameon=False, fontsize=9, ncol=min(n_series, 3))
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label + (f" ({y_unit})" if y_unit else ""))
            ax.yaxis.set_major_formatter(_y_formatter())
            _style_axes(ax)

        if title:
            ax.set_title(title, fontsize=11, fontweight="bold", loc="left", pad=10)

        if annotations:
            caption = " · ".join(str(a) for a in annotations)
            fig.text(
                0.5, 0.02, caption,
                ha="center", fontsize=8.5, color="#475569", style="italic",
            )

        fig.tight_layout(rect=(0, 0.05 if annotations else 0, 1, 1))
        fig.savefig(output_path, dpi=140, bbox_inches="tight", facecolor="white")
        return True
    except Exception:
        return False
    finally:
        plt.close(fig)
