import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    company_id: UUID,
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Report)
        .options(selectinload(Report.sections))
        .where(Report.id == report_id, Report.company_id == company_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


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


@router.get("/{report_id}/pdf")
async def export_report_pdf(
    company_id: UUID,
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.report.pdf_export import generate_report_pdf
    try:
        pdf_bytes = await generate_report_pdf(db, company_id, report_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="report.pdf"'},
    )
