import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(50))
    # A doc can satisfy multiple checklist slots (e.g. org chart + cap table).
    # Populated by extract_document; `category` is kept as the primary slug
    # for legacy queries and filters.
    categories: Mapped[list[str] | None] = mapped_column(JSONB)
    extraction_status: Mapped[str] = mapped_column(String(50), default="pending")
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)
    extraction_error: Mapped[str | None] = mapped_column(Text)
    # The financial period this upload is FOR (e.g. "FY2025"), chosen at upload.
    # When set, extraction only updates that period; other periods the document
    # shows as comparatives are checked against what we hold, never written.
    # Null = no specific period (figures fill unlocked periods only). Eric 2026-10.
    target_period: Mapped[str | None] = mapped_column(String(50))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="documents")
