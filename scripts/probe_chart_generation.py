"""Drive the live article generator on a fresh stub and check whether the
output body contains at least one well-formed ```chart``` block.

This actually calls DeepSeek (Reasoner + Chat) and Tavily, so it costs a
small amount per run. Keep one-off.

Run with:
    cd backend && PYTHONPATH=. .venv/bin/python scripts/probe_chart_generation.py
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date

from sqlalchemy import select

from app.database import async_session
from app.models.published_article import PublishedArticle
from app.services.report.citations import _fact_hash, _slugify, _pick_author
from app.services.article.generator import generate_article_body


PROBE_TOPIC = "global-lithium-supply"
PROBE_CLAIM = (
    "Australia and Chile together accounted for roughly 75% of global mined "
    "lithium supply in 2023."
)


async def main() -> None:
    fh = _fact_hash(PROBE_TOPIC, PROBE_CLAIM)
    slug_base = f"probe-{_slugify(PROBE_TOPIC)}"

    async with async_session() as db:
        existing = (
            await db.execute(select(PublishedArticle).where(PublishedArticle.slug == slug_base))
        ).scalar_one_or_none()
        if existing:
            print(f"Reusing existing probe stub: {existing.id}")
            existing.status = "pending"
            existing.body_md = None
            existing.deck = None
            existing.key_takeaways = None
            existing.reading_time_minutes = None
            existing.generation_error = None
            article_id = existing.id
        else:
            article = PublishedArticle(
                slug=slug_base,
                title="Probe — global lithium supply concentration",
                author=_pick_author(fh),
                publication="Orionmano Industries",
                article_date=date.today(),
                fact_hash=fh,
                topic=PROBE_TOPIC,
                claim_text=PROBE_CLAIM,
                body_md=None,
                status="pending",
            )
            db.add(article)
            await db.flush()
            article_id = article.id
            print(f"Created probe stub: {article_id}")
        await db.commit()

    print("Running generator (this calls DeepSeek + Tavily)…")
    async with async_session() as db:
        await generate_article_body(db, article_id)

    async with async_session() as db:
        article = (
            await db.execute(select(PublishedArticle).where(PublishedArticle.id == article_id))
        ).scalar_one()

    print(f"\nstatus:               {article.status}")
    print(f"title:                {article.title}")
    print(f"deck:                 {article.deck}")
    print(f"key_takeaways count:  {len(article.key_takeaways or [])}")
    print(f"reading_time_minutes: {article.reading_time_minutes}")
    print(f"topic_tags:           {article.topic_tags}")
    body = article.body_md or ""
    print(f"body length:          {len(body)} chars")

    chart_blocks = re.findall(r"```chart\s*(.*?)```", body, re.DOTALL)
    print(f"chart blocks found:   {len(chart_blocks)}")

    valid = 0
    for i, raw in enumerate(chart_blocks, 1):
        try:
            spec = json.loads(raw.strip())
            t = spec.get("type")
            series = spec.get("series") or []
            n_pts = sum(len(s.get("data") or []) for s in series)
            print(f"  - chart {i}: type={t} series={len(series)} pts={n_pts} src={spec.get('source','?')[:40]!r}")
            if t in {"bar", "line", "pie"} and series and n_pts >= 2 and spec.get("source"):
                valid += 1
        except Exception as e:
            print(f"  - chart {i}: INVALID JSON ({e})")

    print(f"\nvalid chart blocks:   {valid} / {len(chart_blocks)}")

    if article.generation_error:
        print(f"\ngeneration_error:    {article.generation_error}")


if __name__ == "__main__":
    asyncio.run(main())
