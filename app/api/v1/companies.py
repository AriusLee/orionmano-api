import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, async_session
from app.models.user import User
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/companies", tags=["companies"])

# Keep references to background tasks so the event loop doesn't GC them
_background_tasks: set[asyncio.Task] = set()


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

    # Kick off logo lookup in the background. Uses LLM to guess the website
    # first if the user didn't supply one, then runs the multi-strategy
    # logo_fetcher (Clearbit → Google Favicon → og:image → favicon).
    task = asyncio.create_task(_auto_fetch_logo_bg(company.id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return company


async def _auto_fetch_logo_bg(company_id: UUID):
    from app.services.ai.logo_fetcher import fetch_logo
    from app.services.ai.website_lookup import guess_website

    async with async_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        c = result.scalar_one_or_none()
        if not c or c.logo_path:
            return

        website = c.website
        if not website:
            guessed = await guess_website(
                name=c.name,
                legal_name=c.legal_name,
                industry=c.industry,
                country=c.country,
            )
            if guessed:
                website = guessed
                # Persist the guessed domain so future fetches / UI links work.
                c.website = guessed

        try:
            logo_path = await fetch_logo(c.name, website)
        except Exception:
            logo_path = None

        if logo_path:
            c.logo_path = logo_path

        # Always commit so the website guess is saved even if logo lookup fails.
        await session.commit()


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

    # Shareholders & key personnel — aggregated across all extracted docs, deduped by uppercased name
    shareholders: list[dict] = []
    personnel: list[dict] = []
    sh_seen: dict[str, int] = {}
    kp_seen: dict[str, int] = {}
    org_chart_summary: str | None = None

    for doc in documents:
        if not (doc.extracted_data and doc.extraction_status == "completed"):
            continue
        data = doc.extracted_data
        # Capture the first non-empty org_chart narrative summary (often from vision extraction of images)
        if org_chart_summary is None:
            dtype = data.get("document_type")
            cats = data.get("categories") or []
            is_org = dtype == "org_chart" or "org_chart" in (cats if isinstance(cats, list) else [])
            summary = data.get("summary")
            if is_org and isinstance(summary, str) and summary.strip():
                org_chart_summary = summary.strip()

        for sh in data.get("shareholders") or []:
            if not isinstance(sh, dict):
                continue
            name = (sh.get("name") or "").strip()
            if not name:
                continue
            key = name.upper()
            entry = {
                "name": name,
                "shares": sh.get("shares"),
                "percentage": sh.get("percentage"),
                "source": doc.filename,
            }
            if key in sh_seen:
                # Prefer the entry that has percentage/shares data
                existing = shareholders[sh_seen[key]]
                if existing.get("percentage") is None and entry["percentage"] is not None:
                    shareholders[sh_seen[key]] = entry
                elif existing.get("shares") is None and entry["shares"] is not None:
                    shareholders[sh_seen[key]] = entry
            else:
                sh_seen[key] = len(shareholders)
                shareholders.append(entry)

        for kp in data.get("key_personnel") or []:
            if not isinstance(kp, dict):
                continue
            name = (kp.get("name") or "").strip()
            if not name:
                continue
            key = name.upper()
            entry = {
                "name": name,
                "title": (kp.get("title") or "").strip() or None,
                "background": (kp.get("background") or "").strip() or None,
                "source": doc.filename,
            }
            if key in kp_seen:
                existing = personnel[kp_seen[key]]
                if not existing.get("background") and entry["background"]:
                    personnel[kp_seen[key]] = entry
            else:
                kp_seen[key] = len(personnel)
                personnel.append(entry)

    # Sort shareholders by percentage desc (nulls last), personnel: directors first
    def _pct(s): return -(s.get("percentage") or 0)
    shareholders.sort(key=_pct)

    def _rank(p):
        t = (p.get("title") or "").upper()
        if "DIRECTOR" in t: return 0
        if "CEO" in t or "CHIEF EXECUTIVE" in t: return 1
        if "CFO" in t or "CHIEF FINANCIAL" in t: return 2
        if "CHAIR" in t: return 3
        if "SECRETARY" in t: return 9
        return 5
    personnel.sort(key=_rank)

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
    timeline.sort(key=lambda x: x["timestamp"] or "")

    return {
        "risk_flags": unique_flags,
        "financial_snapshot": financial_snapshot,
        "cross_reference": cross_ref,
        "shareholders": shareholders,
        "key_personnel": personnel,
        "org_chart_summary": org_chart_summary,
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


@router.post("/{company_id}/fetch-logo")
async def fetch_company_logo(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch and store the company logo from their website."""
    from app.services.ai.logo_fetcher import fetch_logo

    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    logo_path = await fetch_logo(company.name, company.website)
    if logo_path:
        company.logo_path = logo_path
        await db.commit()
        return {"logo_path": logo_path, "status": "fetched"}
    return {"logo_path": None, "status": "not_found"}
