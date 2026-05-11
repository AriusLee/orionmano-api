"""Compiled-knowledge pages per client/company.

Every page is the LLM's distilled view of a single canonical entity (profile,
historical-fs, cap-table, etc.) for one company. Pages are rebuilt from the
union of all that company's extracted documents on every doc-upload completion;
the prior version is preserved in ClientKbPageHistory for audit.

This is the Karpathy "compile knowledge once" layer applied to client
engagements — instead of every report re-deriving facts from raw extracted_data
JSON each call, skills read pre-synthesized pages."""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClientKbPage(Base):
    __tablename__ = "client_kb_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)  # profile | historical-fs | cap-table | ...
    content: Mapped[str] = mapped_column(Text, nullable=False)  # markdown body
    # Provenance — which extracted documents fed this version
    source_doc_ids: Mapped[list | None] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(64), nullable=False)  # llm model used
    version: Mapped[int] = mapped_column(Integer, default=1)  # bumps on each rebuild
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_client_kb_pages_company_slug"),
        Index("ix_client_kb_pages_company", "company_id"),
    )


class ClientKbPageHistory(Base):
    """Append-only history. On every overwrite of a ClientKbPage row, the prior
    version snapshots into here. Audit trail for IPO defensibility — when a
    deliverable claims "USD 22.7M revenue", the version chain proves where the
    number came from and when it was last revised."""
    __tablename__ = "client_kb_page_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_kb_pages.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_doc_ids: Mapped[list | None] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_client_kb_page_history_page", "page_id"),
        Index("ix_client_kb_page_history_company_slug", "company_id", "slug"),
    )
