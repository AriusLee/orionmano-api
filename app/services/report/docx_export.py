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
        # Markdown image — pandoc embeds the PNG inline in the .docx. Caption
        # underneath kept as italicized source attribution.
        parts: list[str] = [""]
        if title:
            parts.append(f"**{title}**")
            parts.append("")
        parts.append(f"![{title or 'Chart'}]({png_path})")
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
) -> str:
    """Stitch the title page, metadata block, and each section into one
    markdown document for pandoc to consume. Chart PNGs are rendered into
    asset_dir as a side-effect of section assembly."""
    date_str = datetime.now().strftime("%d %B %Y")
    parts: list[str] = [
        f"% {title}",
        f"% {company_name}",
        f"% {date_str}",
        "",
    ]
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

    # All chart PNGs + the pandoc output land in a single temp dir so cleanup
    # is one rmtree call. Pandoc resolves the absolute image paths embedded
    # in the markdown when it builds the .docx.
    with tempfile.TemporaryDirectory(prefix="orionmano_docx_") as tmp_dir:
        asset_dir = Path(tmp_dir)
        md = _assemble_markdown(report.title, company_name, section_pairs, asset_dir)
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
        with open(docx_path, "rb") as f:
            return f.read()
