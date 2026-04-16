import os
import uuid as uuid_mod
import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, async_session
from app.models.user import User
from app.models.document import Document
from app.schemas.document import DocumentResponse
from app.api.deps import get_current_user
from app.config import settings

router = APIRouter(prefix="/companies/{company_id}/documents", tags=["documents"])

# Keep references to background tasks so they don't get GC'd
_background_tasks: set[asyncio.Task] = set()


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    company_id: UUID,
    file: UploadFile = File(...),
    category: str = Form(default="other"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(company_id))
    os.makedirs(upload_dir, exist_ok=True)

    file_id = str(uuid_mod.uuid4())
    file_path = os.path.join(upload_dir, f"{file_id}_{file.filename}")

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        company_id=company_id,
        filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type,
        category=category,
        extraction_status="pending",
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Trigger extraction in background — hold reference to prevent GC
    task = asyncio.create_task(_extract_bg(doc.id, file_path, file.filename))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return doc


async def _extract_bg(doc_id: UUID, file_path: str, filename: str | None = None):
    from app.services.ai.document_parser import extract_document
    from app.services.company_intelligence import auto_fill_company

    async with async_session() as session:
        result = await session.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return
        try:
            doc.extraction_status = "processing"
            await session.commit()
            extracted = await extract_document(file_path, filename or doc.filename)
            doc.extracted_data = extracted
            # Auto-classify: sync detected categories (and primary document_type)
            # so the frontend checklist can slot the file across multiple slots.
            if isinstance(extracted, dict):
                cats = extracted.get("categories")
                if isinstance(cats, list):
                    clean = [c.strip().lower() for c in cats if isinstance(c, str) and c.strip()]
                    if clean:
                        doc.categories = clean
                        doc.category = clean[0]
                detected_type = extracted.get("document_type")
                if isinstance(detected_type, str) and detected_type.strip() and not doc.category:
                    doc.category = detected_type.strip().lower()
            doc.extraction_status = "completed"
            await session.commit()
            # Auto-fill company profile from extracted data
            await auto_fill_company(session, doc.company_id)
        except Exception as e:
            doc.extraction_status = "failed"
            doc.extraction_error = str(e)
            await session.commit()


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(Document.company_id == company_id).order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    company_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.company_id == company_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/reclassify")
async def reclassify_documents(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-run filename-based classification on every doc currently bucketed as
    'other'. Fast, no LLM calls — useful after upgrading the classifier or when
    scanned PDFs/images landed unclassified on first pass."""
    from app.services.ai.document_parser import classify_by_filename

    result = await db.execute(
        select(Document).where(
            Document.company_id == company_id,
            Document.category == "other",
        )
    )
    docs = list(result.scalars().all())
    updated = 0
    for doc in docs:
        guessed = classify_by_filename(doc.filename)
        if guessed and guessed != "other":
            doc.category = guessed
            doc.categories = [guessed]
            updated += 1
    if updated:
        await db.commit()
    return {"scanned": len(docs), "updated": updated}


@router.delete("/{document_id}")
async def delete_document(
    company_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.company_id == company_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    await db.delete(doc)
    await db.commit()
    return {"detail": "Document deleted"}
