"""Confirmed historical financial figures (Eric 2026-10, items 1 and 2).

Before this, a company's historical figures existed only inside each
document's `extracted_data` blob, and the valuation producer re-derived the
five historical years with an LLM on every run. Uploading one new document
could therefore shift figures for earlier periods that had already been
agreed.

Now each figure is a row: one value per (period, line item), with the source
document and page it came from. A period can be LOCKED once confirmed; after
that, nothing re-derives it:
  - extraction never overwrites it (a different value becomes a discrepancy
    for review instead),
  - the valuation producer writes locked values into `historical_fs`
    verbatim,
  - an analyst can still amend a locked figure, but it takes an explicit
    reason and is logged in `financial_figure_amendments`.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import String, Float, Text, Boolean, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    # Canonical label, e.g. "FY2024", "H1_2025" (see services/financials/catalogue.normalize_period_label).
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    # annual | interim
    period_type: Mapped[str] = mapped_column(String(20), nullable=False, default="annual")
    # Fiscal year the period belongs to (2024 for FY2024 and H1_2024).
    fiscal_year: Mapped[int | None] = mapped_column()
    end_date: Mapped[date | None] = mapped_column(Date)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    figures = relationship("FinancialFigure", back_populates="period", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (UniqueConstraint("company_id", "label"),)


class FinancialFigure(Base):
    __tablename__ = "financial_figures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False)
    # Key from services/financials/catalogue.LINE_ITEMS (e.g. "revenue", "cogs").
    line_item: Mapped[str] = mapped_column(String(80), nullable=False)
    # As reported in the source: currency, the stated unit and its multiplier.
    value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    unit: Mapped[str | None] = mapped_column(String(40))
    unit_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))
    # "12" for PDF page 12, "Sheet: P&L" for a spreadsheet; free text when entered by hand.
    source_page: Mapped[str | None] = mapped_column(String(80))
    # Set when the extraction flagged the figure or a subtotal check failed:
    # why it needs the analyst's review. Cleared when a clean source replaces it.
    review_note: Mapped[str | None] = mapped_column(Text)
    # extraction | manual
    origin: Mapped[str] = mapped_column(String(20), nullable=False, default="extraction")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    period = relationship("FinancialPeriod", back_populates="figures")

    __table_args__ = (UniqueConstraint("period_id", "line_item"),)


class FinancialFigureAmendment(Base):
    """Audit log: every change to a figure in a locked period, and every manual edit."""

    __tablename__ = "financial_figure_amendments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    period_label: Mapped[str] = mapped_column(String(50), nullable=False)
    line_item: Mapped[str] = mapped_column(String(80), nullable=False)
    old_value: Mapped[float | None] = mapped_column(Float)
    new_value: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    # edit | lock | unlock | resolve_discrepancy
    action: Mapped[str] = mapped_column(String(30), nullable=False, default="edit")
    was_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinancialDiscrepancy(Base):
    """A document reported a different value for a figure we already hold —
    either a locked period, or a comparative period in a document tagged to
    another period. Never applied automatically; the analyst accepts or
    dismisses it."""

    __tablename__ = "financial_discrepancies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    period_label: Mapped[str] = mapped_column(String(50), nullable=False)
    line_item: Mapped[str] = mapped_column(String(80), nullable=False)
    current_value: Mapped[float | None] = mapped_column(Float)
    current_currency: Mapped[str | None] = mapped_column(String(8))
    current_unit: Mapped[str | None] = mapped_column(String(40))
    document_value: Mapped[float | None] = mapped_column(Float)
    document_currency: Mapped[str | None] = mapped_column(String(8))
    document_unit: Mapped[str | None] = mapped_column(String(40))
    document_unit_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    source_page: Mapped[str | None] = mapped_column(String(80))
    # locked_period | comparative
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="locked_period")
    # open | accepted | dismissed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
