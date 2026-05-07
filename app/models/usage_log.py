import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageLog(Base):
    """Per-call LLM usage record. Written fire-and-forget by the AI client wrappers
    so latency is unaffected.

    The DeepSeek-specific cache fields (`cache_hit_tokens` / `cache_miss_tokens`)
    capture the savings from automatic prefix caching. Anthropic uses different
    field names (cache_read / cache_creation) — keep them in the same columns by
    convention so dashboards work across both vendors:
        cache_hit_tokens  ← deepseek prompt_cache_hit_tokens / anthropic cache_read_input_tokens
        cache_miss_tokens ← deepseek prompt_cache_miss_tokens / anthropic cache_creation_input_tokens
    """
    __tablename__ = "usage_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill: Mapped[str | None] = mapped_column(String(100))
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    use_reasoner: Mapped[bool] = mapped_column(Boolean, default=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_miss_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_usage_log_company_created", "company_id", "created_at"),
        Index("ix_usage_log_skill_created", "skill", "created_at"),
    )
