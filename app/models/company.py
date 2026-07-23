import uuid
from datetime import datetime, date
from typing import Any

from sqlalchemy import Float, String, Text, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    date_of_incorporation: Mapped[date | None] = mapped_column(Date)
    company_type: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(255))
    sub_industry: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(100), default="Malaysia")
    description: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="active")
    enterprise_stage: Mapped[str | None] = mapped_column(String(50))
    engagement_type: Mapped[str | None] = mapped_column(String(50))
    target_exchange: Mapped[str | None] = mapped_column(String(50))
    fye_annual: Mapped[str | None] = mapped_column(String(50))  # financial year end (annual audit), e.g. "31 December" — anchors how the AI aligns audited figures
    fye_interim: Mapped[str | None] = mapped_column(String(50))  # financial year end (interim), e.g. "30 June 2025" — cut-off for the latest interim/management period
    target_valuation: Mapped[float | None] = mapped_column(Float)  # saved default for valuation runs; ACTUAL currency units
    target_valuation_basis: Mapped[str | None] = mapped_column(String(20), default="enterprise_value")  # what the target represents: enterprise_value | equity_value (equity = after DLOM/DLOC, post EV-to-equity bridge)
    presentation_currency: Mapped[str | None] = mapped_column(String(8), default="USD")  # deliverable currency (workpaper + report); source docs may be in another currency — producer converts at a cited FX rate. Null = let the AI infer from documents
    valuation_date: Mapped[date | None] = mapped_column(Date)  # saved default for valuation runs; per-run override still allowed on the page
    pinned_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)  # Eric 2026-05-17 — analyst-fixed params the LLM must preserve verbatim and that calibration must skip when scaling to target
    pinned_cocos: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)  # Eric 2026-05-18 — analyst-fixed include/selected_for_wacc per ticker; producer overlays onto payload.cocos after LLM
    business_development_plan: Mapped[str | None] = mapped_column(Text)  # Eric 2026-05-19 #9 — analyst-supplied BDP narrative; producer treats as authoritative context for revenue/growth/margin justification
    additional_revenue_streams: Mapped[list[Any] | None] = mapped_column(JSONB, default=list)  # user-defined revenue streams [{name, description, base_year_revenue, start_year, growth_override, gross_margin_override, opex_pct_override, contractual_support}]; producer maps onto projections.segments, web-researches growth when no override
    industry_report_addendum: Mapped[str | None] = mapped_column(Text)  # Eric 2026-05-23 — analyst-supplied disclosures (BDP highlights, recent launches, niche context) injected into industry_report generation as authoritative context
    report_tier: Mapped[str] = mapped_column(String(20), default="standard")  # essential, standard, premium
    logo_path: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    documents = relationship("Document", back_populates="company", lazy="selectin")
    reports = relationship("Report", back_populates="company", lazy="selectin")
