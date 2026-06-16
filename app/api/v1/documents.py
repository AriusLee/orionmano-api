import os
import uuid as uuid_mod
import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
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

# Bound how many documents extract concurrently. Each extraction makes a slow
# LLM call; without this, bulk upload or "Re-extract all" fans out one task per
# document and — combined with holding a DB connection across that call — blew
# the async pool (QueuePool size 5 + overflow 10) on Render. The semaphore is
# acquired BEFORE any DB session is opened, so waiting tasks hold no connection.
_EXTRACT_CONCURRENCY = 3
_extract_sem: asyncio.Semaphore | None = None


def _get_extract_sem() -> asyncio.Semaphore:
    # Lazily created so it binds to the running event loop.
    global _extract_sem
    if _extract_sem is None:
        _extract_sem = asyncio.Semaphore(_EXTRACT_CONCURRENCY)
    return _extract_sem


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


async def _extract_bg(
    doc_id: UUID,
    file_path: str,
    filename: str | None = None,
    recompile: bool = True,
) -> UUID | None:
    """Extract a document in the background. Holds a DB connection only for the
    brief status/result writes — NEVER across the slow LLM call — and caps global
    concurrency via the semaphore. Returns the company_id when extraction
    completed (so a bulk caller can recompile once at the end). When
    ``recompile`` is True a per-doc KB recompile is kicked off; bulk callers pass
    False and recompile once themselves."""
    from app.services.ai.document_parser import extract_document
    from app.services.company_intelligence import auto_fill_company

    async with _get_extract_sem():
        # 1) Short session: mark processing + read the filename, then release.
        async with async_session() as session:
            doc = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
            if not doc:
                return None
            fname = filename or doc.filename
            doc.extraction_status = "processing"
            await session.commit()

        # 2) Slow LLM extraction — no DB connection held here.
        try:
            extracted = await extract_document(file_path, fname)
        except Exception as e:
            async with async_session() as session:
                doc = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
                if doc:
                    doc.extraction_status = "failed"
                    doc.extraction_error = str(e)
                    await session.commit()
            return None

        # 3) Short session: persist the result + classify + auto-fill company.
        company_id_for_recompile: UUID | None = None
        async with async_session() as session:
            doc = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
            if not doc:
                return None
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
            await auto_fill_company(session, doc.company_id)
            company_id_for_recompile = doc.company_id

    # Recompile the company's KB pages outside the semaphore/session. Bulk
    # callers skip this and recompile once after all docs finish.
    if recompile and company_id_for_recompile is not None:
        from app.services.kb.compile import recompile_company

        async def _recompile_safe(cid: UUID) -> None:
            try:
                await recompile_company(cid)
            except Exception:
                pass

        task = asyncio.create_task(_recompile_safe(company_id_for_recompile))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return company_id_for_recompile


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


@router.post("/{document_id}/reextract", response_model=DocumentResponse)
async def reextract_document(
    company_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-run extraction on an already-uploaded document, in place. Useful after
    upgrading the parser (e.g. Office formats that previously failed) — the file
    is already on disk, so no re-upload is needed. Reuses the same background
    extraction path as upload, including KB recompile."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.company_id == company_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File missing on disk — re-upload required")

    doc.extraction_status = "pending"
    doc.extraction_error = None
    await db.commit()
    await db.refresh(doc)

    task = asyncio.create_task(_extract_bg(doc.id, doc.file_path, doc.filename))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return doc


@router.post("/reextract-all")
async def reextract_all_documents(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-run extraction on every document for the company whose file still
    exists on disk. Kicks one background task per doc and returns immediately;
    the frontend polls extraction_status as usual. Extraction concurrency is
    bounded by the semaphore in _extract_bg, and the KB is recompiled ONCE after
    all docs finish (not per-doc)."""
    result = await db.execute(select(Document).where(Document.company_id == company_id))
    docs = list(result.scalars().all())

    items: list[tuple[UUID, str, str]] = []
    for doc in docs:
        if not doc.file_path or not os.path.exists(doc.file_path):
            continue
        doc.extraction_status = "pending"
        doc.extraction_error = None
        items.append((doc.id, doc.file_path, doc.filename))
    if items:
        await db.commit()

    task = asyncio.create_task(_reextract_all_bg(company_id, items))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"total": len(docs), "queued": len(items)}


async def _reextract_all_bg(company_id: UUID, items: list[tuple[UUID, str, str]]) -> None:
    """Re-extract a batch with bounded concurrency (via _extract_bg's semaphore),
    skipping per-doc recompiles, then recompile the company's KB exactly once."""
    if not items:
        return
    await asyncio.gather(
        *(_extract_bg(doc_id, fp, fn, recompile=False) for doc_id, fp, fn in items),
        return_exceptions=True,
    )
    from app.services.kb.compile import recompile_company
    try:
        await recompile_company(company_id)
    except Exception:
        pass


@router.get("/{document_id}/raw")
async def get_document_raw(
    company_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream the original file. Auth-gated via the standard JWT bearer.
    Frontend fetches as Blob (via apiFetch) and renders in a modal — iframes
    can't carry custom auth headers, so the file isn't loaded via direct URL."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.company_id == company_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(
        doc.file_path,
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.filename,
        content_disposition_type="inline",
    )


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
