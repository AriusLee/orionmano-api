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
    target_valuation: Mapped[float | None] = mapped_column(Float)  # saved default for valuation runs; same currency × unit as the workpaper
    valuation_date: Mapped[date | None] = mapped_column(Date)  # saved default for valuation runs; per-run override still allowed on the page
    pinned_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)  # Eric 2026-05-17 — analyst-fixed params the LLM must preserve verbatim and that calibration must skip when scaling to target
    pinned_cocos: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)  # Eric 2026-05-18 — analyst-fixed include/selected_for_wacc per ticker; producer overlays onto payload.cocos after LLM
    report_tier: Mapped[str] = mapped_column(String(20), default="standard")  # essential, standard, premium
    logo_path: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    documents = relationship("Document", back_populates="company", lazy="selectin")
    reports = relationship("Report", back_populates="company", lazy="selectin")
