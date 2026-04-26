"""Regenerate every published_article whose previous run hit an outline
JSON parse failure (and therefore landed without a chart).

Run with:
    cd backend && PYTHONPATH=. .venv/bin/python scripts/regen_outline_failures.py

Each run costs one Reasoner outline + one Chat body + one Unsplash search
per article. Sequential so we don't rate-limit the LLM provider.
"""

from __future__ import annotations

import asyncio
import re
from uuid import UUID

from sqlalchemy import select

from app.database import async_session
from app.models.published_article import PublishedArticle
from app.services.article.generator import generate_article_body


def _has_chart(body: str | None) -> bool:
    if not body:
        return False
    return bool(re.search(r"```chart\b", body))


async def main() -> None:
    async with async_session() as db:
        rows = (
            await db.execute(
                select(PublishedArticle.id, PublishedArticle.slug)
                .where(PublishedArticle.generation_error.like("Outline pass failed%"))
                .order_by(PublishedArticle.slug)
            )
        ).all()

    if not rows:
        print("No articles with outline-failure markers — nothing to do.")
        return

    print(f"Regenerating {len(rows)} article(s)…")
    results: list[tuple[str, bool, bool, str | None]] = []

    for aid, slug in rows:
        print(f"  → {slug}")
        async with async_session() as db:
            a = (
                await db.execute(select(PublishedArticle).where(PublishedArticle.id == aid))
            ).scalar_one()
            # Reset to pending; clear the prior warning + body so the
            # generator runs end-to-end.
            a.status = "pending"
            a.body_md = None
            a.deck = None
            a.key_takeaways = None
            a.reading_time_minutes = None
            a.generation_error = None
            await db.commit()

        try:
            async with async_session() as db:
                await generate_article_body(db, UUID(str(aid)))
        except Exception as e:
            results.append((slug, False, False, f"generator raised: {e}"))
            continue

        async with async_session() as db:
            a = (
                await db.execute(select(PublishedArticle).where(PublishedArticle.id == aid))
            ).scalar_one()

        results.append((slug, _has_chart(a.body_md), a.status == "published", a.generation_error))

    print("\n=== regen results ===")
    ok_chart = 0
    for slug, has_chart, published, err in results:
        flag = "✓" if (has_chart and published and not err) else "✗"
        chart_flag = "chart" if has_chart else "NO chart"
        err_flag = f" err={err[:80]}" if err else ""
        print(f"  {flag} {slug}  ({chart_flag}, status={'published' if published else 'NOT published'}){err_flag}")
        if has_chart:
            ok_chart += 1
    print(f"\n{ok_chart}/{len(results)} articles now carry at least one chart.")


if __name__ == "__main__":
    asyncio.run(main())
