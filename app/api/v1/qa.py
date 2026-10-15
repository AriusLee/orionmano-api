"""Counterparty Q&A on the valuation (Eric 2026-10, item 3)."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.company import Company
from app.models.qa import QaBatch
from app.models.user import User
from app.services.agent.skills.produce_valuation_inputs import PINNABLE_PARAMS
from app.services.valuation_model import model_io, qa, versions

router = APIRouter(prefix="/companies/{company_id}/qa", tags=["qa"])


def _bad(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


async def _batch(db: AsyncSession, company_id: UUID, batch_id: UUID) -> QaBatch:
    b = (await db.execute(
        select(QaBatch).where(QaBatch.id == batch_id, QaBatch.company_id == company_id)
    )).scalar_one_or_none()
    if b is None:
        raise HTTPException(status_code=404, detail="Question set not found")
    return b


@router.get("/batches")
async def list_batches(company_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(QaBatch).where(QaBatch.company_id == company_id).order_by(QaBatch.created_at.desc())
    )).scalars().all()
    return [await qa.batch_dict(db, b, with_items=False) for b in rows]


@router.post("/batches")
async def create_batch(
    company_id: UUID,
    title: str = Form(default=""),
    text: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    answer: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """New question set from pasted text and/or an uploaded file. Answers
    start drafting straight away unless answer=false."""
    raw = text or ""
    filename = None
    if file is not None and file.filename:
        filename = file.filename
        try:
            raw = (raw + "\n\n" + qa.text_from_upload(file.filename, await file.read())).strip()
        except qa.QaError as e:
            raise _bad(e)
    if not raw.strip():
        raise HTTPException(status_code=400, detail="Paste the questions or upload a file")
    questions = await qa.split_questions(raw)
    try:
        batch = await qa.create_batch(
            db, company_id,
            title=title or (re.sub(r"\.[a-z0-9]+$", "", filename, flags=re.I) if filename else ""),
            questions=questions,
            source_filename=filename,
            user_id=user.id,
        )
    except qa.QaError as e:
        raise _bad(e)
    if answer:
        qa.start_answering(batch.id)
    return await qa.batch_dict(db, batch)


@router.get("/batches/{batch_id}")
async def get_batch(company_id: UUID, batch_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    b = await _batch(db, company_id, batch_id)
    await db.refresh(b)
    return await qa.batch_dict(db, b)


@router.delete("/batches/{batch_id}", status_code=204)
async def delete_batch(company_id: UUID, batch_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    b = await _batch(db, company_id, batch_id)
    if any(i.status == "applying" for i in b.items):
        raise HTTPException(status_code=409, detail="A change is being applied — wait for it to finish")
    await db.delete(b)
    await db.commit()
    return Response(status_code=204)


class AnswerBody(BaseModel):
    item_ids: list[UUID] | None = None


@router.post("/batches/{batch_id}/answer")
async def answer(company_id: UUID, batch_id: UUID, body: AnswerBody | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Draft answers for unanswered questions, or redraft the given ones."""
    b = await _batch(db, company_id, batch_id)
    if b.status == "answering":
        raise HTTPException(status_code=409, detail="Already drafting answers")
    qa.start_answering(b.id, body.item_ids if body else None)
    return {"status": "answering"}


class ItemPatch(BaseModel):
    question: str | None = None
    simplified_answer: str | None = None
    detailed_answer: str | None = None


@router.patch("/items/{item_id}")
async def patch_item(company_id: UUID, item_id: UUID, body: ItemPatch, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        await qa.update_item(db, company_id, item_id, question=body.question,
                             simplified_answer=body.simplified_answer, detailed_answer=body.detailed_answer)
    except qa.QaError as e:
        raise _bad(e)
    return {"ok": True}


class ChangeCreate(BaseModel):
    param_key: str
    new_value: float
    rationale: str | None = None


@router.post("/items/{item_id}/changes")
async def add_change(company_id: UUID, item_id: UUID, body: ChangeCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        c = await qa.add_change(db, company_id, item_id, param_key=body.param_key, new_value=body.new_value, rationale=body.rationale)
    except qa.QaError as e:
        raise _bad(e)
    return {"id": str(c.id)}


class DecideBody(BaseModel):
    approve: bool
    new_value: float | None = None


@router.post("/changes/{change_id}/decide")
async def decide(company_id: UUID, change_id: UUID, body: DecideBody, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        c = await qa.decide_change(db, company_id, change_id, approve=body.approve, new_value=body.new_value, user_id=user.id)
    except qa.QaError as e:
        raise _bad(e)
    return {"id": str(c.id), "status": c.status, "impact": c.impact}


@router.get("/items/{item_id}/impact")
async def item_impact(company_id: UUID, item_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Combined effect of this question's approved changes on the current model."""
    try:
        return {"impact": await qa.combined_impact(db, company_id, item_id)}
    except qa.QaError as e:
        raise _bad(e)


class ApplyBody(BaseModel):
    pin: bool = True


@router.post("/items/{item_id}/apply")
async def apply(company_id: UUID, item_id: UUID, body: ApplyBody | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Approved changes → new valuation version + report, linked to the question."""
    try:
        item = await qa.apply_item(db, company_id, item_id, user.id, pin=body.pin if body else True)
    except qa.QaError as e:
        raise _bad(e)
    return {"status": item.status}


@router.get("/params")
async def params(company_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Parameters a Q&A change may touch, with the active version's values."""
    v = await versions.active_version(db, company_id)
    inputs = v.inputs if v else {}
    return [
        {
            "key": k,
            "label": model_io.PARAM_LABELS.get(k, k),
            "kind": kind,
            "value": model_io.param_value(inputs, k),
            "display": model_io.format_param(k, model_io.param_value(inputs, k), v.currency if v else None, v.unit if v else None),
        }
        for k, (_path, kind) in PINNABLE_PARAMS.items()
    ]


@router.get("/batches/{batch_id}/export")
async def export(company_id: UUID, batch_id: UUID, format: str = "xlsx", db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    b = await _batch(db, company_id, batch_id)
    data = await qa.batch_dict(db, b)
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one()
    safe = re.sub(r"[^A-Za-z0-9]+", "-", f"{company.name} {b.title}").strip("-")[:80] or "qa"
    if format == "docx":
        body = qa.export_docx(data, company.name)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        name = f"{safe}.docx"
    else:
        body = qa.export_xlsx(data)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        name = f"{safe}.xlsx"
    return Response(content=body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})
