"""Deck API — prompt-driven generation with theme selection, amend loop, and
version history.

Endpoint layout:
    GET    /decks/themes                          — list available themes
    GET    /decks/presets                         — list preset prompts
    GET    /companies/{cid}/decks                 — list decks for a company
    POST   /companies/{cid}/decks                 — generate a new deck
    GET    /decks/{deck_id}                       — get spec + versions
    GET    /decks/{deck_id}/pdf                   — render PDF
    GET    /decks/{deck_id}/html                  — render HTML (preview)
    POST   /decks/{deck_id}/amend                 — prompt-driven amendment
    POST   /decks/{deck_id}/theme                 — swap theme
    POST   /decks/{deck_id}/restore/{version_no}  — roll back to a prior version
    DELETE /decks/{deck_id}                       — delete deck + history

The legacy template-based endpoint (GET /companies/{cid}/decks/{deck_type}/pdf)
is retained for backwards compatibility while the frontend migrates — see
the LEGACY section at the bottom.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.deck import Deck, DeckVersion
from app.models.user import User
from app.services.deck.ai_generator import (
    PRESETS,
    amend_deck_spec,
    generate_deck_spec,
)
from app.services.deck.renderer import render_html, render_pdf
from app.services.deck.schema import SlideSpec
from app.services.deck.themes import get_theme, list_themes

router = APIRouter(tags=["decks"])


# ---------------------------------------------------------------------------
# Request / response shapes.
# ---------------------------------------------------------------------------


class GenerateDeckRequest(BaseModel):
    theme_id: str = "orionmano_navy"
    prompt: str | None = None
    preset: str | None = Field(None, description="Optional preset name; prefills prompt if prompt is empty.")


class AmendDeckRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class SwapThemeRequest(BaseModel):
    theme_id: str


class ThemeOut(BaseModel):
    id: str
    name: str
    description: str
    page_size: str
    primary: str
    background: str


class PresetOut(BaseModel):
    id: str
    name: str
    prompt: str


class DeckListItem(BaseModel):
    id: str
    title: str
    theme_id: str
    preset: str | None
    status: str
    slide_count: int
    current_version: int
    created_at: str | None
    updated_at: str | None


class DeckVersionOut(BaseModel):
    version_no: int
    theme_id: str
    source: str
    prompt: str | None
    created_at: str | None


class DeckDetail(BaseModel):
    id: str
    company_id: str
    title: str
    theme_id: str
    preset: str | None
    prompt: str
    status: str
    current_version: int
    spec: dict[str, Any]
    versions: list[DeckVersionOut]
    created_at: str | None
    updated_at: str | None


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

_PRESET_LABELS = {
    "sales_deck": "Sales Deck",
    "kickoff_deck": "Kick-off Deck",
    "teaser": "Investor Teaser",
    "company_deck": "Company Deck",
}


def _deck_to_list_item(d: Deck) -> DeckListItem:
    spec = d.spec or {}
    slides = spec.get("slides", []) if isinstance(spec, dict) else []
    return DeckListItem(
        id=str(d.id),
        title=d.title,
        theme_id=d.theme_id,
        preset=d.preset,
        status=d.status,
        slide_count=len(slides),
        current_version=d.current_version,
        created_at=d.created_at.isoformat() if d.created_at else None,
        updated_at=d.updated_at.isoformat() if d.updated_at else None,
    )


def _deck_to_detail(d: Deck) -> DeckDetail:
    return DeckDetail(
        id=str(d.id),
        company_id=str(d.company_id),
        title=d.title,
        theme_id=d.theme_id,
        preset=d.preset,
        prompt=d.prompt or "",
        status=d.status,
        current_version=d.current_version,
        spec=d.spec or {},
        versions=[
            DeckVersionOut(
                version_no=v.version_no,
                theme_id=v.theme_id,
                source=v.source,
                prompt=v.prompt,
                created_at=v.created_at.isoformat() if v.created_at else None,
            )
            for v in (d.versions or [])
        ],
        created_at=d.created_at.isoformat() if d.created_at else None,
        updated_at=d.updated_at.isoformat() if d.updated_at else None,
    )


async def _load_deck(db: AsyncSession, deck_id: UUID) -> Deck:
    result = await db.execute(select(Deck).where(Deck.id == deck_id))
    deck = result.scalar_one_or_none()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


# ---------------------------------------------------------------------------
# Themes + presets (lookup endpoints).
# ---------------------------------------------------------------------------


@router.get("/decks/themes", response_model=list[ThemeOut])
async def list_themes_endpoint(user: User = Depends(get_current_user)):
    return [
        ThemeOut(
            id=t.id,
            name=t.name,
            description=t.description,
            page_size=t.page_size,
            primary=t.primary,
            background=t.background,
        )
        for t in list_themes()
    ]


@router.get("/decks/presets", response_model=list[PresetOut])
async def list_presets_endpoint(user: User = Depends(get_current_user)):
    return [
        PresetOut(id=pid, name=_PRESET_LABELS.get(pid, pid), prompt=p)
        for pid, p in PRESETS.items()
    ]


# ---------------------------------------------------------------------------
# Per-company endpoints.
# ---------------------------------------------------------------------------


@router.get("/companies/{company_id}/decks", response_model=list[DeckListItem])
async def list_company_decks(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Deck).where(Deck.company_id == company_id).order_by(Deck.created_at.desc())
    )
    return [_deck_to_list_item(d) for d in result.scalars().all()]


@router.post("/companies/{company_id}/decks", response_model=DeckDetail)
async def create_deck(
    company_id: UUID,
    body: GenerateDeckRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    prompt = (body.prompt or "").strip()
    preset = body.preset
    if not prompt and not preset:
        raise HTTPException(status_code=400, detail="Provide a prompt or pick a preset.")
    if not prompt and preset:
        prompt = PRESETS.get(preset, "")
        if not prompt:
            raise HTTPException(status_code=400, detail=f"Unknown preset: {preset}")

    try:
        get_theme(body.theme_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        spec = await generate_deck_spec(
            db,
            company_id=company_id,
            theme_id=body.theme_id,
            prompt=prompt,
            preset=preset,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deck generation failed: {e}")

    deck = Deck(
        company_id=company_id,
        title=spec.title,
        theme_id=body.theme_id,
        preset=preset,
        prompt=prompt,
        spec=spec.model_dump(),
        current_version=1,
        status="ready",
        created_by=user.id,
    )
    db.add(deck)
    await db.flush()

    db.add(DeckVersion(
        deck_id=deck.id,
        version_no=1,
        spec=spec.model_dump(),
        theme_id=body.theme_id,
        source="generate",
        prompt=prompt,
        created_by=user.id,
    ))
    await db.commit()
    await db.refresh(deck)
    return _deck_to_detail(deck)


# ---------------------------------------------------------------------------
# Per-deck endpoints.
# ---------------------------------------------------------------------------


@router.get("/decks/{deck_id}", response_model=DeckDetail)
async def get_deck(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deck = await _load_deck(db, deck_id)
    return _deck_to_detail(deck)


@router.get("/decks/{deck_id}/pdf")
async def get_deck_pdf(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deck = await _load_deck(db, deck_id)
    spec = SlideSpec.model_validate(deck.spec)
    theme = get_theme(deck.theme_id)
    pdf_bytes = render_pdf(spec, theme)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{_safe_filename(deck.title)}.pdf"'},
    )


@router.get("/decks/{deck_id}/html", response_class=HTMLResponse)
async def get_deck_html(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Browser-friendly HTML preview — same render, no WeasyPrint roundtrip.
    Useful for fast iteration in the deck viewer."""
    deck = await _load_deck(db, deck_id)
    spec = SlideSpec.model_validate(deck.spec)
    theme = get_theme(deck.theme_id)
    return HTMLResponse(render_html(spec, theme))


@router.post("/decks/{deck_id}/amend", response_model=DeckDetail)
async def amend_deck(
    deck_id: UUID,
    body: AmendDeckRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deck = await _load_deck(db, deck_id)
    current_spec = SlideSpec.model_validate(deck.spec)
    try:
        new_spec = await amend_deck_spec(
            db,
            company_id=deck.company_id,
            current_spec=current_spec,
            prompt=body.prompt,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Amend failed: {e}")

    new_version = deck.current_version + 1
    deck.spec = new_spec.model_dump()
    deck.title = new_spec.title
    deck.current_version = new_version

    db.add(DeckVersion(
        deck_id=deck.id,
        version_no=new_version,
        spec=new_spec.model_dump(),
        theme_id=deck.theme_id,
        source="amend",
        prompt=body.prompt,
        created_by=user.id,
    ))
    await db.commit()
    await db.refresh(deck)
    return _deck_to_detail(deck)


@router.post("/decks/{deck_id}/theme", response_model=DeckDetail)
async def swap_deck_theme(
    deck_id: UUID,
    body: SwapThemeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        get_theme(body.theme_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    deck = await _load_deck(db, deck_id)
    if deck.theme_id == body.theme_id:
        return _deck_to_detail(deck)

    new_version = deck.current_version + 1
    spec = dict(deck.spec or {})
    spec["theme_id"] = body.theme_id

    deck.spec = spec
    deck.theme_id = body.theme_id
    deck.current_version = new_version

    db.add(DeckVersion(
        deck_id=deck.id,
        version_no=new_version,
        spec=spec,
        theme_id=body.theme_id,
        source="theme_swap",
        prompt=None,
        created_by=user.id,
    ))
    await db.commit()
    await db.refresh(deck)
    return _deck_to_detail(deck)


@router.post("/decks/{deck_id}/restore/{version_no}", response_model=DeckDetail)
async def restore_deck_version(
    deck_id: UUID,
    version_no: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deck = await _load_deck(db, deck_id)
    target = next((v for v in (deck.versions or []) if v.version_no == version_no), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Version {version_no} not found")

    new_version = deck.current_version + 1
    spec = dict(target.spec or {})
    # Keep restored spec's theme; sync the deck row to match.
    deck.spec = spec
    deck.theme_id = target.theme_id
    deck.title = spec.get("title", deck.title)
    deck.current_version = new_version

    db.add(DeckVersion(
        deck_id=deck.id,
        version_no=new_version,
        spec=spec,
        theme_id=target.theme_id,
        source="restore",
        prompt=None,
        created_by=user.id,
    ))
    await db.commit()
    await db.refresh(deck)
    return _deck_to_detail(deck)


@router.delete("/decks/{deck_id}")
async def delete_deck(
    deck_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deck = await _load_deck(db, deck_id)
    await db.delete(deck)  # cascade-deletes versions via ondelete="CASCADE"
    await db.commit()
    return {"deleted": True, "id": str(deck_id)}


# ---------------------------------------------------------------------------
# LEGACY — kept until the frontend migrates off the type-specific URL.
# ---------------------------------------------------------------------------


@router.get("/companies/{company_id}/decks/{deck_type}/pdf")
async def legacy_download_deck_pdf(
    company_id: UUID,
    deck_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Old template-based generator. Frozen — new work goes through the
    prompt-driven endpoints above."""
    from app.services.deck.generator import generate_deck_pdf

    try:
        pdf_bytes = await generate_deck_pdf(db, company_id, deck_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{deck_type}.pdf"'},
    )


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _safe_filename(title: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title).strip()
    return safe[:80] or "deck"
