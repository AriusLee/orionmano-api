"""Article body generator — runs post-report-generation.

A PublishedArticle stub is created when the report agent emits a <cite/> tag.
This module fills the stub with body content grounded in public web sources.

The article is authored "by Orionmano Research" (rotated byline). It must:
  - Use ONLY information from public web sources (no paid/confidential data).
  - Substantiate the original claim using public evidence.
  - Read like an industry-analysis piece, not a summary of search results.
  - Include its own short source list at the bottom (public citations).

## Two-pass generation
Pass 1 — outline (DeepSeek Reasoner): produce a structured plan as JSON
(headline, deck, key_takeaways, topic_tags, section H2s, intended data points).
Pass 2 — body (DeepSeek Chat): write the article grounded by the outline and
the same web evidence. This keeps headline craft + structure deliberate while
keeping cost reasonable.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.published_article import PublishedArticle
from app.services.ai.client import generate_text
from app.services.ai.web_search import web_search, format_search_results
from app.services.article.image import find_hero_image
from app.services.article.industries import classify_industry


OUTLINE_SYSTEM_PROMPT = """You are a senior research editor at Orionmano Industries.
You plan rigorous industry-analysis articles before drafting. Your outlines are
specific, fact-anchored, and engineered for a professional audience that values
information density over rhetoric.

Your outputs are STRICT JSON. No prose, no markdown fences, no commentary."""


BODY_SYSTEM_PROMPT = """You are a senior research analyst at Orionmano Industries,
a public research imprint. You write grounded, fact-dense industry analysis for
a professional audience that reads Bloomberg, Reuters, and the FT.

## STRICT RULES
1. Use ONLY information that is verifiable from the public web sources provided. Never invent figures.
2. If sources disagree or do not support a number, qualify it ("industry estimates suggest…", "sources cite a range of…") or omit it.
3. Third-person analytical voice. No first-person. No marketing language. No superlatives without data.
4. Follow the outline you are given for headline, deck, structure, and emphasis.
5. Lede in the first paragraph: lead with the single most important fact, then context. No throat-clearing openings ("In recent years…", "The world of…").
6. Numbers carry weight: prefer precise figures with units and dates over vague claims.
7. End with a "## Sources" section listing only the public sources you actually used, in:
   - Author or Organisation, "Title," Publication, Date. URL

## LENGTH
700–1,100 words. Markdown only. No preamble. No "As an AI" disclaimers.
"""


def _extract_json(raw: str) -> dict[str, Any]:
    """Best-effort JSON extraction from an LLM response. Strips code fences
    and pulls the first `{...}` block if extra text leaks in."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", s, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _estimate_reading_time(body_md: str) -> int:
    words = len(re.findall(r"\b[\w'-]+\b", body_md))
    return max(1, round(words / 220))


async def _plan_outline(
    title: str,
    topic: str,
    claim: str,
    article_date: date,
    sources_block: str,
) -> dict[str, Any]:
    """Run pass 1: produce a structured outline."""
    user_prompt = f"""Plan an industry-analysis article that substantiates this claim using public evidence.

**Working title:** {title}
**Topic:** {topic}
**As-of date:** {article_date.strftime('%B %Y')}
**Core claim:**
{claim}

## Public Web Research (the ONLY permitted evidence)
{sources_block}

---

Return ONLY a JSON object with these exact keys:
{{
  "headline": "Specific, factual, verb-led where possible. ≤90 chars. No clickbait, no questions, no colons-as-clickbait.",
  "deck": "One sentence sub-headline that adds context the headline cannot. ≤160 chars.",
  "key_takeaways": ["3 to 5 short bullet points, each ≤140 chars, factual and specific."],
  "topic_tags": ["3 to 6 short tags, lowercase, kebab-case where multi-word"],
  "lede_angle": "One sentence describing the angle of the opening paragraph (the single most important fact + why it matters).",
  "sections": [
    {{ "h2": "Section heading", "intent": "What this section establishes", "data_points": ["specific facts/figures from the sources to anchor this section"] }}
  ],
  "exhibits": [
    {{
      "type": "bar | line | pie",
      "title": "Specific, factual title — what the chart actually shows.",
      "subtitle": "Optional one-line context.",
      "x_label": "e.g. Year (omit for pie)",
      "y_label": "e.g. Output (omit for pie)",
      "y_unit": "e.g. M tonnes, %, $B",
      "series": [
        {{ "name": "Series label (country / metric / cohort)", "data": [{{ "x": "2020", "y": 1.2 }}] }}
      ],
      "source": "Concise public source attribution, e.g. 'USGS Mineral Commodity Summaries, 2024'",
      "after_section": "The h2 of the section this chart belongs after"
    }}
  ],
  "outlook": "One sentence describing the closing paragraph's forward-looking angle."
}}

Constraints:
- 3 to 5 sections.
- Every data_point must be supported by the public sources above. If you cannot back a number, drop it.
- Headlines must be specific. Bad: "The Future of X". Good: "Indonesia's EV Battery Output Tripled in 2023 as China Capacity Migrates South".

Exhibit constraints (CRITICAL — these are real charts, not decoration):
- REQUIRED: 1 to 3 exhibits. Every article must include at least ONE chart. Bloomberg-style industry analysis is not text-only. If the article's headline number is the only quantified data, build a chart around that one figure (e.g. a comparison bar against the parent market, a forecast line from current to forecast year, or a share-of-total pie).
- Every numeric value must come from the public sources above. If you cannot back a number with a source, omit that data point. Do NOT fabricate numbers to fill a chart slot — but do reuse figures already in the body / sources.
- "bar" — 3-8 categories per series. Up to 2 series. Use for cross-section comparisons (e.g. country output by year, ranked players, segment shares).
- "line" — at least 4 time-series points per series, ordered by x. Up to 2 series. Use for trends over time, including current → forecast trajectories where forecast figures are sourced.
- "pie" — single series, 3-7 slices that add to ~100. Use only for share-of-total breakdowns. Do NOT use pie for trends.
- Each exhibit needs a non-empty `source` attribution naming the underlying public source(s).
- `after_section` must exactly match one of the planned section h2 strings.
"""
    raw = await generate_text(
        system_prompt=OUTLINE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        # The reasoner is verbose. With sections + exhibits the JSON runs
        # ~6-7k chars; budget enough headroom that it never truncates.
        max_tokens=4500,
        use_reasoner=True,
    )
    return _extract_json(raw)


async def _draft_body(
    outline: dict[str, Any],
    author: str,
    article_date: date,
    sources_block: str,
    claim: str,
) -> str:
    """Run pass 2: draft the body grounded by the outline."""
    headline = outline.get("headline", "").strip()
    deck = outline.get("deck", "").strip()
    lede_angle = outline.get("lede_angle", "").strip()
    outlook = outline.get("outlook", "").strip()
    sections = outline.get("sections") or []
    exhibits = outline.get("exhibits") or []

    sections_block = "\n".join(
        f"{i+1}. **{s.get('h2','').strip()}** — {s.get('intent','').strip()}"
        + ("\n   Data to use: " + "; ".join(s.get("data_points") or []) if s.get("data_points") else "")
        for i, s in enumerate(sections)
    )

    if exhibits:
        # Render the planned exhibits as ready-to-paste chart blocks. The
        # body model is told to drop them in verbatim after the named
        # section — no creative editing of the data, since the model
        # already validated the numbers in pass 1.
        rendered_exhibits = []
        for ex in exhibits:
            after = (ex.get("after_section") or "").strip()
            spec = {k: ex.get(k) for k in (
                "type", "title", "subtitle", "x_label", "y_label", "y_unit", "series", "source"
            ) if ex.get(k) is not None}
            rendered_exhibits.append(
                f"After the section titled \"{after}\", insert exactly:\n"
                f"```chart\n{json.dumps(spec, ensure_ascii=False, indent=2)}\n```"
            )
        exhibits_block = "\n\n".join(rendered_exhibits)
        exhibits_section = f"\n\n## Approved exhibits (insert verbatim)\n{exhibits_block}\n"
        exhibits_rule = (
            "- Insert each approved exhibit AS-IS, immediately after the section it is "
            "assigned to. Do not edit the JSON. Do not omit exhibits. Do not add new chart "
            "blocks beyond those listed. The fenced ```chart blocks must use the literal "
            "language tag `chart`."
        )
    else:
        # Outline pass failed or returned no exhibits. Don't ship a chartless
        # article — instruct the body model to synthesise one chart from the
        # quantified data it cites in its own draft. The constraints below
        # mirror the outline-pass exhibit schema so the parser still works.
        exhibits_section = ""
        exhibits_rule = (
            "- REQUIRED: include exactly ONE chart block in the body, since the outline "
            "did not pre-plan exhibits. Place it where it best supports the analysis. "
            "Use this exact format (the language tag MUST be `chart`):\n"
            "  ```chart\n"
            "  {\n"
            "    \"type\": \"bar\" | \"line\" | \"pie\",\n"
            "    \"title\": \"specific factual title\",\n"
            "    \"subtitle\": \"optional one-line context\",\n"
            "    \"x_label\": \"omit for pie\",\n"
            "    \"y_label\": \"omit for pie\",\n"
            "    \"y_unit\": \"e.g. %, M tonnes, $B\",\n"
            "    \"series\": [{ \"name\": \"...\", \"data\": [{\"x\": ..., \"y\": ...}] }],\n"
            "    \"source\": \"concise public source attribution\"\n"
            "  }\n"
            "  ```\n"
            "  Constraints: bar 3-8 cats / ≤2 series; line ≥4 pts / ≤2 series; "
            "pie single series 3-7 slices summing to ~100. Every numeric value must come "
            "from the public sources provided above — never fabricate figures."
        )

    user_prompt = f"""Draft a public-facing industry analysis article using this approved outline.

**Byline:** {author}
**Publication:** Orionmano Industries
**As-of date:** {article_date.strftime('%B %Y')}
**Headline:** {headline}
**Deck:** {deck}
**Lede angle:** {lede_angle}
**Outlook angle:** {outlook}

**Section plan:**
{sections_block}
{exhibits_section}
**Original claim to substantiate:**
{claim}

## Public Web Research (the ONLY permitted evidence)
{sources_block}

---

Output requirements:
- First line: the headline above, prefixed with "# " (markdown H1). Do not change the headline wording.
- Second non-empty line: the deck above as a single italic paragraph (wrap in *…*). Do not change wording.
- Body: follow the section plan exactly. Each section starts with "## " + the planned H2. Use the planned data points. 700–1,100 words total (excluding the exhibit JSON).
{exhibits_rule}
- Final section: "## Sources" — bulleted list of the public sources you actually cited, formatted:
  - Author or Organisation, "Title," Publication, Date. URL
- Do NOT mention Orionmano, Orionmano Assurance, or any client by name unless they appear independently in the public sources.
"""

    return await generate_text(
        system_prompt=BODY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        # Exhibit JSON adds a few hundred tokens; bump headroom.
        max_tokens=3000,
    )


async def _write_article(
    title: str,
    topic: str,
    claim: str,
    author: str,
    article_date: date,
) -> dict[str, Any]:
    """Two-pass article writer. Returns a dict of fields to persist."""
    query = f"{topic.replace('-', ' ')} {claim[:120]}".strip()
    try:
        search_results = await web_search(query, max_results=6)
    except Exception:
        search_results = []
    sources_block = format_search_results(search_results) or "(No external web results available.)"

    outline_warning: str | None = None
    try:
        outline = await _plan_outline(title, topic, claim, article_date, sources_block)
    except Exception as e:
        # Reasoner / JSON failure — fall back to a minimal outline so we still
        # produce a body rather than dropping the article entirely. Record
        # the failure reason on the article so it surfaces to the admin UI
        # instead of disappearing.
        outline_warning = f"Outline pass failed ({type(e).__name__}: {str(e)[:200]}); fell back to minimal outline."
        outline = {
            "headline": title,
            "deck": "",
            "key_takeaways": [],
            "topic_tags": [],
            "lede_angle": claim[:200],
            "sections": [],
            "exhibits": [],
            "outlook": "",
        }

    body = await _draft_body(outline, author, article_date, sources_block, claim)

    refined_title = (outline.get("headline") or title).strip()[:200] or title
    deck = (outline.get("deck") or "").strip()[:400] or None
    key_takeaways = [
        str(t).strip()[:200]
        for t in (outline.get("key_takeaways") or [])
        if str(t).strip()
    ][:5] or None
    topic_tags = [
        str(t).strip().lower()[:40]
        for t in (outline.get("topic_tags") or [])
        if str(t).strip()
    ][:8] or None

    # Strip a leading H1 if the model still emitted one (we already store the
    # headline in `title`). Keep the deck line in body for now since the
    # frontend renderer can choose whether to display it inline.
    body_clean = body.lstrip()
    if body_clean.startswith("# "):
        first_break = body_clean.find("\n")
        body_clean = body_clean[first_break + 1 :].lstrip() if first_break != -1 else ""

    # Hero image — best-effort. Unsplash treats multi-word queries as
    # phrases, so we feed it short candidates ranked from specific to
    # broad. The first candidate that returns a result wins.
    image_candidates: list[str] = []
    # 1) topic tags joined as keywords — most specific.
    if topic_tags:
        kw = " ".join(t.replace("-", " ") for t in topic_tags[:2])
        if kw.strip():
            image_candidates.append(kw)
    # 2) the article topic (slug → spaced).
    image_candidates.append(topic.replace("-", " ").replace("_", " ").strip())
    # 3) just the first tag, broadened.
    if topic_tags:
        image_candidates.append(topic_tags[0].replace("-", " "))

    image_primary = image_candidates[0] if image_candidates else topic
    hero = await find_hero_image(image_primary, fallbacks=image_candidates[1:])

    industry = classify_industry(
        title=refined_title, topic=topic, topic_tags=topic_tags or []
    )

    return {
        "body_md": body_clean,
        "title": refined_title,
        "deck": deck,
        "key_takeaways": key_takeaways,
        "topic_tags": topic_tags,
        "reading_time_minutes": _estimate_reading_time(body_clean),
        "outline_warning": outline_warning,
        "hero_image": hero,
        "industry": industry,
    }


async def generate_article_body(db: AsyncSession, article_id: UUID) -> None:
    """Fill in body_md and structured fields for a single pending PublishedArticle."""
    result = await db.execute(
        select(PublishedArticle).where(PublishedArticle.id == article_id)
    )
    article = result.scalar_one_or_none()
    if not article or article.status not in ("pending", "failed"):
        return

    article.status = "generating"
    await db.commit()

    try:
        out = await _write_article(
            title=article.title,
            topic=article.topic,
            claim=article.claim_text,
            author=article.author,
            article_date=article.article_date,
        )
        article.body_md = out["body_md"]
        article.title = out["title"]
        article.deck = out["deck"]
        article.key_takeaways = out["key_takeaways"]
        article.topic_tags = out["topic_tags"]
        article.reading_time_minutes = out["reading_time_minutes"]
        hero = out.get("hero_image")
        if hero:
            article.hero_image_url = hero["url"]
            article.hero_image_alt = hero["alt"]
            article.hero_image_credit = hero["credit"]
            article.hero_image_credit_url = hero["credit_url"]
        article.industry = out.get("industry")
        # Auto-publish on successful generation. Citation footnotes in
        # industry reports point straight at industries.omassurance.com,
        # so the article must be live the moment the report is delivered.
        # The internal `POST /articles/{id}/publish` endpoint stays around
        # for future manual-review flows but is no longer required.
        article.status = "published"
        # Surface a non-fatal outline warning instead of silently swallowing
        # it; success path otherwise clears any prior error.
        article.generation_error = out.get("outline_warning")
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
            await asyncio.sleep(0.5)
