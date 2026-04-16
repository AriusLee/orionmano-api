"""Article body generator — runs post-report-generation.

A PublishedArticle stub is created when the report agent emits a <cite/> tag.
This module fills the stub with body content grounded in public web sources.

The article is authored "by Orionmano Research" (rotated byline). It must:
  - Use ONLY information from public web sources (no paid/confidential data).
  - Substantiate the original claim using public evidence.
  - Read like an industry-analysis piece, not a summary of search results.
  - Include its own short source list at the bottom (public citations).
"""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.published_article import PublishedArticle
from app.services.ai.client import generate_text
from app.services.ai.web_search import web_search, format_search_results


ARTICLE_SYSTEM_PROMPT = """You are a senior research analyst at Orionmano Industries, a public research imprint.
You write grounded, fact-dense industry analysis articles for a professional audience.

## STRICT RULES
1. Use ONLY information that is verifiable from the public web sources provided. Do not invent numbers.
2. If the public sources disagree with or do not support a specific data point, qualify it ("industry estimates suggest…", "sources cite a range of…") or omit it.
3. Write in third-person analytical voice. No first-person, no marketing language, no superlatives without data.
4. Structure: opening context (1 paragraph) → core analysis with data (2–4 paragraphs) → outlook or implications (1 paragraph).
5. End with a "Sources" section listing the public sources actually referenced, in the format:
   - Author (or organisation), "Title," Publication, Date. URL

## LENGTH
700 to 1,100 words. Markdown formatting. No preamble, no "As an AI" disclaimers.
"""


async def _write_article_body(
    title: str,
    topic: str,
    claim: str,
    author: str,
    article_date: date,
) -> tuple[str, str]:
    """Returns (body_md, refined_title). May raise on LLM/search errors."""
    query = f"{topic.replace('-', ' ')} {claim[:120]}".strip()
    try:
        search_results = await web_search(query, max_results=6)
    except Exception:
        search_results = []

    sources_block = format_search_results(search_results) or "(No external web results available.)"

    user_prompt = f"""Draft a public-facing industry analysis article.

**Author (byline):** {author}
**Publication:** Orionmano Industries
**Article as-of date:** {article_date.strftime('%B %Y')}
**Working title:** {title}
**Core claim this article should substantiate (using ONLY public evidence below):**
{claim}

## Public Web Research (the ONLY permitted evidence)
{sources_block}

---

Output requirements:
- First line: a refined headline/title prefixed with "# " (markdown H1). The title must be factual, non-clickbait, and specific.
- Body: grounded analysis substantiating the core claim. Use markdown. Include specific figures with their source attributions where available.
- Final section: "## Sources" — a bulleted list of the public sources actually cited in the article, in the format:
  - Author or Organisation, "Title," Publication, Date. URL

Do NOT mention Orionmano, Orionmano Assurance, or any client by name unless they appear independently in the public sources."""

    body = await generate_text(
        system_prompt=ARTICLE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=2000,
    )

    refined_title = title
    lines = body.lstrip().split("\n", 1)
    if lines and lines[0].startswith("# "):
        refined_title = lines[0][2:].strip()[:200] or title
        body = lines[1].lstrip() if len(lines) > 1 else body

    return body, refined_title


async def generate_article_body(db: AsyncSession, article_id: UUID) -> None:
    """Fill in body_md for a single pending PublishedArticle."""
    result = await db.execute(
        select(PublishedArticle).where(PublishedArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article or article.status not in ("pending", "failed"):
        return

    article.status = "generating"
    await db.commit()

    try:
        body, refined_title = await _write_article_body(
            title=article.title,
            topic=article.topic,
            claim=article.claim_text,
            author=article.author,
            article_date=article.article_date,
        )
        article.body_md = body
        article.title = refined_title
        article.status = "draft"
        article.generation_error = None
    except Exception as e:
        article.status = "failed"
        article.generation_error = str(e)[:2000]

    await db.commit()


async def generate_pending_articles_for_report(report_id: UUID) -> None:
    """Fill body_md for every pending article first cited by this report.

    Designed to run detached from the request/report session. Creates its own
    DB session so it survives after the parent transaction commits.
    """
    async with async_session() as db:
        result = await db.execute(
            select(PublishedArticle.id).where(
                PublishedArticle.first_cited_by_report_id == report_id,
                PublishedArticle.status == "pending",
            )
        )
        ids = [row[0] for row in result.all()]

    # Generate sequentially to avoid rate-limiting the LLM provider.
    for aid in ids:
        async with async_session() as db:
            try:
                await generate_article_body(db, aid)
            except Exception:
                # Individual article failure must not halt the batch.
                continue
            # Small spacer between calls.
            await asyncio.sleep(0.5)
