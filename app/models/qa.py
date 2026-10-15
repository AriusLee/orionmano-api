"""Counterparty Q&A on a valuation (Eric 2026-10, item 3).

A batch is one set of questions from the counterparty (pasted or uploaded).
Each question gets a simplified and a detailed answer drafted against the
active valuation version. When the right answer is "the model should change",
the draft also proposes concrete parameter changes; each shows its impact on
EV and equity before anything is applied. Approving a question's changes
produces a new valuation version and report linked back to that question.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QaBatch(Base):
    __tablename__ = "qa_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(500))
    # The valuation version the questions were asked against.
    base_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("valuation_versions.id", ondelete="SET NULL"))
    # draft | answering | answered | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    progress_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items = relationship("QaItem", back_populates="batch", cascade="all, delete-orphan", lazy="selectin", order_by="QaItem.item_no")


class QaItem(Base):
    __tablename__ = "qa_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("qa_batches.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    item_no: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(80))
    simplified_answer: Mapped[str | None] = mapped_column(Text)
    detailed_answer: Mapped[str | None] = mapped_column(Text)
    # pending | answered | change_proposed | applying | applied | rejected | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    # Version + report created when this item's changes were applied.
    resulting_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("valuation_versions.id", ondelete="SET NULL"))
    resulting_report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    batch = relationship("QaBatch", back_populates="items")
    changes = relationship("QaModelChange", back_populates="item", cascade="all, delete-orphan", lazy="selectin", order_by="QaModelChange.created_at")


class QaModelChange(Base):
    __tablename__ = "qa_model_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("qa_items.id", ondelete="CASCADE"), nullable=False)
    # Key from PINNABLE_PARAMS (produce_valuation_inputs) and its dotted inputs path.
    param_key: Mapped[str] = mapped_column(String(80), nullable=False)
    path: Mapped[str] = mapped_column(String(200), nullable=False)
    old_value: Mapped[float | None] = mapped_column(Float)
    new_value: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    # {ev_before, ev_after, equity_before, equity_after, ev_change_pct, equity_change_pct, currency, unit}
    impact: Mapped[dict | None] = mapped_column(JSONB)
    # proposed | approved | rejected
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item = relationship("QaItem", back_populates="changes")
