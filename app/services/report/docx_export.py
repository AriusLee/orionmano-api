"""DOCX export for reports.

Eric 2026-05-21 — the DRS Industry Section deliverable needs to ship as a
.docx so it can be pasted into the prospectus draft alongside the legal
team's existing Word workflow. Same input as the PDF exporter (Report rows
with ordered sections); output is Word bytes produced via pandoc.

Eric 2026-05-22 — for the DRS to look like a real S-1 industry chapter,
chart fenced JSON blocks are rendered to PNG images (matplotlib) and
embedded inline as `![](path)` markdown image refs. Pandoc resolves those
references and embeds the PNGs as real Word images. Fallback when a chart
spec fails to render: the existing `_chart_block_to_table` helper emits a
clean markdown table so no raw JSON ever leaks into the final doc.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.company import Company
from app.models.report import Report

# Match ```chart fences whether the JSON starts on a new line or inline on
# the same line as the opener — matches the PDF renderer's pattern exactly.
_CHART_FENCE_RE = re.compile(r"```chart\b[ \t]*\n?([\s\S]*?)```", re.IGNORECASE)


def _embed_chart_images(
    body_md: str,
    asset_dir: Path,
    counter: list[int],
) -> str:
    """Render every ```chart fenced JSON spec to a PNG in asset_dir and
    rewrite the fence as a markdown image reference. Falls back to the
    markdown-table conversion when the spec is malformed or matplotlib
    fails. `counter` is a one-element list used as a mutable int so chart
    indices stay unique across sections within a single export."""
    from app.services.report.chart_png_renderer import render_chart_spec_to_png
    from app.services.report.generator import _chart_block_to_table

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        try:
            spec = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Unparseable — let _chart_block_to_table strip it cleanly.
            return _chart_block_to_table(f"```chart\n{raw}\n```")
        counter[0] += 1
        png_path = asset_dir / f"chart_{counter[0]}.png"
        ok = render_chart_spec_to_png(spec, str(png_path))
        if not ok:
            return _chart_block_to_table(f"```chart\n{raw}\n```")
        title = spec.get("title", "")
        source_note = spec.get("source_note") or ""
        # Markdown image. Eric 2026-05-25 — previously we ALSO emitted a
        # `**{title}**` bold paragraph above the image, but pandoc already
        # creates an Image Caption from the image alt text, so the title
        # was rendering twice (bold pre-caption + Image Caption beneath the
        # PNG). Now we emit ONLY the image — pandoc renders one captioned
        # figure with the title as caption — and the italicized source
        # note immediately below.
        parts: list[str] = ["", f"![{title or 'Chart'}]({png_path})"]
        if source_note:
            parts.append("")
            parts.append(f"*{source_note}*")
        parts.append("")
        return "\n".join(parts)

    return _CHART_FENCE_RE.sub(_replace, body_md)


def _section_to_markdown(
    title: str,
    body_md: str | None,
    asset_dir: Path,
    chart_counter: list[int],
) -> str:
    body = body_md.strip() if body_md else "*Content pending*"
    body = _embed_chart_images(body, asset_dir, chart_counter)
    return f"# {title}\n\n{body}"


def _assemble_markdown(
    title: str,
    company_name: str,
    sections: Iterable[tuple[str, str | None]],
    asset_dir: Path,
    preamble: str | None = None,
) -> str:
    """Stitch the title page, metadata block, optional preamble, and each
    section into one markdown document for pandoc to consume. Chart PNGs are
    rendered into asset_dir as a side-effect of section assembly. `preamble`
    is rendered as italicized text immediately after the title page and
    before the first section heading (used for the DRS legal disclosure)."""
    date_str = datetime.now().strftime("%d %B %Y")
    parts: list[str] = [
        f"% {title}",
        f"% {company_name}",
        f"% {date_str}",
        "",
    ]
    if preamble:
        # Italicized in pandoc markdown; matches the Frost & Sullivan-style
        # opening paragraph in real S-1 industry chapters.
        parts.append(f"*{preamble}*")
        parts.append("")
    chart_counter = [0]
    for sec_title, sec_body in sections:
        parts.append(_section_to_markdown(sec_title, sec_body, asset_dir, chart_counter))
        parts.append("")
    return "\n".join(parts)


async def generate_report_docx(
    db: AsyncSession,
    company_id: UUID,
    report_id: UUID,
) -> bytes:
    """Render a report row to a Word (.docx) document."""
    import pypandoc  # lazy: pypandoc_binary ships its own bundled pandoc

    result = await db.execute(
        select(Report)
        .options(selectinload(Report.sections))
        .where(Report.id == report_id, Report.company_id == company_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise ValueError("Report not found")

    comp_result = await db.execute(select(Company).where(Company.id == company_id))
    company = comp_result.scalar_one_or_none()
    company_name = company.name if company else "Company"

    ordered = sorted(report.sections, key=lambda s: s.sort_order)
    section_pairs = [(s.section_title, s.content) for s in ordered]

    # DRS Industry Section opens with the OM Assurance / OM Report disclosure
    # (Eric 2026-05-24) — same text the on-screen viewer renders, sourced
    # from disclosure.industry_drs_disclosure for single-source-of-truth.
    # Also renumber Exhibit N references globally so the chapter sequence
    # starts at 1 (Eric 2026-05-25 — REMSEA shipped with 2, 3 and no 1).
    preamble: str | None = None
    if report.report_type == "industry_drs":
        from app.services.report.disclosure import industry_drs_disclosure
        from app.services.report.drs_render import renumber_exhibits
        preamble = industry_drs_disclosure(company_name)
        section_pairs = renumber_exhibits(section_pairs)

    # All chart PNGs + the pandoc output land in a single temp dir so cleanup
    # is one rmtree call. Pandoc resolves the absolute image paths embedded
    # in the markdown when it builds the .docx.
    with tempfile.TemporaryDirectory(prefix="orionmano_docx_") as tmp_dir:
        asset_dir = Path(tmp_dir)
        md = _assemble_markdown(report.title, company_name, section_pairs, asset_dir, preamble=preamble)
        docx_path = asset_dir / "out.docx"
        try:
            pypandoc.convert_text(
                md,
                to="docx",
                format="markdown+pipe_tables+grid_tables+footnotes+raw_html",
                outputfile=str(docx_path),
                extra_args=["--standalone", f"--resource-path={asset_dir}"],
            )
        except OSError as e:
            # pypandoc_binary couldn't locate the bundled pandoc — surface a
            # clear error rather than letting the OSError bubble unhelpfully.
            raise RuntimeError(
                f"DOCX export failed because pandoc could not be invoked: {e}. "
                "Confirm `pypandoc_binary` is installed (pip install -r requirements.txt)."
            ) from e

        # Post-process: pandoc's default markdown→docx converter ships tables
        # with no visible borders (Eric 2026-05-25 screenshot) — the columns
        # are just whitespace-separated, which looks unprofessional in a
        # prospectus exhibit. Apply 0.5pt black borders to every table so
        # peer-comparison and market-size tables render with proper grid
        # lines matching standard S-1 formatting.
        _apply_table_borders(docx_path)

        with open(docx_path, "rb") as f:
            return f.read()


def _apply_table_borders(docx_path: Path) -> None:
    """Open the pandoc-generated .docx and apply 0.5pt single black borders
    (top / bottom / left / right / inside-horizontal / inside-vertical) to
    every table. Borders are written directly to each table's `<w:tblPr>`
    via the OOXML schema so every cell inherits them — independent of
    whether the document carries a `Table Grid` style definition.
    """
    from docx import Document as _Doc
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def _border_element(edge: str) -> OxmlElement:
        b = OxmlElement(f"w:{edge}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")  # half-points → 0.5pt
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "000000")
        return b

    doc = _Doc(str(docx_path))
    for table in doc.tables:
        tblPr = table._tbl.tblPr
        # Drop any existing tblBorders so we don't double-stack edges.
        existing = tblPr.find(qn("w:tblBorders"))
        if existing is not None:
            tblPr.remove(existing)
        tblBorders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            tblBorders.append(_border_element(edge))
        tblPr.append(tblBorders)
    doc.save(str(docx_path))
