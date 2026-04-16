import uuid
from datetime import datetime, date

from sqlalchemy import String, Text, Date, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PublishedArticle(Base):
    """Public-facing article authored by Orionmano Research.

    Articles back every citation in industry expert reports. Confidential/paid
    data never appears in citations directly — instead an article is generated
    (or reused) that synthesises public information on the same topic, and the
    report footnote points to that article's URL on industries.omassurance.com.
    """

    __tablename__ = "published_articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Public identity
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    publication: Mapped[str] = mapped_column(String(200), default="Orionmano Industries")
    # Content-as-of date shown on the article page and in citations.
    # Inferred from the claim (e.g. a 2023 data point -> article_date ~ Q1 2024).
    article_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Reuse/dedup key — hash(topic + normalized claim). Unique so identical
    # facts resolve to the same article across all reports.
    fact_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    topic_tags: Mapped[list | None] = mapped_column(JSONB)

    # Article body is filled in post-gen by the article generator skill.
    body_md: Mapped[str | None] = mapped_column(Text)
    # pending | generating | draft | published | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    generation_error: Mapped[str | None] = mapped_column(Text)

    # Private. Internal references used to ground the article (document IDs,
    # paid-source identifiers). Never rendered publicly.
    underlying_source_refs: Mapped[dict | None] = mapped_column(JSONB)

    # Audit
    first_cited_by_report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_published_articles_topic", "topic"),
        Index("ix_published_articles_status", "status"),
    )
