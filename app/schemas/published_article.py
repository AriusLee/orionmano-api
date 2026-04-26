from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date


class HeroImageFields(BaseModel):
    hero_image_url: str | None = None
    hero_image_alt: str | None = None
    hero_image_credit: str | None = None
    hero_image_credit_url: str | None = None


class IndustryItem(BaseModel):
    slug: str
    label: str
    count: int


class PublishedArticleListItem(HeroImageFields):
    id: UUID
    slug: str
    title: str
    deck: str | None = None
    author: str
    publication: str
    article_date: date
    topic: str
    topic_tags: list | None = None
    industry: str | None = None
    reading_time_minutes: int | None = None
    status: str
    has_body: bool
    first_cited_by_report_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublishedArticleDetail(HeroImageFields):
    id: UUID
    slug: str
    title: str
    deck: str | None = None
    author: str
    publication: str
    article_date: date
    topic: str
    topic_tags: list | None = None
    industry: str | None = None
    key_takeaways: list | None = None
    reading_time_minutes: int | None = None
    claim_text: str
    body_md: str | None = None
    status: str
    generation_error: str | None = None
    url: str
    first_cited_by_report_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None


class PublishedArticlePublicListItem(HeroImageFields):
    """Public list payload — homepage feeds and topic pages."""
    slug: str
    title: str
    deck: str | None = None
    author: str
    publication: str
    article_date: date
    topic: str
    topic_tags: list | None = None
    industry: str | None = None
    reading_time_minutes: int | None = None
    url: str


class PublishedArticlePublicDetail(HeroImageFields):
    """Strictly public payload. Never includes underlying_source_refs or internal metadata."""
    slug: str
    title: str
    deck: str | None = None
    author: str
    publication: str
    article_date: date
    topic: str
    topic_tags: list | None = None
    industry: str | None = None
    key_takeaways: list | None = None
    reading_time_minutes: int | None = None
    body_md: str | None = None
    status: str
    url: str
