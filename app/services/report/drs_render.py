"""Render-time transforms for the DRS Industry Section.

Eric 2026-05-25 — per-section LLM calls don't see neighbouring sections so
exhibit numbering drifts across the chapter (REMSEA shipped with Exhibit 2
and Exhibit 3 but no Exhibit 1; the regenerate dropped the Exhibit prefix
entirely on chart titles). We own the global numbering server-side: walk
every label site — a ```chart fence OR a markdown body caption that begins
with `Exhibit` — in document order, assign sequential numbers starting at
1, rewrite each site, then remap any in-prose `Exhibit N` cross-references
using a mapping built from original-to-new numbers.

Applied at both render boundaries — the .docx export AND the API response
for industry_drs reports — so on-screen view and downloaded file agree.
"""
from __future__ import annotations

import json
import re

# Match a ```chart fenced JSON block, capturing the JSON body. Mirrors the
# pattern used by docx_export._embed_chart_images so renumbering and image
# rendering see exactly the same fences.
_CHART_FENCE_RE = re.compile(r"```chart\b[ \t]*\n?([\s\S]*?)```", re.IGNORECASE)

# Body-level Exhibit caption: a whole line that opens with optional bold
# wrapping, then `Exhibit`, optional existing number, a colon, the caption
# text, optional closing bold. Anchored to line boundaries via MULTILINE.
# Colon is optional to catch `**Exhibit 2 Foo**` (no colon) variants.
_BODY_LABEL_RE = re.compile(
    r"^(?P<bold_open>\*\*)?Exhibit(?:\s+(?P<old_num>\d+))?\s*:?\s*"
    r"(?P<caption>[^\n]+?)(?P<bold_close>\*\*)?$",
    re.MULTILINE,
)

# In-prose reference like "as shown in Exhibit 2" / "see Exhibit 3 below".
_INLINE_REF_RE = re.compile(r"\bExhibit\s+(\d+)\b")

# Strip an existing "Exhibit\s*\d*\s*:" prefix from a chart JSON title so we
# can rebuild it cleanly with the new number.
_TITLE_PREFIX_RE = re.compile(r"^\s*Exhibit(?:\s+\d+)?\s*:\s*", re.IGNORECASE)
# Pull the original number (if any) out of a chart JSON title, for the
# in-prose ref remapping pass.
_TITLE_NUM_RE = re.compile(r"^\s*Exhibit\s+(\d+)\b", re.IGNORECASE)


def _scan_sites(body: str) -> tuple[list[tuple[int, int, str, re.Match]], list[tuple[int, int]]]:
    """Return (label_sites, redundant_spans). label_sites is the sorted list
    of (start, end, kind, match) for non-redundant label sites — chart
    fences plus body Exhibit captions that are NOT immediately followed by
    a chart fence. redundant_spans is the list of (start, end) ranges for
    body labels that ARE immediately followed by a chart fence (only
    whitespace between); these will be deleted from the markdown in the
    rewrite pass so the chart fence alone carries the exhibit number.

    Otherwise one chart would consume two counter slots (Eric 2026-05-25 —
    the REMSEA (8).docx showed every chart producing two Exhibit labels:
    one from the LLM's pre-chart bold paragraph, one from the chart fence
    itself).
    """
    chart_matches = list(_CHART_FENCE_RE.finditer(body))
    chart_ranges = [(m.start(), m.end()) for m in chart_matches]
    chart_starts_sorted = sorted(cs for cs, _ in chart_ranges)

    label_sites: list[tuple[int, int, str, re.Match]] = []
    redundant_spans: list[tuple[int, int]] = []
    for m in chart_matches:
        label_sites.append((m.start(), m.end(), "chart", m))
    for m in _BODY_LABEL_RE.finditer(body):
        s, e = m.start(), m.end()
        # Skip body labels that fall inside a chart fence (the JSON title
        # might contain "Exhibit" text that shouldn't double as a label).
        if any(cs <= s < ce for cs, ce in chart_ranges):
            continue
        # Redundant-pre-chart: nearest chart fence starting at/after the
        # label, with only whitespace between, means this label is the
        # LLM's redundant heading for the chart that follows.
        next_chart_start = next((cs for cs in chart_starts_sorted if cs >= e), None)
        if next_chart_start is not None and not body[e:next_chart_start].strip():
            # Stretch the deletion span to swallow the trailing whitespace
            # so we don't leave a dangling blank line.
            redundant_spans.append((s, next_chart_start))
            continue
        label_sites.append((s, e, "label", m))
    label_sites.sort(key=lambda x: x[0])
    return label_sites, redundant_spans


def _label_sites(body: str) -> list[tuple[int, int, str, re.Match]]:
    """Back-compat shim: return only the surviving label sites."""
    sites, _ = _scan_sites(body)
    return sites


def renumber_exhibits(
    sections: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    """Renumber every exhibit label across the section sequence so numbering
    starts at 1 and increments monotonically in document order.

    Two passes:
      1. Read-only: scan label sites in document order across all sections,
         build {original_num: new_num} mapping for sites that already had
         a number.
      2. Rewrite: walk each section, replace label sites with new numbers
         and replace in-prose `Exhibit N` references (outside label spans)
         via the mapping. Replacements applied end-to-start so earlier
         spans aren't invalidated by later string-length deltas.

    Returns a new list — input is not mutated.
    """
    # Pass 1 — build mapping. We don't rewrite anything here.
    counter = 0
    mapping: dict[int, int] = {}
    for _, body in sections:
        if not body:
            continue
        for start, end, kind, m in _label_sites(body):
            if kind == "chart":
                try:
                    spec = json.loads(m.group(1).strip())
                except (json.JSONDecodeError, ValueError):
                    # Malformed chart contributes nothing to numbering. The
                    # rewrite pass will skip it identically.
                    continue
                counter += 1
                title = (spec.get("title") or "").strip()
                old_match = _TITLE_NUM_RE.match(title)
                if old_match:
                    mapping[int(old_match.group(1))] = counter
            else:  # body label
                counter += 1
                old_num = m.group("old_num")
                if old_num:
                    mapping[int(old_num)] = counter

    # Pass 2 — rewrite labels (counter) and in-prose refs (mapping); also
    # delete redundant pre-chart body labels.
    counter = 0
    out: list[tuple[str, str | None]] = []
    for sec_title, body in sections:
        if not body:
            out.append((sec_title, body))
            continue

        sites, redundant_spans = _scan_sites(body)
        label_spans = [(s, e) for s, e, _, _ in sites]
        replacements: list[tuple[int, int, str]] = []

        # Drop redundant pre-chart body labels (replace with empty string).
        for rs, re_ in redundant_spans:
            replacements.append((rs, re_, ""))

        for start, end, kind, m in sites:
            if kind == "chart":
                try:
                    spec = json.loads(m.group(1).strip())
                except (json.JSONDecodeError, ValueError):
                    continue
                counter += 1
                title = (spec.get("title") or "").strip()
                stripped = _TITLE_PREFIX_RE.sub("", title).strip()
                spec["title"] = (
                    f"Exhibit {counter}: {stripped}" if stripped else f"Exhibit {counter}"
                )
                new_chunk = f"```chart\n{json.dumps(spec, ensure_ascii=False)}\n```"
                replacements.append((start, end, new_chunk))
            else:  # body label
                counter += 1
                bold_open = m.group("bold_open") or ""
                bold_close = m.group("bold_close") or ""
                caption = (m.group("caption") or "").strip()
                # If the LLM wrote `**Exhibit: foo**` the regex sometimes
                # absorbs the closing `**` into caption; strip defensively.
                if caption.endswith("**") and not bold_close:
                    caption = caption[:-2].rstrip()
                    bold_close = "**"
                replacements.append(
                    (start, end, f"{bold_open}Exhibit {counter}: {caption}{bold_close}")
                )

        # In-prose refs OUTSIDE any label span or redundant span use the mapping.
        protected_spans = label_spans + redundant_spans
        if mapping:
            for m in _INLINE_REF_RE.finditer(body):
                s = m.start()
                if any(ps <= s < pe for ps, pe in protected_spans):
                    continue
                old = int(m.group(1))
                new = mapping.get(old, old)
                if new == old:
                    continue
                replacements.append(
                    (m.start(), m.end(), m.group(0).replace(str(old), str(new), 1))
                )

        new_body = body
        for start, end, new_chunk in sorted(replacements, key=lambda x: x[0], reverse=True):
            new_body = new_body[:start] + new_chunk + new_body[end:]
        out.append((sec_title, new_body))

    return out
