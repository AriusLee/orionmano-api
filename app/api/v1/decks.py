from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services.deck.generator import generate_deck_pdf

router = APIRouter(prefix="/companies/{company_id}/decks", tags=["decks"])


@router.get("/{deck_type}/pdf")
async def download_deck_pdf(
    company_id: UUID,
    deck_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        pdf_bytes = await generate_deck_pdf(db, company_id, deck_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{deck_type}.pdf"'},
    )
