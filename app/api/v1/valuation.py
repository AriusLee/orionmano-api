"""Valuation workpaper generation endpoint."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.agent.context import AgentContext
from app.services.agent.registry import registry
from app.services.agent.skill import SkillStatus

router = APIRouter(
    prefix="/companies/{company_id}/valuation",
    tags=["valuation"],
)


def _valuations_dir() -> Path:
    return (Path(settings.UPLOAD_DIR).resolve() / "valuations")


def _latest_summary_for(company_id: UUID) -> dict | None:
    """Find the most recent .summary.json belonging to this company.

    Files are named `valuation-{slug}-{DDMMYYYY}.summary.json` (no UUID in
    the filename), so we glob all summaries and filter by the `company_id`
    field stored inside each one. Returns the freshest by mtime.
    """
    d = _valuations_dir()
    if not d.exists():
        return None
    cid = str(company_id)
    candidates: list[tuple[float, dict]] = []
    for p in d.glob("valuation-*.summary.json"):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("company_id") != cid:
            continue
        candidates.append((p.stat().st_mtime, data))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


@router.post("/generate-workpaper")
async def generate_workpaper(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate the populated Excel valuation workpaper for a company.

    Pipeline:
      1. produce_valuation_inputs — Claude reads extracted documents and produces
         JSON conforming to the inputs-sheet schema.
      2. export_workpaper — fills the v1 skeleton xlsx from the JSON, validates,
         writes to {UPLOAD_DIR}/valuations/.

    Returns the download URL plus any validation warnings.
    """
    skill = registry.get("generate_valuation_workpaper")
    if skill is None:
        raise HTTPException(
            status_code=500,
            detail="generate_valuation_workpaper skill not registered",
        )

    ctx = AgentContext(db=db, company_id=company_id, user_id=user.id)
    result = await skill.execute(ctx)

    if result.status == SkillStatus.FAILED:
        raise HTTPException(status_code=500, detail=result.message)

    payload = result.data or {}
    return {
        "status": result.status.value,
        "message": result.message,
        "xlsx_url": payload.get("xlsx_url"),
        "warnings": payload.get("warnings", []),
        "errors": payload.get("errors", []),
        "summary": payload.get("summary"),
    }


@router.get("/latest")
async def latest_workpaper(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the most-recent generated workpaper summary for this company.

    Reads the .summary.json file written alongside each xlsx in
    {UPLOAD_DIR}/valuations/. Returns 404 if no workpaper has been generated.
    """
    summary = _latest_summary_for(company_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="No valuation workpaper generated yet")
    return summary


@router.post("/produce-inputs")
async def produce_inputs(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Produce the valuation inputs JSON without writing an xlsx.

    Useful for previewing what the AI extracted before committing to a workpaper.
    """
    skill = registry.get("produce_valuation_inputs")
    if skill is None:
        raise HTTPException(
            status_code=500,
            detail="produce_valuation_inputs skill not registered",
        )

    ctx = AgentContext(db=db, company_id=company_id, user_id=user.id)
    result = await skill.execute(ctx)

    if result.status == SkillStatus.FAILED:
        raise HTTPException(status_code=500, detail=result.message)

    return {
        "status": result.status.value,
        "message": result.message,
        "inputs_json": result.data,
        "usage": result.artifacts.get("usage", {}),
    }
