from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class ChatConversationCreate(BaseModel):
    title: str | None = "New Conversation"


class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    metadata_: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatConversationResponse(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
