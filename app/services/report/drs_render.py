"""Render-time transforms for the DRS Industry Section.

Eric 2026-05-25 — per-section LLM calls don't see neighbouring sections so
chart titles drift across the chapter (REMSEA shipped with Exhibit 2 and
Exhibit 3 but no Exhibit 1). We own the global numbering server-side: walk
every ```chart fence in document order, build an old→new mapping, and
rewrite both the JSON title field and any in-prose "Exhibit N" references.

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

# Match the word "Exhibit" followed by a number. Case-insensitive so we
# catch "exhibit 2" inline references the model occasionally lowercases.
_EXHIBIT_REF_RE = re.compile(r"\bExhibit\s+(\d+)\b", re.IGNORECASE)


def _section_chart_numbers(body: str) -> list[int]:
    """Return the list of original 'Exhibit N' numbers found in chart JSON
    titles in body, in document order. Charts whose JSON fails to parse or
    whose title lacks an Exhibit prefix contribute nothing."""
    nums: list[int] = []
    for m in _CHART_FENCE_RE.finditer(body):
        try:
            spec = json.loads(m.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue
        title = spec.get("title") or ""
        em = _EXHIBIT_REF_RE.search(title)
        if em:
            nums.append(int(em.group(1)))
    return nums


def renumber_exhibits(
    sections: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    """Renumber every 'Exhibit N' reference across the section sequence so
    numbering starts at 1 and increments monotonically in document order.

    Walks each section body in the order supplied, scans every ```chart
    fence's JSON title, builds a {original_num: new_num} mapping, then
    rewrites every Exhibit reference in every body using that mapping.
    In-prose references to numbers that never appeared in any chart title
    are left untouched (mapping.get falls through to the original).

    Returns a new list — input is not mutated.
    """
    mapping: dict[int, int] = {}
    counter = 1
    for _, body in sections:
        if not body:
            continue
        for original in _section_chart_numbers(body):
            if original not in mapping:
                mapping[original] = counter
                counter += 1

    if not mapping:
        return list(sections)

    def _remap(text: str) -> str:
        def _sub(m: re.Match) -> str:
            old = int(m.group(1))
            new = mapping.get(old, old)
            # Preserve the literal "Exhibit" capitalization the writer chose
            # — replace only the number, leave the surrounding word as-is.
            return m.group(0).replace(str(old), str(new), 1)
        return _EXHIBIT_REF_RE.sub(_sub, text)

    out: list[tuple[str, str | None]] = []
    for title, body in sections:
        out.append((title, _remap(body) if body else body))
    return out
