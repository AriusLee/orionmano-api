"""Confirmed historical figures (Eric 2026-10, items 1–2)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.financials import store
from app.services.financials.catalogue import normalize_period

router = APIRouter(prefix="/companies/{company_id}/financials", tags=["financials"])


@router.get("")
async def get_financials(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Every period and figure, with source document + page, open
    discrepancies and the amendment log."""
    return await store.table(db, company_id)


class PeriodCreate(BaseModel):
    label: str
    end_date: date | None = None


@router.post("/periods")
async def create_period(
    company_id: UUID,
    body: PeriodCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        p = await store.create_period(db, company_id, body.label, body.end_date)
    except store.FinancialsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(p.id), "label": p.label}


class LockBody(BaseModel):
    locked: bool
    reason: str | None = None


@router.post("/periods/{period_id}/lock")
async def lock_period(
    company_id: UUID,
    period_id: UUID,
    body: LockBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lock a confirmed period (or unlock it, with a reason)."""
    try:
        p = await store.set_lock(db, company_id, period_id, body.locked, user.id, body.reason)
    except store.FinancialsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(p.id), "label": p.label, "locked": p.locked}


class FigureEdit(BaseModel):
    period_id: UUID
    line_item: str
    value: float | None = None
    reason: str | None = None
    currency: str | None = None
    unit: str | None = None
    source_page: str | None = None


@router.put("/figures")
async def edit_figure(
    company_id: UUID,
    body: FigureEdit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set or clear one figure by hand. Locked periods need a reason."""
    try:
        await store.edit_figure(
            db, company_id,
            period_id=body.period_id,
            line_item=body.line_item,
            value=body.value,
            reason=body.reason,
            user_id=user.id,
            currency=body.currency,
            unit=body.unit,
            source_page=body.source_page,
        )
    except store.FinancialsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


class ResolveBody(BaseModel):
    accept: bool
    reason: str | None = None


@router.post("/discrepancies/{discrepancy_id}/resolve")
async def resolve_discrepancy(
    company_id: UUID,
    discrepancy_id: UUID,
    body: ResolveBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Accept the document's value (logged as an amendment) or dismiss it."""
    try:
        d = await store.resolve_discrepancy(db, company_id, discrepancy_id, body.accept, user.id, body.reason)
    except store.FinancialsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(d.id), "status": d.status}


@router.post("/resync")
async def resync(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-read all extracted documents into unlocked periods. Locked periods
    and hand-entered figures are never changed; differences become discrepancies."""
    return await store.sync_company(db, company_id)


@router.get("/period-options")
async def period_options(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Periods offered by the upload form's "This document is for" picker."""
    data = await store.table(db, company_id)
    return [{"label": p["label"], "locked": p["locked"]} for p in data["periods"]]


@router.get("/normalize-period")
async def normalize(label: str, user: User = Depends(get_current_user)):
    norm, ptype, year = normalize_period(label)
    return {"label": norm, "period_type": ptype, "fiscal_year": year}
