"""ValuationVersion — one row per valuation workpaper run.

Eric 2026-10 request. Before this table a run lived only as an xlsx plus a
`.summary.json` on disk, and "latest" meant "newest active file by mtime", so
there was no version number, no link from a run to what caused it, and no way
to tie a Q&A answer or a Market Data Supported report to the model it changed.

Every run (Generate, re-upload, Q&A change, restore) now writes a version with
the full inputs + computed summary. Exactly one version per company is
`active`; the rest are `superseded`. The xlsx and summary.json are still
written exactly as before, so downloads and the legacy readers keep working.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ValuationVersion(Base):
    __tablename__ = "valuation_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    # 1, 2, 3 … per company, in creation order.
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # The version this one was derived from (the active one when it was made).
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("valuation_versions.id"))
    # active | superseded
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # generate | regenerate_inputs | regenerate_xlsx | qa_change | restore | legacy_import
    trigger: Mapped[str] = mapped_column(String(30), nullable=False, default="generate")
    # Short human description, e.g. "Q&A #4 — WACC specific risk premium 3% → 2%".
    note: Mapped[str | None] = mapped_column(Text)
    # Set when trigger == qa_change: the counterparty question that caused it.
    qa_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict | None] = mapped_column(JSONB)
    warnings: Mapped[list | None] = mapped_column(JSONB)
    errors: Mapped[list | None] = mapped_column(JSONB)
    xlsx_filename: Mapped[str | None] = mapped_column(String(500))
    xlsx_url: Mapped[str | None] = mapped_column(String(1000))
    # The written valuation report produced with this run, if any.
    report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"))

    # Headline numbers, denormalised for the version list (workpaper units).
    ev: Mapped[float | None] = mapped_column(Float)
    equity_value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    unit: Mapped[str | None] = mapped_column(String(20))

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("company_id", "version_no"),)
