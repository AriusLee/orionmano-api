"""Published article endpoints.

Internal (auth-required):
  GET    /articles                — list, filter by status/topic
  GET    /articles/{id}           — full detail (auth)
  POST   /articles/{id}/publish   — flip status draft -> published
  POST   /articles/{id}/regenerate — re-run article body generation

Public (for the future industries.omassurance.com site):
  GET    /articles/public/{slug}  — published body only
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models.user import User
from app.models.published_article import PublishedArticle
from app.schemas.published_article import (
    PublishedArticleListItem,
    PublishedArticleDetail,
    PublishedArticlePublicListItem,
    PublishedArticlePublicDetail,
    IndustryItem,
)
from app.api.deps import get_current_user
from app.services.report.citations import article_url
from app.services.article.industries import INDUSTRY_LABELS, INDUSTRY_ORDER


router = APIRouter(prefix="/articles", tags=["articles"])


def _hero_fields(a: PublishedArticle) -> dict:
    return {
        "hero_image_url": a.hero_image_url,
        "hero_image_alt": a.hero_image_alt,
        "hero_image_credit": a.hero_image_credit,
        "hero_image_credit_url": a.hero_image_credit_url,
    }


def _to_detail(a: PublishedArticle) -> PublishedArticleDetail:
    return PublishedArticleDetail(
        id=a.id,
        slug=a.slug,
        title=a.title,
        deck=a.deck,
        author=a.author,
        publication=a.publication,
        article_date=a.article_date,
        topic=a.topic,
        topic_tags=a.topic_tags,
        industry=a.industry,
        key_takeaways=a.key_takeaways,
        reading_time_minutes=a.reading_time_minutes,
        claim_text=a.claim_text,
        body_md=a.body_md,
        status=a.status,
        generation_error=a.generation_error,
        url=article_url(a),
        first_cited_by_report_id=a.first_cited_by_report_id,
        created_at=a.created_at,
        updated_at=a.updated_at,
        **_hero_fields(a),
    )


def _to_list_item(a: PublishedArticle) -> PublishedArticleListItem:
    return PublishedArticleListItem(
        id=a.id,
        slug=a.slug,
        title=a.title,
        deck=a.deck,
        author=a.author,
        publication=a.publication,
        article_date=a.article_date,
        topic=a.topic,
        topic_tags=a.topic_tags,
        industry=a.industry,
        reading_time_minutes=a.reading_time_minutes,
        status=a.status,
        has_body=bool(a.body_md),
        first_cited_by_report_id=a.first_cited_by_report_id,
        created_at=a.created_at,
        **_hero_fields(a),
    )


def _to_public_list_item(a: PublishedArticle) -> PublishedArticlePublicListItem:
    return PublishedArticlePublicListItem(
        slug=a.slug,
        title=a.title,
        deck=a.deck,
        author=a.author,
        publication=a.publication,
        article_date=a.article_date,
        topic=a.topic,
        topic_tags=a.topic_tags,
        industry=a.industry,
        reading_time_minutes=a.reading_time_minutes,
        url=article_url(a),
        **_hero_fields(a),
    )


# -- Public endpoints for the article site --
# Declared FIRST so they match before any auth-protected /{article_id} route.
# Without this ordering, FastAPI would try `/{article_id}` for `/public`,
# run the auth dependency before path validation, and return 401.


@router.get("/public", response_model=list[PublishedArticlePublicListItem])
async def list_public_articles(
    topic: str | None = Query(default=None, description="Filter by topic slug"),
    industry: str | None = Query(default=None, description="Filter by industry slug"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Homepage feed for the article site. Newest published first."""
    stmt = (
        select(PublishedArticle)
        .where(PublishedArticle.status == "published")
        .order_by(PublishedArticle.article_date.desc(), PublishedArticle.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if topic:
        stmt = stmt.where(PublishedArticle.topic == topic.lower())
    if industry:
        stmt = stmt.where(PublishedArticle.industry == industry.lower())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_to_public_list_item(a) for a in rows]


@router.get("/public/topics", response_model=list[str])
async def list_public_topics(db: AsyncSession = Depends(get_db)):
    """Distinct topics that have at least one published article."""
    from sqlalchemy import distinct
    stmt = (
        select(distinct(PublishedArticle.topic))
        .where(PublishedArticle.status == "published")
        .order_by(PublishedArticle.topic)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


@router.get("/public/industries", response_model=list[IndustryItem])
async def list_public_industries(db: AsyncSession = Depends(get_db)):
    """Industries that have at least one published article, ordered by the
    canonical taxonomy order with article counts."""
    from sqlalchemy import func
    stmt = (
        select(PublishedArticle.industry, func.count().label("n"))
        .where(PublishedArticle.status == "published")
        .where(PublishedArticle.industry.is_not(None))
        .group_by(PublishedArticle.industry)
    )
    result = await db.execute(stmt)
    counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

    items: list[IndustryItem] = []
    for slug in INDUSTRY_ORDER:
        if slug in counts:
            items.append(
                IndustryItem(
                    slug=slug, label=INDUSTRY_LABELS.get(slug, slug), count=counts[slug]
                )
            )
    return items


@router.get("/public/{slug}", response_model=PublishedArticlePublicDetail)
async def get_public_article(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PublishedArticle).where(PublishedArticle.slug == slug)
    )
    article = result.scalar_one_or_none()
    if not article or article.status != "published":
        raise HTTPException(status_code=404, detail="Article not found")
    return PublishedArticlePublicDetail(
        slug=article.slug,
        title=article.title,
        deck=article.deck,
        author=article.author,
        publication=article.publication,
        article_date=article.article_date,
        topic=article.topic,
        topic_tags=article.topic_tags,
        industry=article.industry,
        key_takeaways=article.key_takeaways,
        reading_time_minutes=article.reading_time_minutes,
        body_md=article.body_md,
        status=article.status,
        url=article_url(article),
        **_hero_fields(article),
    )


# -- Internal (auth-required) --


@router.get("", response_model=list[PublishedArticleListItem])
async def list_articles(
    status: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(PublishedArticle).order_by(PublishedArticle.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(PublishedArticle.status == status)
    if topic:
        stmt = stmt.where(PublishedArticle.topic == topic.lower())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_to_list_item(a) for a in rows]


@router.get("/{article_id}", response_model=PublishedArticleDetail)
async def get_article(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PublishedArticle).where(PublishedArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return _to_detail(article)


@router.post("/{article_id}/publish", response_model=PublishedArticleDetail)
async def publish_article(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PublishedArticle).where(PublishedArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if not article.body_md:
        raise HTTPException(status_code=400, detail="Article has no body yet; generate before publishing")
    article.status = "published"
    await db.commit()
    await db.refresh(article)
    return _to_detail(article)


@router.post("/{article_id}/regenerate", response_model=PublishedArticleDetail)
async def regenerate_article(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PublishedArticle).where(PublishedArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article.status = "pending"
    article.generation_error = None
    await db.commit()
    article_id_copy = article.id

    async def _run():
        from app.services.article.generator import generate_article_body
        async with async_session() as session:
            await generate_article_body(session, article_id_copy)

    asyncio.create_task(_run())
    await db.refresh(article)
    return _to_detail(article)


