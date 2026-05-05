from datetime import datetime

from sqlalchemy import String, Text, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TranslationCache(Base):
    """Segment-level translation memory keyed by (segment_hash, target_lang, glossary_ver).

    Glossary changes bump glossary_ver (computed from yaml content hash); old rows
    naturally miss and get re-translated under the new key. No TTL — finance reports
    stay relevant for years.
    """
    __tablename__ = "translation_cache"

    segment_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_lang: Mapped[str] = mapped_column(String(10), primary_key=True)
    glossary_ver: Mapped[str] = mapped_column(String(16), primary_key=True)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_translation_cache_lookup", "segment_hash", "target_lang", "glossary_ver"),
    )
