"""Deck context builder — gathers the company-data slice the LLM consumes
during outline + content passes.

Output is structured JSON-shaped data, not prose. That's deliberate: the deck
generator needs to *pick specific facts* (a revenue number, an industry term, a
target exchange) and slot them into slide content fields. A prose summary
makes that lossy. The chat service already uses prose; deck generation needs
the raw structured form.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.document import Document
from app.models.report import Report, ReportSection


# ---------------------------------------------------------------------------
# Top-level entry: assemble everything in one shot.
# ---------------------------------------------------------------------------


async def build_deck_context(
    db: AsyncSession,
    company_id: UUID,
    *,
    include_reports: bool = True,
    max_report_sections: int = 12,
    max_section_chars: int = 600,
) -> dict[str, Any]:
    """Return a compact structured snapshot of everything the deck generator
    can pull from. Shape:

      {
        "company": {name, legal_name, industry, sub_industry, country,
                    description, website, engagement_type, target_exchange,
                    enterprise_stage, status},
        "financials": {revenue: {FY2023: ..., FY2024: ...}, ...},
        "documents": [{filename, category, key_facts}, ...],
        "reports": [{type, title, status, sections: [{title, snippet}]}, ...],
      }

    `max_report_sections` and `max_section_chars` cap how much report content
    we expand into prompts. Reports are summaries of summaries by the time
    they reach the deck — full-fidelity bodies belong in the report viewer,
    not a slide deck.
    """
    company = await _fetch_company(db, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    documents, financials = await _fetch_documents_and_financials(db, company_id)

    reports: list[dict] = []
    if include_reports:
        reports = await _fetch_reports(
            db,
            company_id,
            max_sections=max_report_sections,
            max_section_chars=max_section_chars,
        )

    return {
        "company": _company_snapshot(company),
        "financials": financials,
        "documents": documents,
        "reports": reports,
    }


# ---------------------------------------------------------------------------
# Helpers — each fetches one slice and shapes it for prompt consumption.
# ---------------------------------------------------------------------------


async def _fetch_company(db: AsyncSession, company_id: UUID) -> Company | None:
    result = await db.execute(select(Company).where(Company.id == company_id))
    return result.scalar_one_or_none()


def _company_snapshot(c: Company) -> dict[str, Any]:
    """The fields the LLM should be able to reference verbatim. Anything not
    listed is intentionally hidden — keep the context narrow."""
    return {
        "name": c.name,
        "legal_name": c.legal_name,
        "industry": c.industry,
        "sub_industry": c.sub_industry,
        "country": c.country,
        "description": c.description,
        "website": c.website,
        "engagement_type": c.engagement_type,
        "target_exchange": c.target_exchange,
        "enterprise_stage": getattr(c, "enterprise_stage", None),
        "status": c.status,
    }


async def _fetch_documents_and_financials(
    db: AsyncSession, company_id: UUID
) -> tuple[list[dict], dict[str, Any]]:
    """Walk completed documents once. Returns:
      - a slim list of {filename, category, key_facts} for non-financial doc context
      - a merged financials dict keyed by metric -> {period: value, ...}

    Merge strategy for financials: newer document wins on conflict (we sort by
    created_at desc before merging). Most-recent-first is the right tiebreaker
    because the audit report extracted last usually supersedes the management
    accounts extracted earlier."""
    q = (
        select(Document)
        .where(
            Document.company_id == company_id,
            Document.extraction_status == "completed",
        )
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(q)
    docs = list(result.scalars().all())

    documents: list[dict] = []
    financials: dict[str, Any] = {}

    for doc in docs:
        data = doc.extracted_data or {}

        # Pull a slim doc card. Skip the raw blob — the LLM doesn't need it.
        doc_kind = data.get("document_type") or doc.category or "other"
        key_facts = _extract_key_facts(data)
        documents.append({
            "filename": doc.filename,
            "category": doc.category,
            "document_type": doc_kind,
            "key_facts": key_facts,
        })

        # Merge financial_data into the running snapshot. Each metric is a dict
        # of {period: value}; we union periods across docs.
        fin = data.get("financial_data") or {}
        # Some extracted shapes nest under e.g. "income_statement"; others are flat.
        for section_key, section_val in fin.items():
            if isinstance(section_val, dict):
                for metric, periods in section_val.items():
                    if not isinstance(periods, dict):
                        continue
                    existing = financials.setdefault(metric, {})
                    for period, value in periods.items():
                        # First-write wins; docs already iterated newest-first.
                        existing.setdefault(period, value)
            elif isinstance(section_val, (str, int, float)):
                financials.setdefault(section_key, section_val)

    return documents, financials


def _extract_key_facts(data: dict[str, Any]) -> dict[str, Any]:
    """Hand-picked top-level facts from extracted document data that are useful
    for deck content. Avoids dumping the entire JSON blob (often 5-50KB per doc)."""
    picks = (
        "company_name",
        "legal_name",
        "registration_number",
        "industry",
        "country",
        "summary",
        "key_highlights",
        "key_risks",
        "headcount",
        "products",
        "markets",
        "customers",
    )
    out: dict[str, Any] = {}
    for key in picks:
        if key in data and data[key] not in (None, "", [], {}):
            out[key] = data[key]
    return out


async def _fetch_reports(
    db: AsyncSession,
    company_id: UUID,
    *,
    max_sections: int,
    max_section_chars: int,
) -> list[dict]:
    """Pull existing reports' section summaries — capped, snippetted. The
    deck generator should use these to ground claims (e.g. industry size,
    valuation range) rather than re-research from scratch."""
    q = (
        select(Report)
        .where(
            Report.company_id == company_id,
            Report.status.in_(["draft", "review", "approved", "published"]),
        )
        .order_by(Report.created_at.desc())
    )
    result = await db.execute(q)
    reports = list(result.scalars().all())

    out: list[dict] = []
    section_budget = max_sections
    for r in reports:
        if section_budget <= 0:
            break
        sec_q = (
            select(ReportSection)
            .where(ReportSection.report_id == r.id)
            .order_by(ReportSection.sort_order)
        )
        sec_res = await db.execute(sec_q)
        sections = list(sec_res.scalars().all())

        section_items: list[dict] = []
        for s in sections:
            if section_budget <= 0:
                break
            snippet = (s.content or "").strip()
            if len(snippet) > max_section_chars:
                snippet = snippet[: max_section_chars - 1].rsplit(" ", 1)[0] + "…"
            section_items.append({
                "key": s.section_key,
                "title": s.section_title,
                "snippet": snippet,
            })
            section_budget -= 1

        out.append({
            "type": r.report_type,
            "title": r.title,
            "status": r.status,
            "tier": r.tier,
            "sections": section_items,
        })

    return out


# ---------------------------------------------------------------------------
# Prompt-side formatting — turn the structured dict into a compact text block
# the LLM can consume cheaply. Keep stable across calls (system-cacheable).
# ---------------------------------------------------------------------------


def context_to_prompt_block(ctx: dict[str, Any]) -> str:
    """Render the context dict as a stable text block suitable for the system
    prompt. Stable formatting matters for DeepSeek prefix caching — identical
    bytes → cache hit at ~10% the cost."""
    import json

    # json.dumps with sort_keys=True gives deterministic, stable bytes regardless
    # of insertion order. ensure_ascii=False keeps unicode (currency symbols,
    # names) intact in the prompt.
    return json.dumps(ctx, indent=2, sort_keys=True, ensure_ascii=False)
