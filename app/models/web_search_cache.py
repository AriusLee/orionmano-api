from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WebSearchCache(Base):
    """Cache for Tavily web search results. Mirrors the translation cache pattern:
    keyed by query hash + freshness bucket so the cache naturally invalidates
    when content gets stale.

    Bucket = floor(unix_days / freshness_window_days). Same query in the same
    quarter returns the cached result; bucket rollover forces a fresh fetch.
    Default window is 90d, matching ARTICLE_REUSE_DAYS in config."""
    __tablename__ = "web_search_cache"

    query_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 hex
    freshness_bucket: Mapped[int] = mapped_column(Integer, primary_key=True)
    results: Mapped[list] = mapped_column(JSONB, nullable=False)
    query_preview: Mapped[str | None] = mapped_column(Text)  # for debugging
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_web_search_cache_lookup", "query_hash", "freshness_bucket"),
    )
