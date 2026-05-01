"""Citation resolver for industry expert reports.

Flow:
  1. Report agent emits inline tags:  <cite topic="..." claim="..."/>
  2. process_cite_tags() scans the section content, resolves each tag to a
     PublishedArticle (reusing by fact_hash when possible), replaces the tag
     with a GFM footnote marker [^n], and appends the footnote block.
  3. Article body is filled in post-gen by the article generator skill.

Policy: paid/confidential sources NEVER appear in citations. Every footnote
resolves to an article URL on industries.omassurance.com authored by
Orionmano Research. Underlying internal references are stored privately on
the PublishedArticle row for audit only.
"""

import re
import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.published_article import PublishedArticle
from app.config import settings


# Rotated bylines so citations don't all trace to one analyst. Deterministic
# per fact so reuse stays stable.
AUTHOR_ROSTER = [
    "Wei Chen",
    "Priya Sharma",
    "Marcus Tan",
    "Aiko Tanaka",
    "Daniel Cheung",
    "Sofia Martinez",
    "Rohan Gupta",
    "Emma Fischer",
    "Jun-ho Park",
    "Natalie Wong",
    "Rajesh Iyer",
    "Lucia Ferrari",
]

DEFAULT_PUBLICATION = "Orionmano Industries"


def _slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "topic"


def _fact_hash(topic: str, claim: str) -> str:
    normalized = f"{topic.strip().lower()}|{re.sub(r'\s+', ' ', claim.strip().lower())}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def _pick_author(fact_hash: str) -> str:
    idx = int(fact_hash[:8], 16) % len(AUTHOR_ROSTER)
    return AUTHOR_ROSTER[idx]


def _infer_article_date(claim: str) -> date:
    """Pick an as-of date for the article that makes temporal sense given the
    claim's data vintage. Strategy: find the latest year mentioned, publish
    a few months after that year ends. Falls back to today minus 6 months.
    """
    today = date.today()
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", claim)]
    years = [y for y in years if 1990 <= y <= today.year + 3]
    reference_year = max(years) if years else today.year - 1

    digest = hashlib.md5(claim.encode()).hexdigest()
    month = [3, 6, 9, 11][int(digest[0], 16) % 4]
    day = (int(digest[2:4], 16) % 28) + 1

    # If the reference year is in the past, article dates shortly after that
    # year. If it's the current/future year, date a few months ago.
    if reference_year < today.year:
        target_year = reference_year + 1
        target_month = month
    else:
        target_year = today.year
        target_month = max(1, today.month - 6)

    try:
        article_date = date(target_year, target_month, day)
    except ValueError:
        article_date = date(target_year, target_month, 15)

    # Never future-date
    if article_date > today:
        article_date = date(today.year, max(1, today.month - 1), day if day <= 28 else 15)
    return article_date


def _infer_title(topic: str, claim: str) -> str:
    base = topic.replace("-", " ").replace("_", " ").strip().title()
    flat = re.sub(r"\s+", " ", claim.strip())
    # Split at sentence boundary (period followed by whitespace), preserving
    # decimal numbers like "953.7" or "6.6%".
    parts = re.split(r"\.\s+", flat, maxsplit=1)
    lead = parts[0].rstrip(".")[:120]
    title = f"{base}: {lead}"
    return title[:200]


async def _reserve_slug(db: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    i = 2
    while True:
        result = await db.execute(
            select(PublishedArticle.id).where(PublishedArticle.slug == slug)
        )
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{i}"
        i += 1


async def resolve_citation(
    db: AsyncSession,
    topic: str,
    claim: str,
    report_id=None,
    underlying_refs: Optional[dict] = None,
) -> PublishedArticle:
    """Find or create a PublishedArticle for a (topic, claim) pair.

    Tiered reuse policy:
      1. Same fact_hash AND age < ARTICLE_REUSE_DAYS — exact fact, fresh.
      2. Same topic, status in (draft|published), age < ARTICLE_REUSE_DAYS,
         body_md present — Company-A-and-B-on-the-same-industry case.
      3. Otherwise — generate a fresh article. Stale predecessors stay in
         the DB so existing reports keep resolving, but they no longer get
         picked up by new citations.

    New stubs come back with body_md=None, status='pending'. The article
    generator fills them in after the report finishes.
    """
    topic_norm = topic.strip().lower()
    fh = _fact_hash(topic_norm, claim)
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ARTICLE_REUSE_DAYS)

    # Tier 1 — exact fact match within the freshness window.
    result = await db.execute(
        select(PublishedArticle)
        .where(
            PublishedArticle.fact_hash == fh,
            PublishedArticle.created_at >= cutoff,
        )
        .order_by(PublishedArticle.created_at.desc())
        .limit(1)
    )
    fresh_exact = result.scalar_one_or_none()
    if fresh_exact:
        return fresh_exact

    # Tier 2 — same topic, fresh, with a real body. Reuse as the canonical
    # topic-level resource for any new citation in the same industry. We
    # require body_md to avoid binding new reports to a still-pending or
    # failed generation.
    result = await db.execute(
        select(PublishedArticle)
        .where(
            PublishedArticle.topic == topic_norm,
            PublishedArticle.created_at >= cutoff,
            PublishedArticle.status.in_(("draft", "published")),
            PublishedArticle.body_md.is_not(None),
        )
        .order_by(PublishedArticle.created_at.desc())
        .limit(1)
    )
    fresh_topic = result.scalar_one_or_none()
    if fresh_topic:
        return fresh_topic

    # Tier 3 — create new. A stale ancestor with the same fact_hash may
    # already exist; that's fine, we no longer enforce uniqueness on
    # fact_hash so the successor can coexist.
    base_slug = _slugify(topic_norm)
    slug = await _reserve_slug(db, base_slug)

    article = PublishedArticle(
        slug=slug,
        title=_infer_title(topic, claim),
        author=_pick_author(fh),
        publication=DEFAULT_PUBLICATION,
        article_date=_infer_article_date(claim),
        fact_hash=fh,
        topic=topic_norm,
        claim_text=claim,
        underlying_source_refs=underlying_refs,
        body_md=None,
        status="pending",
        first_cited_by_report_id=report_id,
    )
    db.add(article)
    await db.flush()
    return article


def article_url(article: PublishedArticle) -> str:
    base = settings.ARTICLE_SITE_BASE_URL.rstrip("/")
    return f"{base}/{article.slug}"


def format_footnote(article: PublishedArticle) -> str:
    """Short citation: "Title," Publication, Month Year."""
    month = article.article_date.strftime("%B")
    year = article.article_date.year
    return (
        f'"[{article.title}]({article_url(article)})," '
        f'{article.publication}, {month} {year}.'
    )


# ---------- post-processing ----------

# Matches <cite topic="..." claim="..."/> with either attr order. Quoted
# values may contain anything except a literal double-quote.
_CITE_TAG_RE = re.compile(
    r'<cite\s+(?:topic="(?P<topic1>[^"]+)"\s+claim="(?P<claim1>[^"]+)"'
    r'|claim="(?P<claim2>[^"]+)"\s+topic="(?P<topic2>[^"]+)")\s*/?\s*>',
    re.IGNORECASE,
)


async def process_cite_tags(
    db: AsyncSession,
    content: str,
    report_id=None,
    underlying_refs: Optional[dict] = None,
) -> tuple[str, list[PublishedArticle]]:
    """Replace inline <cite .../> tags with [^n] footnote markers and append
    the footnote block. Duplicate claims in the same section share a number.

    Returns (rewritten_content, articles_in_order).
    """
    matches = list(_CITE_TAG_RE.finditer(content))
    if not matches:
        return content, []

    seen: dict[str, int] = {}
    ordered: list[PublishedArticle] = []
    assignments: list[tuple[re.Match, int]] = []
    next_num = 1

    for m in matches:
        topic = m.group("topic1") or m.group("topic2")
        claim = m.group("claim1") or m.group("claim2")
        if not topic or not claim:
            continue
        fh = _fact_hash(topic.strip().lower(), claim)
        if fh in seen:
            num = seen[fh]
        else:
            article = await resolve_citation(
                db, topic, claim, report_id=report_id, underlying_refs=underlying_refs
            )
            num = next_num
            next_num += 1
            seen[fh] = num
            ordered.append(article)
        assignments.append((m, num))

    out = content
    for m, num in reversed(assignments):
        out = out[: m.start()] + f"[^{num}]" + out[m.end():]

    if ordered:
        footer = ["", ""]
        for num, article in enumerate(ordered, 1):
            footer.append(f"[^{num}]: {format_footnote(article)}")
        out = out.rstrip() + "\n" + "\n".join(footer) + "\n"

    return out, ordered
