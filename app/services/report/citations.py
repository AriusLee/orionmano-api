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
from sqlalchemy import and_, or_, select

from app.models.published_article import PublishedArticle
from app.config import settings


# Articles created within this window are considered "in-flight" — another
# section of the same report (or a concurrent report) is still generating
# their body. Reusing them keeps the same fact on one footnote target across
# the run. Outside this window, a still-`pending` article is a stuck orphan
# whose generation never completed; reusing it propagates a 404 on
# industries.omassurance.com (the public endpoint only serves status=published).
IN_FLIGHT_PENDING_MINUTES = 30


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
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.ARTICLE_REUSE_DAYS)
    in_flight_cutoff = now - timedelta(minutes=IN_FLIGHT_PENDING_MINUTES)

    # Tier 1 — exact fact match within the freshness window. To keep new
    # citations from inheriting dead links (root cause of the 2026-05 batch
    # of 404s on industries.omassurance.com), the candidate must be EITHER:
    #   (a) status=published with body_md set — the public site can render it; or
    #   (b) status=pending/generating AND created within the in-flight window —
    #       another section/concurrent report is still generating it, so we
    #       share the footnote target until it lands.
    # Stale pending (older than the in-flight window) and any `failed` rows
    # are intentionally NOT reused — they are dead links.
    result = await db.execute(
        select(PublishedArticle)
        .where(
            PublishedArticle.fact_hash == fh,
            PublishedArticle.created_at >= cutoff,
            or_(
                and_(
                    PublishedArticle.status == "published",
                    PublishedArticle.body_md.is_not(None),
                ),
                and_(
                    PublishedArticle.status.in_(("pending", "generating")),
                    PublishedArticle.created_at >= in_flight_cutoff,
                ),
            ),
        )
        .order_by(PublishedArticle.created_at.desc())
        .limit(1)
    )
    fresh_exact = result.scalar_one_or_none()
    if fresh_exact:
        return fresh_exact

    # Tier 2 — same topic, fresh, published with a real body. Previously also
    # accepted `draft` status, but the public endpoint only serves `published`,
    # so any Tier-2 reuse of a draft would 404 in production. Locked to
    # `published` to keep new citation links resolvable.
    result = await db.execute(
        select(PublishedArticle)
        .where(
            PublishedArticle.topic == topic_norm,
            PublishedArticle.created_at >= cutoff,
            PublishedArticle.status == "published",
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
    """Short citation: "Title," Publication, Year. Eric 2026-05-19 #10b —
    month dropped to keep the citation compact and match the industry-expert
    report style. Year-only is sufficient for analyst review and saves space."""
    year = article.article_date.year
    return (
        f'"[{article.title}]({article_url(article)})," '
        f'{article.publication}, {year}.'
    )


# ---------- post-processing ----------

# Matches <cite topic="..." claim="..."/> with either attr order. Quoted
# values may contain anything except a literal double-quote.
_CITE_TAG_RE = re.compile(
    r'<cite\s+(?:topic="(?P<topic1>[^"]+)"\s+claim="(?P<claim1>[^"]+)"'
    r'|claim="(?P<claim2>[^"]+)"\s+topic="(?P<topic2>[^"]+)")\s*/?\s*>',
    re.IGNORECASE,
)

# Inline GFM footnote reference (NOT a definition — definitions end in `:`).
_FOOTNOTE_REF_RE = re.compile(r"\[\^([A-Za-z0-9_-]+)\](?!:)")
# A footnote definition must start a line: `[^N]: ...`.
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([A-Za-z0-9_-]+)\]:", re.MULTILINE)

# Truncated `<cite ...` tag at end of content (no closing `>`).
_TRUNCATED_CITE_RE = re.compile(r"\s*<cite\b[^>]*$", re.IGNORECASE)
# Truncated ` ```chart` fence at end of content. The negative lookahead
# `(?![\s\S]*```)` skips the match when a closing fence still follows, so
# properly-closed charts earlier in the section are left untouched.
_TRUNCATED_CHART_RE = re.compile(
    r"\s*```chart\b(?![\s\S]*```)[\s\S]*$",
    re.IGNORECASE,
)


def salvage_truncated_tail(content: str) -> str:
    """Strip dangling `<cite ...` or ` ```chart` blocks left by max_tokens
    truncation in the LLM output.

    When the LLM hits its token cap mid-attribute or mid-JSON, the partial
    markup never gets parsed by the cite resolver or chart renderer and ends
    up as raw text in the rendered report (or as an "Invalid chart spec"
    banner in the React preview). Trimming the broken tail keeps the rest of
    the section presentable while making the truncation invisible.
    """
    out = content
    # Order matters: a chart fence may itself contain `<cite/>` examples in
    # comments or strings, so strip the chart tail first.
    out = _TRUNCATED_CHART_RE.sub("", out)
    out = _TRUNCATED_CITE_RE.sub("", out)
    return out.rstrip()


def strip_cites_and_footnotes(content: str) -> str:
    """Remove every `<cite .../>` tag, every `[^N]` ref, and every `[^N]:`
    definition block from `content`.

    Eric 2026-05-24 — the DRS Industry Section opens with the OM Report
    chapter-level disclosure, so body prose must NOT carry inline footnotes.
    Chart `source_note` fields and explicit "Source: …" lines inside chart
    JSON / markdown table footers are unaffected because they don't use
    `<cite/>` syntax. Tail-truncation cleanup runs first so dangling tags
    don't survive as raw text.
    """
    out = salvage_truncated_tail(content)
    # Drop every well-formed cite tag.
    out = _CITE_TAG_RE.sub("", out)
    # Drop any residual `<cite ...>` / `<cite ... />` that didn't match the
    # strict tag regex (e.g. malformed attributes). Use a permissive pattern
    # scoped to the literal `<cite` opener so we don't touch unrelated HTML.
    out = re.sub(r"<cite\b[^>]*/?>", "", out, flags=re.IGNORECASE)
    # Drop GFM footnote DEFINITIONS line-by-line: `[^N]: ...` at line start.
    out = re.sub(r"(?m)^\[\^[A-Za-z0-9_-]+\]:.*(?:\n|$)", "", out)
    # Drop inline `[^N]` markers regardless of whether a definition existed.
    out = _FOOTNOTE_REF_RE.sub("", out)
    # Collapse any blank-line runs left by the deletions.
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.rstrip()


def strip_orphan_footnote_refs(content: str) -> str:
    """Remove `[^N]` markers that have no matching `[^N]:` definition.

    The LLM occasionally emits raw GFM footnote syntax despite the prompt
    instructing it to use `<cite/>` tags only. Without a matching definition,
    remark-gfm (and Python markdown without the footnotes extension) leaves
    the marker as raw text — so users see `infrastructure.[^1]` in the
    rendered report. Stripping orphans here makes the body read cleanly.
    """
    defined = set(_FOOTNOTE_DEF_RE.findall(content))

    def _drop_orphan(m: re.Match) -> str:
        return m.group(0) if m.group(1) in defined else ""

    return _FOOTNOTE_REF_RE.sub(_drop_orphan, content)


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
    # First, salvage any tail the LLM truncated mid-tag or mid-chart-JSON.
    # Without this, dangling `<cite ...` and ` ```chart {…` survive as raw
    # text in the PDF and break the React chart parser in the preview UI.
    content = salvage_truncated_tail(content)

    matches = list(_CITE_TAG_RE.finditer(content))
    if not matches:
        # No <cite/> tags to resolve — but the LLM may have emitted raw
        # `[^N]` markers anyway. Strip orphans so they don't render as
        # raw text (e.g. `infrastructure.[^1]`) in HTML/PDF output.
        return strip_orphan_footnote_refs(content), []

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

    # The LLM may have sprinkled additional raw `[^N]` markers alongside
    # the resolved <cite/> tags. Drop any whose number we didn't define.
    out = strip_orphan_footnote_refs(out)

    return out, ordered
