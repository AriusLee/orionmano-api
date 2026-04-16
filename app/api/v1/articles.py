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
    PublishedArticlePublicDetail,
)
from app.api.deps import get_current_user
from app.services.report.citations import article_url


router = APIRouter(prefix="/articles", tags=["articles"])


def _to_detail(a: PublishedArticle) -> PublishedArticleDetail:
    return PublishedArticleDetail(
        id=a.id,
        slug=a.slug,
        title=a.title,
        author=a.author,
        publication=a.publication,
        article_date=a.article_date,
        topic=a.topic,
        topic_tags=a.topic_tags,
        claim_text=a.claim_text,
        body_md=a.body_md,
        status=a.status,
        generation_error=a.generation_error,
        url=article_url(a),
        first_cited_by_report_id=a.first_cited_by_report_id,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _to_list_item(a: PublishedArticle) -> PublishedArticleListItem:
    return PublishedArticleListItem(
        id=a.id,
        slug=a.slug,
        title=a.title,
        author=a.author,
        publication=a.publication,
        article_date=a.article_date,
        topic=a.topic,
        status=a.status,
        has_body=bool(a.body_md),
        first_cited_by_report_id=a.first_cited_by_report_id,
        created_at=a.created_at,
    )


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


# -- Public endpoint for the article site --
# No auth, returns only published articles.

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
        author=article.author,
        publication=article.publication,
        article_date=article.article_date,
        body_md=article.body_md,
        status=article.status,
        url=article_url(article),
    )
