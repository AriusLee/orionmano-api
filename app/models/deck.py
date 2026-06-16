"""Deck + DeckVersion models.

A Deck is a persisted SlideSpec for a company. Each amend prompt produces a new
DeckVersion row so the user can roll back when the AI butchers a slide. The
current spec always lives on the Deck row (`spec`), and DeckVersion holds the
history. Render is pure: same spec + same theme → same PDF, so we don't store
rendered PDFs.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

    # User-facing title — shown in the deck list, used as PDF filename.
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # The theme this deck currently renders under. Swapping themes mutates this
    # field only; the spec is theme-agnostic.
    theme_id: Mapped[str] = mapped_column(String(80), nullable=False, default="orionmano_navy")

    # Preset that seeded this deck, if any: 'sales_deck', 'kickoff_deck', 'teaser',
    # 'company_deck', or None for fully free-prompt decks. Kept for analytics —
    # the generation path is identical regardless.
    preset: Mapped[str | None] = mapped_column(String(50))

    # The original user prompt that produced the initial spec. Persisted for
    # audit + future re-runs.
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # The current SlideSpec as JSON. Shape defined by app.services.deck.schema.SlideSpec.
    spec: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Monotonic counter; current_version on Deck == latest DeckVersion.version_no.
    current_version: Mapped[int] = mapped_column(Integer, default=1)

    status: Mapped[str] = mapped_column(String(50), default="ready")  # ready | generating | failed
    error_message: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    versions = relationship(
        "DeckVersion",
        back_populates="deck",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DeckVersion.version_no",
    )


class DeckVersion(Base):
    """An immutable snapshot of a Deck's spec at a point in time. Created on
    initial generation and on every amend. Restoring a version copies its spec
    back onto the parent Deck and bumps current_version."""

    __tablename__ = "deck_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deck_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("decks.id", ondelete="CASCADE"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)

    spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    theme_id: Mapped[str] = mapped_column(String(80), nullable=False)

    # What action produced this version: 'generate' (initial), 'amend' (prompt-driven edit),
    # 'theme_swap' (theme change only), 'restore' (rolled back from another version).
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text)  # null for theme_swap/restore

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    deck = relationship("Deck", back_populates="versions")

    __table_args__ = (UniqueConstraint("deck_id", "version_no"),)
