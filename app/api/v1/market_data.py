"""Market Data Supported valuation report (Eric 2026-10, item 4)."""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.report import Report
from app.models.user import User
from app.services.valuation_model import market, versions

router = APIRouter(prefix="/companies/{company_id}/valuation/market-evidence", tags=["market-data"])

_tasks: set[asyncio.Task] = set()


@router.get("")
async def get_evidence(
    company_id: UUID,
    version_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evidence for a version (default: the active one) plus its Market Data
    Supported reports."""
    v = (await versions.get_version(db, company_id, version_id)) if version_id else await versions.active_version(db, company_id)
    if v is None:
        return {"version": None, "rows": [], "reports": [], "assumptions": [a.label for a in market.ASSUMPTIONS]}
    rows = await market.evidence_for(db, v.id)
    reports = (await db.execute(
        select(Report)
        .where(Report.company_id == company_id, Report.valuation_version_id == v.id, Report.variant == "market_supported")
        .order_by(Report.created_at.desc())
    )).scalars().all()
    return {
        "version": versions.to_list_item(v),
        "rows": [market.evidence_dict(r) for r in rows],
        "running": any(r.assessment == "pending" for r in rows),
        "reports": [
            {"id": str(r.id), "title": r.title, "status": r.status, "progress_message": r.progress_message,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in reports
        ],
        "assumptions": [a.label for a in market.ASSUMPTIONS],
    }


class RunBody(BaseModel):
    version_id: UUID | None = None
    keys: list[str] | None = None
    make_report: bool = True


@router.post("")
async def run(
    company_id: UUID,
    body: RunBody | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search live market data for each key assumption (or just `keys`), then
    generate the Market Data Supported report unless make_report is false."""
    body = body or RunBody()
    if body.keys:
        unknown = [k for k in body.keys if k not in market.BY_KEY]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown assumptions: {', '.join(unknown)}")
    try:
        v = await market.start(db, company_id, body.version_id, user.id, keys=body.keys, make_report=body.make_report)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "running", "version_id": str(v.id), "version_no": v.version_no}


class ReportBody(BaseModel):
    version_id: UUID | None = None


@router.post("/report")
async def make_report(
    company_id: UUID,
    body: ReportBody | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate (another) Market Data Supported report from the evidence already gathered."""
    v = (await versions.get_version(db, company_id, body.version_id)) if body and body.version_id else await versions.active_version(db, company_id)
    if v is None:
        raise HTTPException(status_code=400, detail="Generate a valuation workpaper first")
    rows = await market.evidence_for(db, v.id)
    if not any(r.assessment not in ("pending", "failed") for r in rows):
        raise HTTPException(status_code=400, detail="Run the market data check first")
    task = asyncio.create_task(market.create_report(company_id, v.id, user.id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"status": "generating"}
