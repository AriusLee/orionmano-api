from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date


class PublishedArticleListItem(BaseModel):
    id: UUID
    slug: str
    title: str
    author: str
    publication: str
    article_date: date
    topic: str
    status: str
    has_body: bool
    first_cited_by_report_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublishedArticleDetail(BaseModel):
    id: UUID
    slug: str
    title: str
    author: str
    publication: str
    article_date: date
    topic: str
    topic_tags: list | None = None
    claim_text: str
    body_md: str | None = None
    status: str
    generation_error: str | None = None
    url: str
    first_cited_by_report_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None


class PublishedArticlePublicDetail(BaseModel):
    """Strictly public payload. Never includes underlying_source_refs or internal metadata."""
    slug: str
    title: str
    author: str
    publication: str
    article_date: date
    body_md: str | None = None
    status: str
    url: str
