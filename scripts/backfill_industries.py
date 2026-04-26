"""Classify every published_article into an industry using the keyword
taxonomy in app.services.article.industries.

Idempotent — only updates rows whose `industry` is NULL or differs from the
classifier's current verdict, so re-runs after rule tweaks are safe.

Run with:
    cd backend && PYTHONPATH=. .venv/bin/python scripts/backfill_industries.py
"""

from __future__ import annotations

import asyncio
from collections import Counter

from sqlalchemy import select

from app.database import async_session
from app.models.published_article import PublishedArticle
from app.services.article.industries import classify_industry, INDUSTRY_LABELS


async def main() -> None:
    async with async_session() as db:
        rows = (
            await db.execute(
                select(
                    PublishedArticle.id,
                    PublishedArticle.title,
                    PublishedArticle.topic,
                    PublishedArticle.topic_tags,
                    PublishedArticle.industry,
                )
            )
        ).all()

    if not rows:
        print("No articles in DB.")
        return

    updates: list[tuple] = []
    counts: Counter[str] = Counter()
    moved: int = 0

    for r in rows:
        new_industry = classify_industry(title=r.title, topic=r.topic, topic_tags=r.topic_tags)
        counts[new_industry] += 1
        if r.industry != new_industry:
            updates.append((r.id, new_industry))
            moved += 1

    if updates:
        async with async_session() as db:
            for aid, industry in updates:
                await db.execute(
                    PublishedArticle.__table__.update()
                    .where(PublishedArticle.id == aid)
                    .values(industry=industry)
                )
            await db.commit()

    print(f"Examined {len(rows)} articles. Updated industry on {moved}.\n")
    print("Distribution:")
    for slug in sorted(counts, key=lambda s: -counts[s]):
        label = INDUSTRY_LABELS.get(slug, slug)
        print(f"  {counts[slug]:>4}  {slug:<14} {label}")


if __name__ == "__main__":
    asyncio.run(main())
