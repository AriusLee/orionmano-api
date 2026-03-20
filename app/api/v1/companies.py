from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("", response_model=CompanyResponse)
async def create_company(
    req: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company = Company(**req.model_dump(), created_by=user.id)
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@router.get("", response_model=list[CompanyResponse])
async def list_companies(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Company).order_by(Company.created_at.desc()))
    return result.scalars().all()


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    req: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(company, key, value)
    await db.commit()
    await db.refresh(company)
    return company


@router.get("/{company_id}/intelligence")
async def get_company_intelligence(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns risk flags, financial snapshot, document cross-reference, and activity timeline."""
    from app.models.document import Document
    from app.models.report import Report
    from app.services.company_intelligence import detect_risk_flags

    # Get company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Get documents
    doc_result = await db.execute(
        select(Document).where(Document.company_id == company_id).order_by(Document.created_at)
    )
    documents = list(doc_result.scalars().all())

    # Get reports
    report_result = await db.execute(
        select(Report).where(Report.company_id == company_id).order_by(Report.created_at)
    )
    reports = list(report_result.scalars().all())

    # Risk flags from all extracted data
    risk_flags = []
    for doc in documents:
        if doc.extracted_data and doc.extraction_status == "completed":
            risk_flags.extend(detect_risk_flags(doc.extracted_data))
    # Deduplicate by title
    seen = set()
    unique_flags = []
    for f in risk_flags:
        if f["title"] not in seen:
            seen.add(f["title"])
            unique_flags.append(f)

    # Financial snapshot from extracted data
    financial_snapshot = None
    for doc in documents:
        if doc.extracted_data and doc.extraction_status == "completed":
            fin = doc.extracted_data.get("financial_data", {})
            if isinstance(fin, dict) and fin.get("income_statement"):
                financial_snapshot = fin
                break

    # Document cross-reference
    extracted_count = sum(1 for d in documents if d.extraction_status == "completed")
    doc_types = set()
    for doc in documents:
        if doc.extracted_data:
            dt = doc.extracted_data.get("document_type")
            if dt:
                doc_types.add(dt)

    cross_ref = {
        "total_documents": len(documents),
        "extracted": extracted_count,
        "processing": sum(1 for d in documents if d.extraction_status in ("pending", "processing")),
        "failed": sum(1 for d in documents if d.extraction_status == "failed"),
        "document_types": list(doc_types),
        "cross_referenced": extracted_count >= 2,
    }

    # Activity timeline
    timeline = []
    timeline.append({
        "type": "company_created",
        "title": "Company created",
        "detail": company.name,
        "timestamp": company.created_at.isoformat() if company.created_at else None,
    })
    for doc in documents:
        timeline.append({
            "type": "document_uploaded",
            "title": f"Document uploaded",
            "detail": doc.filename,
            "timestamp": doc.created_at.isoformat() if doc.created_at else None,
        })
        if doc.extraction_status == "completed":
            timeline.append({
                "type": "extraction_completed",
                "title": "AI extraction completed",
                "detail": doc.filename,
                "timestamp": doc.created_at.isoformat() if doc.created_at else None,
            })
    for report in reports:
        timeline.append({
            "type": "report_generated",
            "title": f"Report generated",
            "detail": report.title,
            "timestamp": report.created_at.isoformat() if report.created_at else None,
        })
    timeline.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    return {
        "risk_flags": unique_flags,
        "financial_snapshot": financial_snapshot,
        "cross_reference": cross_ref,
        "timeline": timeline[:20],
    }


@router.get("/{company_id}/summary")
async def get_executive_summary(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.company_intelligence import generate_executive_summary
    summary = await generate_executive_summary(db, company_id)
    return {"summary": summary}
