"""DOCX export for reports.

Eric 2026-05-21 — the DRS Industry Section deliverable needs to ship as a
.docx so it can be pasted into the prospectus draft alongside the legal
team's existing Word workflow. Same input as the PDF exporter (Report rows
with ordered sections); output is Word bytes produced via pandoc.

Requires the `pandoc` binary on PATH (added to render-build.sh for prod)
and the `pypandoc` package (in requirements.txt). The exporter raises
RuntimeError when pandoc is missing rather than silently falling back —
the analyst would not want a half-baked artifact in front of an SEC reader.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from typing import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.company import Company
from app.models.report import Report


def _pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def _section_to_markdown(title: str, body_md: str | None) -> str:
    body = body_md.strip() if body_md else "*Content pending*"
    # Belt-and-suspenders: even when the DRS prompt forbids chart-fenced JSON
    # blocks, the LLM occasionally still emits one. Convert any leftover
    # ```chart blocks to markdown tables before pandoc sees them so Word
    # doesn't show raw JSON. Eric 2026-05-21.
    from app.services.report.generator import _chart_block_to_table
    body = _chart_block_to_table(body)
    return f"# {title}\n\n{body}"


def _assemble_markdown(
    title: str,
    company_name: str,
    sections: Iterable[tuple[str, str | None]],
) -> str:
    """Stitch the title page, metadata block, and each section into one
    markdown document for pandoc to consume."""
    date_str = datetime.now().strftime("%d %B %Y")
    parts: list[str] = [
        f"% {title}",
        f"% {company_name}",
        f"% {date_str}",
        "",
    ]
    for sec_title, sec_body in sections:
        parts.append(_section_to_markdown(sec_title, sec_body))
        parts.append("")
    return "\n".join(parts)


async def generate_report_docx(
    db: AsyncSession,
    company_id: UUID,
    report_id: UUID,
) -> bytes:
    """Render a report row to a Word (.docx) document."""
    if not _pandoc_available():
        raise RuntimeError(
            "pandoc binary not found on PATH. Install pandoc "
            "(apt-get install pandoc on Render; brew install pandoc locally)."
        )

    import pypandoc  # imported lazily so the rest of the app boots without it

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
    md = _assemble_markdown(report.title, company_name, section_pairs)

    # pypandoc.convert_text returns a unicode str when outputfile is None and
    # the target is a text format; for binary formats (docx, pdf) it needs an
    # outputfile. We write to a temp file and read bytes back.
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        pypandoc.convert_text(
            md,
            to="docx",
            format="markdown+pipe_tables+grid_tables+footnotes+raw_html",
            outputfile=tmp_path,
            extra_args=["--standalone"],
        )
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
