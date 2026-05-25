import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.database import get_db, async_session
from app.models.user import User
from app.models.report import Report, ReportSection
from app.schemas.report import (
    ReportGenerateRequest,
    ReportResponse,
    ReportListResponse,
    ReportSectionUpdate,
    ReportSectionResponse,
)
from app.api.deps import get_current_user

router = APIRouter(prefix="/companies/{company_id}/reports", tags=["reports"])


@router.post("/generate", response_model=ReportListResponse)
async def trigger_generate(
    company_id: UUID,
    req: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.report.generator import REPORT_TITLES

    report = Report(
        company_id=company_id,
        report_type=req.report_type,
        tier=req.tier,
        title=f"Generating {REPORT_TITLES.get(req.report_type, req.report_type)}...",
        status="pending",
        created_by=user.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    asyncio.create_task(_generate_bg(company_id, req.report_type, user.id, report.id))
    return report


async def _generate_bg(company_id: UUID, report_type: str, user_id: UUID, report_id: UUID):
    from app.services.report.generator import generate_report_bg
    async with async_session() as db:
        await generate_report_bg(db, company_id, report_type, report_id)


@router.get("", response_model=list[ReportListResponse])
async def list_reports(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Report).where(Report.company_id == company_id).order_by(Report.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{report_id}", status_code=204)
async def delete_report(
    company_id: UUID,
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.company_id == company_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    await db.execute(delete(ReportSection).where(ReportSection.report_id == report_id))
    await db.delete(report)
    await db.commit()
    return Response(status_code=204)


@router.post("/{report_id}/regenerate", response_model=ReportListResponse)
async def regenerate_report(
    company_id: UUID,
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-run report generation against the current workpaper, in place.

    Eric 2026-05-19 — analyst wants to iterate on the written narrative
    without re-running the producer. This endpoint deletes the existing
    sections, resets the Report row to pending, and re-kicks the
    generator background task. The Report row id stays the same so the
    URL/View Report link remains valid.
    """
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.company_id == company_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status == "generating":
        raise HTTPException(
            status_code=409,
            detail="Report is already regenerating — wait for the current run to finish.",
        )

    await db.execute(delete(ReportSection).where(ReportSection.report_id == report_id))
    report.status = "pending"
    report.error_message = None
    report.progress_message = None
    await db.commit()

    asyncio.create_task(_generate_bg(company_id, report.report_type, user.id, report.id))
    return report


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    company_id: UUID,
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Report)
        .options(selectinload(Report.sections), selectinload(Report.company))
        .where(Report.id == report_id, Report.company_id == company_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    # Industry-DRS-specific render: build the response, then mutate it.
    # Mutating the ORM row directly would mark `content` dirty and let
    # autoflush persist the renumbering — we want the transform to be a
    # render-time concern, leaving the stored content untouched. So we
    # validate into a Pydantic response and mutate that.
    if report.report_type == "industry_drs":
        from app.services.report.disclosure import industry_drs_disclosure
        from app.services.report.drs_render import renumber_exhibits

        response = ReportResponse.model_validate(report)
        response.disclosure_preamble = industry_drs_disclosure(
            report.company.name if report.company else "the Company"
        )
        # Sections come back in sort_order via the eager-load above; the
        # renumbering mapping is built from that same global order.
        ordered_sections = sorted(response.sections, key=lambda s: s.sort_order)
        remapped = renumber_exhibits([(s.section_title, s.content) for s in ordered_sections])
        for sec, (_, new_body) in zip(ordered_sections, remapped):
            sec.content = new_body
        return response
    return report


@router.post("/{report_id}/validate-citations")
async def validate_citations(
    company_id: UUID,
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run / re-run the citation-health snapshot for an industry report.

    Article IDs are sourced from (in priority order):
      1. The existing `report.citation_health.article_ids` if populated.
      2. Parsed from the report's section content — matches every markdown
         footnote link whose URL begins with `settings.ARTICLE_SITE_BASE_URL`,
         then looks up the article by slug. Lets us bootstrap a snapshot for
         reports that finished before the citation-health flow shipped."""
    result = await db.execute(
        select(Report)
        .options(selectinload(Report.sections))
        .where(Report.id == report_id, Report.company_id == company_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    existing = report.citation_health or {}
    raw_ids = existing.get("article_ids") if isinstance(existing, dict) else None

    from uuid import UUID as _UUID
    typed_ids: list[_UUID] = []
    if raw_ids:
        for aid in raw_ids:
            try:
                typed_ids.append(_UUID(aid))
            except (TypeError, ValueError):
                continue

    if not typed_ids:
        # Bootstrap from section content — parse every markdown footnote URL
        # under the article-site base, look up by slug.
        from app.config import settings
        from app.services.article.generator import extract_cited_article_slugs
        from app.models.published_article import PublishedArticle
        slugs: list[str] = []
        for s in report.sections:
            slugs.extend(extract_cited_article_slugs(s.content or "", settings.ARTICLE_SITE_BASE_URL))
        # Dedupe preserving order
        slugs = list(dict.fromkeys(slugs))
        if slugs:
            slug_result = await db.execute(
                select(PublishedArticle.id, PublishedArticle.slug)
                .where(PublishedArticle.slug.in_(slugs))
            )
            id_by_slug = {row[1]: row[0] for row in slug_result.all()}
            for slug in slugs:
                if slug in id_by_slug:
                    typed_ids.append(id_by_slug[slug])

    if not typed_ids:
        # Genuinely no citations in this report — write an empty all-ok snapshot
        # so the frontend stops showing the indefinite spinner.
        from app.services.article.generator import _snapshot_citation_health, _save_citation_snapshot
        snap = await _snapshot_citation_health([], in_flight=False)
        await _save_citation_snapshot(report_id, snap)
        return {
            "status": "no_citations",
            "article_ids": [],
            "citation_health": snap,
            "message": "No citations found in this report.",
        }

    from app.services.article.generator import (
        initialize_citation_snapshot,
        run_citation_heal_loop,
    )
    # Synchronously: reset stuck articles + write the in-flight snapshot so the
    # response carries an immediately-visible progress state. The heal loop
    # itself (sequential article generation, ~30-60s each) runs detached.
    initial_snapshot = await initialize_citation_snapshot(report_id, typed_ids)
    asyncio.create_task(run_citation_heal_loop(report_id, typed_ids))
    return {
        "status": "queued",
        "article_ids": [str(i) for i in typed_ids],
        "citation_health": initial_snapshot,
        "message": (
            f"Re-validation kicked off for {len(typed_ids)} citation(s). "
            f"The banner will show live progress as each article generates."
        ),
    }


@router.patch("/{report_id}/sections/{section_key}", response_model=ReportSectionResponse)
async def update_section(
    company_id: UUID,
    report_id: UUID,
    section_key: str,
    req: ReportSectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ReportSection).where(
            ReportSection.report_id == report_id,
            ReportSection.section_key == section_key,
        )
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    section.content = req.content
    section.is_ai_generated = False
    section.last_edited_by = user.id
    await db.commit()
    await db.refresh(section)
    return section


@router.post("/{report_id}/lint/fix")
async def autofix_lint_finding(
    company_id: UUID,
    report_id: UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Auto-patch the two sections involved in a single lint finding.

    Body: {"finding_index": int}.
    Returns: {"status": "fixed"|"rejected", "lint_findings": [...], "updated_sections": [section_key,...], "message": str}.

    Resolution flow:
    1. Load report + sections + lint_findings
    2. Pick finding[finding_index]; locate section_a / section_b by title
    3. Pull kb pages as ground truth (if any)
    4. Ask the LLM for minimal-change replacements
    5. On success: update both sections, re-run lint, persist new findings
    6. On rejection (over-rewrite, parse failure, etc.): leave sections untouched
    """
    from app.services.report.lint import apply_lint_fix, lint_report
    from app.services.kb.reader import get_kb_pages, format_kb_pages_for_prompt

    finding_index = payload.get("finding_index")
    if not isinstance(finding_index, int):
        raise HTTPException(status_code=400, detail="finding_index (int) required")

    result = await db.execute(
        select(Report).options(selectinload(Report.sections)).where(
            Report.id == report_id, Report.company_id == company_id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    findings = report.lint_findings or []
    if not (0 <= finding_index < len(findings)):
        raise HTTPException(status_code=400, detail=f"finding_index {finding_index} out of range (0..{len(findings) - 1})")

    finding = findings[finding_index]
    title_a = (finding.get("section_a") or "").strip().lower()
    title_b = (finding.get("section_b") or "").strip().lower()
    section_a = next((s for s in report.sections if (s.section_title or "").strip().lower() == title_a), None)
    section_b = next((s for s in report.sections if (s.section_title or "").strip().lower() == title_b), None)
    if section_a is None or section_b is None:
        raise HTTPException(
            status_code=400,
            detail=f"could not locate sections by title (a={finding.get('section_a')!r}, b={finding.get('section_b')!r})",
        )
    if section_a.id == section_b.id:
        raise HTTPException(status_code=400, detail="section_a and section_b resolve to the same section")

    kb_pages = await get_kb_pages(db, company_id)
    ground_truth = format_kb_pages_for_prompt(kb_pages) if kb_pages else None

    new_a, new_b, error = await apply_lint_fix(
        report_id=report_id,
        company_id=company_id,
        finding=finding,
        section_a=section_a,
        section_b=section_b,
        ground_truth=ground_truth,
    )
    if error or new_a is None or new_b is None:
        return {
            "status": "rejected",
            "lint_findings": findings,
            "updated_sections": [],
            "message": error or "auto-fix produced no replacement",
        }

    section_a.content = new_a
    section_a.is_ai_generated = False
    section_a.last_edited_by = user.id
    section_b.content = new_b
    section_b.is_ai_generated = False
    section_b.last_edited_by = user.id
    await db.commit()

    # Re-lint the updated report so the panel shows fresh findings
    await db.refresh(report)
    new_findings = await lint_report(
        report_id=report.id,
        company_id=report.company_id,
        sections=sorted(report.sections, key=lambda s: s.sort_order),
    )
    report.lint_findings = new_findings
    await db.commit()

    return {
        "status": "fixed",
        "lint_findings": new_findings,
        "updated_sections": [section_a.section_key, section_b.section_key],
        "message": f"patched {section_a.section_title} + {section_b.section_title}; lint re-ran",
    }


@router.get("/{report_id}/docx")
async def export_report_docx(
    company_id: UUID,
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Render a report row to a Word (.docx) document.

    Eric 2026-05-21 — DRS Industry Section ships as .docx so legal can paste
    it into the prospectus draft. Other report_types can also use this
    endpoint when a Word deliverable is preferred over PDF.
    """
    from app.services.report.docx_export import generate_report_docx
    try:
        docx_bytes = await generate_report_docx(db, company_id, report_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        # Pandoc missing on host — surface as 500 with a clear message so the
        # deploy team knows to add the binary.
        raise HTTPException(status_code=500, detail=str(e))
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="report.docx"'},
    )


@router.get("/{report_id}/pdf")
async def export_report_pdf(
    company_id: UUID,
    report_id: UUID,
    lang: str = "en",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.report.pdf_export import generate_report_pdf
    try:
        pdf_bytes = await generate_report_pdf(db, company_id, report_id, lang=lang)
    except ValueError as e:
        # Lang validation and "report not found" both raise ValueError;
        # use 400 for the lang case (it's a bad query param).
        if "lang" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    suffix = f"-{lang}" if lang != "en" else ""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="report{suffix}.pdf"'},
    )
