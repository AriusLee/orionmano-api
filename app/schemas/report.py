from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class ReportGenerateRequest(BaseModel):
    report_type: str  # industry_report, dd_report, valuation_report, sales_deck, kickoff_deck, teaser, company_deck
    tier: str = "standard"  # essential, standard, premium


class ReportSectionUpdate(BaseModel):
    content: str


class ReportSectionResponse(BaseModel):
    id: UUID
    section_key: str
    section_title: str
    content: str | None = None
    content_data: dict | None = None
    sort_order: int
    is_ai_generated: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    id: UUID
    company_id: UUID
    report_type: str
    title: str
    status: str
    language: str
    version: int
    progress_message: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    sections: list[ReportSectionResponse] = []

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    id: UUID
    company_id: UUID
    report_type: str
    title: str
    status: str
    tier: str = "standard"
    language: str
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}
