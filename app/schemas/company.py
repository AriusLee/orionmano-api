from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date


class CompanyCreate(BaseModel):
    name: str
    legal_name: str | None = None
    registration_number: str | None = None
    date_of_incorporation: date | None = None
    company_type: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    country: str = "Malaysia"
    description: str | None = None
    website: str | None = None
    engagement_type: str | None = None
    target_exchange: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    registration_number: str | None = None
    date_of_incorporation: date | None = None
    company_type: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    country: str | None = None
    description: str | None = None
    website: str | None = None
    engagement_type: str | None = None
    target_exchange: str | None = None
    report_tier: str | None = None


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    legal_name: str | None = None
    registration_number: str | None = None
    date_of_incorporation: date | None = None
    company_type: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    country: str
    description: str | None = None
    website: str | None = None
    status: str
    enterprise_stage: str | None = None
    engagement_type: str | None = None
    target_exchange: str | None = None
    report_tier: str = "standard"
    logo_path: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
