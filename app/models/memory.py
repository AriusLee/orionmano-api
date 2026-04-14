"""Memory model for the learning/memory system."""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, FLOAT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Scope: null company_id = global memory
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )

    # Which skill and sub-scope this applies to
    skill_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scope: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )  # e.g. "gap_analysis", "valuation_report.sensitivity_analysis"

    # The distilled rule (compressed, not raw feedback)
    rule: Mapped[str] = mapped_column(Text, nullable=False)

    # Embedding vector for semantic retrieval (stored as float array)
    embedding: Mapped[list | None] = mapped_column(ARRAY(FLOAT), nullable=True)

    # How this memory was created
    source: Mapped[str] = mapped_column(
        String(50), default="explicit_feedback"
    )  # explicit_feedback, regeneration, edit_diff, developer

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(30), default="active"
    )  # active, archived, superseded_by_code

    # Metadata for the developer export / cleanup cycle
    superseded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_count: Mapped[int] = mapped_column(default=0)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_memories_company_skill", "company_id", "skill_name"),
        Index("ix_memories_status", "status"),
    )
