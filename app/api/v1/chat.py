import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models.user import User
from app.models.chat import ChatConversation, ChatMessage
from app.schemas.chat import (
    ChatConversationCreate,
    ChatConversationResponse,
    ChatMessageCreate,
    ChatMessageResponse,
)
from app.api.deps import get_current_user
from app.services.chat.chat_service import chat_stream

router = APIRouter(prefix="/companies/{company_id}/chat", tags=["chat"])


@router.post("/conversations", response_model=ChatConversationResponse)
async def create_conversation(
    company_id: UUID,
    req: ChatConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = ChatConversation(
        company_id=company_id,
        user_id=user.id,
        title=req.title or "New Conversation",
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ChatConversationResponse])
async def list_conversations(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatConversation)
        .where(ChatConversation.company_id == company_id, ChatConversation.user_id == user.id)
        .order_by(ChatConversation.updated_at.desc().nulls_last(), ChatConversation.created_at.desc())
    )
    return result.scalars().all()


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageResponse])
async def get_messages(
    company_id: UUID,
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    company_id: UUID,
    conversation_id: UUID,
    req: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify conversation exists
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.company_id == company_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    async def event_generator():
        async for chunk in chat_stream(db, conversation_id, company_id, req.content):
            yield {"event": "message", "data": json.dumps({"content": chunk})}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())
