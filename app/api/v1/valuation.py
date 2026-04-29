"""Valuation workpaper generation endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.agent.context import AgentContext
from app.services.agent.registry import registry
from app.services.agent.skill import SkillStatus

router = APIRouter(
    prefix="/companies/{company_id}/valuation",
    tags=["valuation"],
)


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
    }


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
