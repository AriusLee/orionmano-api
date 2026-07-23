from pydantic import BaseModel, computed_field
from typing import Any
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
    fye_annual: str | None = None
    fye_interim: str | None = None
    target_valuation: float | None = None
    target_valuation_basis: str | None = None
    valuation_date: date | None = None
    pinned_overrides: dict[str, Any] | None = None
    pinned_cocos: dict[str, Any] | None = None
    business_development_plan: str | None = None
    additional_revenue_streams: list[dict[str, Any]] | None = None
    industry_report_addendum: str | None = None


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
    fye_annual: str | None = None
    fye_interim: str | None = None
    target_valuation: float | None = None
    target_valuation_basis: str | None = None
    valuation_date: date | None = None
    pinned_overrides: dict[str, Any] | None = None
    pinned_cocos: dict[str, Any] | None = None
    business_development_plan: str | None = None
    additional_revenue_streams: list[dict[str, Any]] | None = None
    industry_report_addendum: str | None = None
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
    fye_annual: str | None = None
    fye_interim: str | None = None
    target_valuation: float | None = None
    target_valuation_basis: str | None = None
    valuation_date: date | None = None
    pinned_overrides: dict[str, Any] | None = None
    pinned_cocos: dict[str, Any] | None = None
    business_development_plan: str | None = None
    additional_revenue_streams: list[dict[str, Any]] | None = None
    industry_report_addendum: str | None = None
    report_tier: str = "standard"
    logo_path: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def logo_url(self) -> str | None:
        """HTTP path (relative to backend origin) under /uploads, suitable for
        the frontend to prepend with the backend base URL. Derived from
        logo_path, which is stored as a filesystem path."""
        if not self.logo_path:
            return None
        normalized = self.logo_path.replace("\\", "/")
        marker = "/uploads/"
        idx = normalized.find(marker)
        if idx == -1:
            return None
        return normalized[idx:]
