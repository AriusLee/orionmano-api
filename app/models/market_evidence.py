"""Market evidence for one valuation assumption (Eric 2026-10, item 4).

The "Market Data Supported" report checks each key assumption of a valuation
version against live market data found by web search, and records what was
found: whether it supports the value used, the finding in a sentence or two,
and every source with its URL and date. The report variant renders these rows;
the analyst can also read them on the valuation page.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarketEvidence(Base):
    __tablename__ = "market_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("valuation_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    # Key from services/market/evidence.ASSUMPTIONS, e.g. "terminal_growth_rate".
    assumption_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    value_used: Mapped[float | None] = mapped_column(Float)
    value_display: Mapped[str | None] = mapped_column(String(100))
    # supported | partially_supported | not_supported | insufficient_data | pending | failed
    assessment: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # Market range or point the evidence points to, in words ("2.0%–2.5%").
    market_range: Mapped[str | None] = mapped_column(String(200))
    finding: Mapped[str | None] = mapped_column(Text)
    # [{url, title, publisher, published_date, quote}]
    sources: Mapped[list | None] = mapped_column(JSONB)
    searched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
