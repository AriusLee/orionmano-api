"""Exercise resolve_citation across the three reuse tiers.

Run with:
    cd backend && PYTHONPATH=. .venv/bin/python scripts/verify_dedup.py

Expected output:
    Tier 1 (exact fact, fresh)        -> reuses seeded article
    Tier 2 (same topic, fresh)        -> reuses seeded article
    Tier 3 (same topic, stale ancestor) -> creates a NEW article
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.database import async_session
from app.models.published_article import PublishedArticle
from app.services.report.citations import resolve_citation
from app.config import settings


SEEDED_TOPIC = "indonesia-nickel"
SEEDED_CLAIM = (
    "Indonesia's share of global mined nickel reached approximately 50% in 2023 "
    "as Chinese-led refining capacity in Sulawesi and Halmahera came online."
)


async def _get_seeded(db) -> PublishedArticle:
    return (
        await db.execute(
            select(PublishedArticle).where(PublishedArticle.slug == SEEDED_TOPIC)
        )
    ).scalar_one()


async def main() -> None:
    print(f"Reuse window: {settings.ARTICLE_REUSE_DAYS} days\n")

    # --- Tier 1: identical topic + claim, fresh ---
    async with async_session() as db:
        seeded = await _get_seeded(db)
        original_id = seeded.id
        original_created_at = seeded.created_at

        hit = await resolve_citation(db, SEEDED_TOPIC, SEEDED_CLAIM)
        await db.flush()
        assert hit.id == original_id, f"Tier 1 miss: got {hit.id}, expected {original_id}"
        print(f"[OK] Tier 1 — exact fact reused (slug={hit.slug})")
        await db.rollback()

    # --- Tier 2: same topic, different claim wording, fresh ---
    different_claim = (
        "Indonesia is now the world's largest nickel exporter, accounting for over "
        "half of mined supply in 2023."
    )
    async with async_session() as db:
        hit = await resolve_citation(db, SEEDED_TOPIC, different_claim)
        await db.flush()
        assert hit.id == original_id, (
            f"Tier 2 miss: got new article {hit.id}, expected reuse of {original_id}"
        )
        print(f"[OK] Tier 2 — different claim, same topic reused (slug={hit.slug})")
        await db.rollback()

    # --- Tier 3: backdate the seeded article past the freshness window ---
    stale_dt = datetime.now(timezone.utc) - timedelta(days=settings.ARTICLE_REUSE_DAYS + 5)
    async with async_session() as db:
        await db.execute(
            update(PublishedArticle)
            .where(PublishedArticle.id == original_id)
            .values(created_at=stale_dt)
        )
        await db.commit()

    try:
        async with async_session() as db:
            hit = await resolve_citation(db, SEEDED_TOPIC, different_claim)
            await db.flush()
            assert hit.id != original_id, (
                f"Tier 3 miss: reused stale article {hit.id} instead of creating new"
            )
            print(
                f"[OK] Tier 3 — stale ancestor superseded; new article created "
                f"(slug={hit.slug}, status={hit.status})"
            )
            await db.rollback()
    finally:
        # Restore original created_at so the seeded article stays usable.
        async with async_session() as db:
            await db.execute(
                update(PublishedArticle)
                .where(PublishedArticle.id == original_id)
                .values(created_at=original_created_at)
            )
            await db.commit()
        print("\nSeed timestamps restored.")


if __name__ == "__main__":
    asyncio.run(main())
