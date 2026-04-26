"""Insert a sample published article so the article-frontend has content to render.

Idempotent: if an article with the sample slug already exists, it is updated.
Run with:
    cd backend && .venv/bin/python scripts/seed_sample_article.py
"""

from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import select

from app.database import async_session
from app.models.published_article import PublishedArticle
from app.services.report.citations import _fact_hash, _slugify
from app.services.article.image import find_hero_image


SAMPLE_BODY = """*Indonesia's nickel sulfate output more than doubled in 2023 as Chinese refiners localised capacity to qualify for U.S. and EU clean-energy incentives.*

Indonesia produced an estimated 1.8 million tonnes of nickel in metallic content in 2023, roughly half of global mined supply, according to figures cited by the U.S. Geological Survey. The shift has compressed the LME nickel price below $18,000 per tonne for much of the year, squeezing higher-cost producers in the Philippines and New Caledonia and accelerating consolidation among non-Indonesian processors.

```chart
{
  "type": "bar",
  "title": "Indonesia mined nickel output, 2019-2023",
  "subtitle": "Metallic content; estimates rounded to nearest 0.1M tonnes.",
  "x_label": "Year",
  "y_label": "Output",
  "y_unit": "M tonnes",
  "series": [
    {
      "name": "Indonesia",
      "data": [
        { "x": "2019", "y": 0.8 },
        { "x": "2020", "y": 0.76 },
        { "x": "2021", "y": 1.0 },
        { "x": "2022", "y": 1.6 },
        { "x": "2023", "y": 1.8 }
      ]
    }
  ],
  "source": "USGS Mineral Commodity Summaries, 2020-2024"
}
```

## A capacity migration, not a demand surge

The growth has not been driven by a step-change in EV battery demand — global passenger-EV sales rose roughly 35% year-on-year, well below the 70%+ pace of 2021-22 — but by where new refining capacity has been built. Chinese players including Tsingshan, GEM, and Huayou have commissioned more than 30 high-pressure acid leach (HPAL) and rotary kiln-electric furnace (RKEF) lines in Sulawesi and Halmahera since 2020, taking advantage of low-cost local laterite ore and integrated coal power.

The export-ban regime imposed by Jakarta in 2020 forced the migration. Unrefined ore exports were prohibited, and refiners that wanted access to Indonesian feedstock had to invest in domestic processing. The policy has worked as a value-capture lever: Indonesia's nickel-product exports rose from $5 billion in 2019 to over $30 billion in 2023.

```chart
{
  "type": "pie",
  "title": "Global mined nickel supply, 2023",
  "subtitle": "Indicative shares by country of origin.",
  "y_unit": "%",
  "series": [
    {
      "name": "Country share",
      "data": [
        { "x": "Indonesia", "y": 50 },
        { "x": "Philippines", "y": 11 },
        { "x": "Russia", "y": 7 },
        { "x": "New Caledonia", "y": 6 },
        { "x": "Australia", "y": 5 },
        { "x": "Other", "y": 21 }
      ]
    }
  ],
  "source": "USGS Mineral Commodity Summaries, 2024"
}
```

## Margin compression and the IRA question

Two structural pressures now define the market. First, oversupply has driven sustained margin compression at the smelter gate, with several Class 1 refiners reporting cash costs that have moved closer to spot prices than at any time in the past decade. Second, the U.S. Inflation Reduction Act's foreign-entity-of-concern (FEOC) rules — which restrict Chinese-controlled inputs from qualifying for EV tax credits from 2025 — create a bifurcated demand picture.

Indonesian capacity built by Chinese majority-owned vehicles cannot, on current readings, supply battery materials destined for IRA-qualifying U.S. EV programmes. South Korean and Japanese refiners, including LG Chem and Sumitomo, have moved to take minority but operationally significant stakes in Indonesian projects to engineer compliance, but the legal and political durability of those structures is still untested.

## Outlook

Industry estimates suggest Indonesian nickel output could expand by a further 25–35% by 2026 if announced HPAL projects come online on schedule. Whether that capacity finds buyers depends less on the global demand curve and more on how restrictively the U.S. Treasury polices the FEOC threshold. Producers without a clear non-FEOC pathway face a discount to Class 1 reference prices that could persist into the second half of the decade.

## Sources

- U.S. Geological Survey, "Mineral Commodity Summaries: Nickel," USGS, January 2024. https://pubs.usgs.gov/periodicals/mcs2024/mcs2024-nickel.pdf
- International Energy Agency, "Global EV Outlook 2024," IEA, April 2024. https://www.iea.org/reports/global-ev-outlook-2024
- Reuters, "Indonesia's nickel exports surge as smelter buildout accelerates," Reuters, February 2024. https://www.reuters.com/markets/commodities/indonesia-nickel-exports-2024
- U.S. Department of the Treasury, "Section 30D Foreign Entity of Concern Final Rule," Treasury, May 2024. https://home.treasury.gov/policy-issues/tax-policy/section-30d
"""


async def main() -> None:
    topic = "indonesia-nickel"
    claim = (
        "Indonesia's share of global mined nickel reached approximately 50% in 2023 "
        "as Chinese-led refining capacity in Sulawesi and Halmahera came online."
    )
    fh = _fact_hash(topic, claim)
    slug = _slugify(topic)

    async with async_session() as db:
        existing = (
            await db.execute(select(PublishedArticle).where(PublishedArticle.fact_hash == fh))
        ).scalar_one_or_none()

        if existing:
            article = existing
            print(f"Updating existing article {article.id} ({article.slug})")
        else:
            article = PublishedArticle(
                slug=slug,
                fact_hash=fh,
                topic=topic,
                claim_text=claim,
                publication="OM Industries",
                article_date=date(2024, 3, 18),
                first_cited_by_report_id=None,
            )
            db.add(article)
            print(f"Creating new article ({slug})")

        article.title = (
            "Indonesia's Nickel Output Doubled in 2023 as Chinese Refining Capacity Migrated South"
        )
        article.deck = (
            "A 2020 export ban turned Indonesia into the world's dominant supplier — "
            "but IRA rules now threaten to bifurcate the market."
        )
        article.author = "Wei Chen"
        article.body_md = SAMPLE_BODY.lstrip()
        article.status = "published"
        article.topic_tags = [
            "nickel",
            "indonesia",
            "ev-supply-chain",
            "ira",
            "commodities",
        ]
        article.key_takeaways = [
            "Indonesia produced ~1.8M tonnes of nickel in 2023 — roughly half of global mined supply.",
            "Growth was driven by Chinese refining capacity migrating to qualify for local feedstock, not by EV demand.",
            "U.S. IRA foreign-entity-of-concern rules from 2025 may bifurcate Indonesian output by buyer eligibility.",
            "Industry estimates point to a further 25–35% capacity expansion by 2026 if announced HPAL projects come online.",
        ]
        article.reading_time_minutes = 5

        # Pull a hero image unless the article already has one. Doing this
        # lazily means re-running the seed doesn't burn an Unsplash request.
        if not article.hero_image_url:
            print("  fetching hero image from Unsplash …")
            hero = await find_hero_image("nickel mining indonesia")
            if hero:
                article.hero_image_url = hero["url"]
                article.hero_image_alt = hero["alt"]
                article.hero_image_credit = hero["credit"]
                article.hero_image_credit_url = hero["credit_url"]
                print(f"  hero: {hero['credit']} — {hero['url'][:80]}")
            else:
                print("  hero: (none — Unsplash returned no match or key not set)")

        await db.commit()
        await db.refresh(article)
        print(f"OK — slug=/{article.slug}  status={article.status}")


if __name__ == "__main__":
    asyncio.run(main())
