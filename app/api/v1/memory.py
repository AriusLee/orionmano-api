"""Memory and feedback API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.memory import Memory
from app.api.deps import get_current_user
from app.services.agent.memory import (
    store_memory,
    retrieve_memories,
    mark_superseded,
    export_memories,
)

router = APIRouter(tags=["memory"])


# --- Feedback endpoint (user-facing) ---

class FeedbackRequest(BaseModel):
    content: str
    company_id: UUID | None = None
    skill_name: str | None = None
    scope: str | None = None


class FeedbackResponse(BaseModel):
    id: str
    rule: str
    skill_name: str | None
    scope: str | None


@router.post("/companies/{company_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    company_id: UUID,
    req: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit explicit feedback that the system will learn from."""
    memory = await store_memory(
        db=db,
        rule="",  # will be overwritten by compression
        raw_feedback=req.content,
        company_id=company_id,
        skill_name=req.skill_name,
        scope=req.scope,
        source="explicit_feedback",
    )
    return FeedbackResponse(
        id=str(memory.id),
        rule=memory.rule,
        skill_name=memory.skill_name,
        scope=memory.scope,
    )


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_global_feedback(
    req: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit global feedback (not company-specific)."""
    memory = await store_memory(
        db=db,
        rule="",
        raw_feedback=req.content,
        company_id=req.company_id,
        skill_name=req.skill_name,
        scope=req.scope,
        source="explicit_feedback",
    )
    return FeedbackResponse(
        id=str(memory.id),
        rule=memory.rule,
        skill_name=memory.skill_name,
        scope=memory.scope,
    )


# --- Memory retrieval (for debugging / transparency) ---

class MemoryResponse(BaseModel):
    id: str
    rule: str
    skill_name: str | None
    scope: str | None
    company_id: str | None
    source: str
    status: str
    retrieval_count: int


@router.get("/companies/{company_id}/memories", response_model=list[MemoryResponse])
async def get_company_memories(
    company_id: UUID,
    skill_name: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List active memories for a company."""
    from sqlalchemy import and_
    conditions = [Memory.status == "active", Memory.company_id == company_id]
    if skill_name:
        conditions.append(Memory.skill_name == skill_name)

    result = await db.execute(
        select(Memory).where(and_(*conditions)).order_by(Memory.created_at.desc())
    )
    memories = result.scalars().all()
    return [
        MemoryResponse(
            id=str(m.id),
            rule=m.rule,
            skill_name=m.skill_name,
            scope=m.scope,
            company_id=str(m.company_id) if m.company_id else None,
            source=m.source,
            status=m.status,
            retrieval_count=m.retrieval_count,
        )
        for m in memories
    ]


# --- Admin endpoints (developer-facing) ---

@router.get("/admin/memory/export")
async def admin_export_memories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export memory analytics for developer review.
    Shows frequency patterns, skill gaps, and hard-code recommendations."""
    return await export_memories(db)


class SupersedeRequest(BaseModel):
    skill_name: str
    scope: str | None = None
    pattern: str | None = None
    reason: str = ""


@router.post("/admin/memory/mark-superseded")
async def admin_mark_superseded(
    req: SupersedeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark memories as superseded after deploying a skill upgrade."""
    count = await mark_superseded(
        db=db,
        skill_name=req.skill_name,
        scope=req.scope,
        pattern=req.pattern,
        reason=req.reason,
    )
    return {"marked": count, "reason": req.reason}


@router.delete("/admin/memory/{memory_id}")
async def admin_delete_memory(
    memory_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a specific memory."""
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    await db.delete(memory)
    await db.commit()
    return {"deleted": str(memory_id)}
