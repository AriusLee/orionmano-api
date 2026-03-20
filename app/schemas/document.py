from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class DocumentResponse(BaseModel):
    id: UUID
    company_id: UUID
    filename: str
    file_size: int | None = None
    mime_type: str | None = None
    category: str | None = None
    extraction_status: str
    extracted_data: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
