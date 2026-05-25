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


def _label_sites(body: str) -> list[tuple[int, int, str, re.Match]]:
    """Return all (start, end, kind, match) tuples for label sites in body,
    sorted by document position. A label site is either a ```chart fence
    OR a body caption line starting with `Exhibit`. Body labels whose
    position falls inside a chart fence are excluded (the chart's own JSON
    might contain "Exhibit" text that shouldn't double as a body label).
    """
    chart_matches = list(_CHART_FENCE_RE.finditer(body))
    chart_ranges = [(m.start(), m.end()) for m in chart_matches]
    sites: list[tuple[int, int, str, re.Match]] = []
    for m in chart_matches:
        sites.append((m.start(), m.end(), "chart", m))
    for m in _BODY_LABEL_RE.finditer(body):
        s = m.start()
        if any(cs <= s < ce for cs, ce in chart_ranges):
            continue
        sites.append((m.start(), m.end(), "label", m))
    sites.sort(key=lambda x: x[0])
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

    # Pass 2 — rewrite labels (counter) and in-prose refs (mapping).
    counter = 0
    out: list[tuple[str, str | None]] = []
    for sec_title, body in sections:
        if not body:
            out.append((sec_title, body))
            continue

        sites = _label_sites(body)
        label_spans = [(s, e) for s, e, _, _ in sites]
        replacements: list[tuple[int, int, str]] = []

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

        # In-prose refs OUTSIDE any label span use the mapping.
        if mapping:
            for m in _INLINE_REF_RE.finditer(body):
                s = m.start()
                if any(ls <= s < le for ls, le in label_spans):
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
