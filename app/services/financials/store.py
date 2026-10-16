"""Confirmed historical figures: sync from documents, lock, amend, review.

Rules (Eric 2026-10):
  - A document tagged to a target period only ever WRITES that period. Other
    periods it shows (prior-year comparatives) are compared with what we hold;
    a different value opens a discrepancy for review, and nothing is written.
  - A locked period is never written by extraction. A different value opens a
    discrepancy; the analyst accepts it (logged) or dismisses it.
  - A figure the analyst typed by hand is treated like a locked one: a later
    extraction never overwrites it silently.
  - An untagged document fills unlocked periods only (the old behaviour,
    minus the ability to change confirmed history).
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.financials import (
    FinancialDiscrepancy,
    FinancialFigure,
    FinancialFigureAmendment,
    FinancialPeriod,
)
from app.services.financials import catalogue as cat

logger = logging.getLogger(__name__)


class FinancialsError(ValueError):
    """A request the store refuses (bad period, missing reason …)."""


# ─── Reading extracted data ──────────────────────────────────────────────────

@dataclass
class ExtractedFigure:
    item: cat.LineItem
    period_label: str
    period_type: str
    fiscal_year: int | None
    value: float | None
    currency: str | None
    unit: str | None
    unit_multiplier: float
    source_page: str | None


def extracted_figures(extracted: dict | None) -> list[ExtractedFigure]:
    """Flatten a document's `financial_data` into one entry per (period, line)."""
    if not isinstance(extracted, dict):
        return []
    fd = extracted.get("financial_data")
    if not isinstance(fd, dict):
        return []
    currency = cat.normalize_currency(fd.get("currency"))
    unit = str(fd.get("unit") or "").strip() or None
    mult = cat.unit_multiplier(unit)
    # A currency glued to the unit ("RM'000") counts when currency is blank.
    if currency is None and unit:
        currency = cat.normalize_currency(unit)
    pages = fd.get("source_pages") if isinstance(fd.get("source_pages"), dict) else {}

    out: list[ExtractedFigure] = []
    for statement in cat.STATEMENTS:
        block = fd.get(statement)
        if not isinstance(block, dict):
            continue
        for raw_key, by_period in block.items():
            if not isinstance(by_period, dict):
                continue
            item = cat.resolve(statement, str(raw_key))
            page = pages.get(f"{statement}.{raw_key}") or pages.get(f"{statement}.{item.key}") or pages.get(statement)
            for raw_label, raw_value in by_period.items():
                value = cat.parse_number(raw_value)
                if value is None:
                    continue
                label, ptype, year = cat.normalize_period(str(raw_label))
                if year is None:
                    # "RENT", "OTHERS" … a breakdown keyed where a period belongs.
                    continue
                out.append(ExtractedFigure(
                    item=item,
                    period_label=label,
                    period_type=ptype,
                    fiscal_year=year,
                    value=value,
                    currency=currency,
                    unit=unit,
                    unit_multiplier=mult,
                    source_page=str(page) if page not in (None, "") else None,
                ))
    return out


# ─── Source authority ────────────────────────────────────────────────────────

_SCHEDULE_NAME = re.compile(
    r"lead\s*-?\s*sheet|schedule|breakdown|working\s*paper|reconciliation|\btop\s*\d+|vendors?|customers?|"
    r"aging|ageing|summary|liability report|listing|trial\s*balance|\btb\b",
    re.IGNORECASE,
)


def source_rank(doc: Document | None) -> int:
    """How far a document's figures can be trusted, highest first:
      3 — face financial statements: prospectus / DRS / F-1, audited report,
          compiled financial statements
      2 — management accounts
      1 — anything else (projections, decks …)
      0 — supporting schedules: leadsheets, breakdowns, top-N lists. These
          only fill a line no better source has; they never overwrite one.
    Classification alone can't tell a leadsheet from an audit report (both
    come back as audit_report), so the filename decides first."""
    if doc is None:
        return 1
    if _SCHEDULE_NAME.search(doc.filename or ""):
        return 0
    cats = set(doc.categories or []) | ({doc.category} if doc.category else set())
    if cats & {"prospectus", "audit_report", "financial_statements"}:
        return 3
    if "management_accounts" in cats:
        return 2
    return 1


# ─── Periods ─────────────────────────────────────────────────────────────────

async def get_or_create_period(
    db: AsyncSession, company_id: uuid.UUID, label: str, period_type: str | None = None, fiscal_year: int | None = None,
) -> FinancialPeriod:
    norm, ptype, year = cat.normalize_period(label)
    period = (await db.execute(
        select(FinancialPeriod).where(FinancialPeriod.company_id == company_id, FinancialPeriod.label == norm)
    )).scalar_one_or_none()
    if period is not None:
        return period
    period = FinancialPeriod(
        company_id=company_id,
        label=norm,
        period_type=period_type or ptype,
        fiscal_year=fiscal_year if fiscal_year is not None else year,
        # Initialised so code can append to it without a lazy load (async).
        figures=[],
    )
    db.add(period)
    await db.flush()
    return period


async def _periods(db: AsyncSession, company_id: uuid.UUID) -> dict[str, FinancialPeriod]:
    rows = (await db.execute(
        select(FinancialPeriod).where(FinancialPeriod.company_id == company_id)
    )).scalars().all()
    return {p.label: p for p in rows}


# ─── Sync from a document ────────────────────────────────────────────────────

async def sync_document(db: AsyncSession, doc: Document) -> dict[str, int]:
    """Apply one document's extracted figures under the rules above. Commits."""
    figures = extracted_figures(doc.extracted_data)
    stats = {"written": 0, "unchanged": 0, "discrepancies": 0, "skipped": 0}
    if not figures:
        return stats

    target = cat.normalize_period(doc.target_period)[0] if doc.target_period else None
    # A re-extraction replaces this document's earlier open findings.
    await db.execute(delete(FinancialDiscrepancy).where(
        FinancialDiscrepancy.document_id == doc.id, FinancialDiscrepancy.status == "open"
    ))
    periods = await _periods(db, doc.company_id)
    rank = source_rank(doc)
    company_docs = {
        d.id: d for d in (await db.execute(select(Document).where(Document.company_id == doc.company_id))).scalars().all()
    }

    for f in figures:
        period = periods.get(f.period_label)
        existing: FinancialFigure | None = None
        if period is not None:
            existing = next((x for x in period.figures if x.line_item == f.item.key), None)

        is_comparative = target is not None and f.period_label != target
        if is_comparative:
            # Never written. Only flagged when it contradicts what we hold.
            if existing is not None and _differs(existing, f):
                _add_discrepancy(db, doc, f, existing, "comparative")
                stats["discrepancies"] += 1
            else:
                stats["skipped"] += 1
            continue

        protected = period is not None and period.locked
        if protected or (existing is not None and existing.origin == "manual"):
            if existing is None or _differs(existing, f):
                _add_discrepancy(db, doc, f, existing, "locked_period")
                stats["discrepancies"] += 1
            else:
                stats["unchanged"] += 1
            continue

        if period is None:
            period = await get_or_create_period(db, doc.company_id, f.period_label, f.period_type, f.fiscal_year)
            periods[period.label] = period
        if existing is None:
            fig = FinancialFigure(
                company_id=doc.company_id,
                period_id=period.id,
                line_item=f.item.key,
                value=f.value,
                currency=f.currency,
                unit=f.unit,
                unit_multiplier=f.unit_multiplier,
                source_document_id=doc.id,
                source_page=f.source_page,
                origin="extraction",
            )
            db.add(fig)
            period.figures.append(fig)
            stats["written"] += 1
        elif existing.source_document_id != doc.id and source_rank(company_docs.get(existing.source_document_id)) > rank:
            # A better source already gave this figure (e.g. the F-1's face
            # statement vs a leadsheet). Keep it.
            stats["skipped"] += 1
        elif _differs(existing, f) or existing.source_document_id != doc.id or (f.source_page and existing.source_page != f.source_page):
            existing.value = f.value
            existing.currency = f.currency
            existing.unit = f.unit
            existing.unit_multiplier = f.unit_multiplier
            existing.source_document_id = doc.id
            existing.source_page = f.source_page
            stats["written"] += 1
        else:
            stats["unchanged"] += 1

    stats["needs_review"] = _flag_reviews(doc, periods)
    await db.commit()
    return stats


# ─── Needs review ────────────────────────────────────────────────────────────

def _llm_review_flags(extracted: dict | None) -> dict[tuple[str, str], str]:
    """(line item key, period label) -> reason, from the extraction's own
    `financial_data.needs_review` list."""
    fd = (extracted or {}).get("financial_data") if isinstance(extracted, dict) else None
    out: dict[tuple[str, str], str] = {}
    for f in (fd or {}).get("needs_review") or []:
        if not isinstance(f, dict) or not f.get("line_item") or not f.get("period"):
            continue
        reason = str(f.get("reason") or "").strip()
        if not reason:
            continue
        item = cat.resolve(str(f.get("statement") or "income_statement"), str(f["line_item"]))
        label = cat.normalize_period(str(f["period"]))[0]
        out[(item.key, label)] = reason
    return out


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


def _subtotal_checks(by_key: dict[str, FinancialFigure]) -> dict[str, str]:
    """Subtotals that don't add up, as {line item of the subtotal: why}.
    Compared in the figures' own unit; only when all parts share it."""
    out: dict[str, str] = {}

    def val(k: str) -> float | None:
        f = by_key.get(k)
        return f.value if f is not None and f.value is not None else None

    def comparable(*keys: str) -> bool:
        figs = [by_key[k] for k in keys]
        return len({(f.currency, f.unit_multiplier) for f in figs}) == 1

    def off(expected: float, shown: float) -> bool:
        return abs(expected - shown) > max(1.0, 0.005 * abs(expected))

    rev, cogs, gp = val("revenue"), val("cogs"), val("gross_profit")
    if None not in (rev, cogs, gp) and comparable("revenue", "cogs", "gross_profit"):
        exp = rev - abs(cogs)
        if off(exp, gp):
            out["gross_profit"] = (f"Doesn't add up: revenue {_fmt(rev)} − cost of sales {_fmt(abs(cogs))} = {_fmt(exp)}, "
                                   f"but the document shows {_fmt(gp)} (difference {_fmt(gp - exp)}).")
    pbt, tax, ni = val("profit_before_tax"), val("tax_expense"), val("net_income")
    if None not in (pbt, tax, ni) and comparable("profit_before_tax", "tax_expense", "net_income"):
        # A tax credit raises profit; accept either direction.
        if off(pbt - abs(tax), ni) and off(pbt + abs(tax), ni):
            out["net_income"] = (f"Doesn't add up: profit before tax {_fmt(pbt)} less tax {_fmt(abs(tax))} = {_fmt(pbt - abs(tax))}, "
                                 f"but the document shows net profit {_fmt(ni)}.")
    ebit, da, ebitda = val("ebit"), val("da"), val("ebitda")
    if None not in (ebit, da, ebitda) and comparable("ebit", "da", "ebitda"):
        exp = ebit + abs(da)
        if off(exp, ebitda):
            out["ebitda"] = (f"Doesn't add up: EBIT {_fmt(ebit)} + D&A {_fmt(abs(da))} = {_fmt(exp)}, "
                             f"but the document shows EBITDA {_fmt(ebitda)}.")
    ta, tl, te = val("total_assets"), val("total_liabilities"), val("total_equity")
    if None not in (ta, tl, te) and comparable("total_assets", "total_liabilities", "total_equity"):
        exp = abs(tl) + te
        if off(exp, ta):
            out["total_assets"] = (f"Balance sheet doesn't balance: liabilities {_fmt(abs(tl))} + equity {_fmt(te)} = {_fmt(exp)}, "
                                   f"but total assets are {_fmt(ta)}.")
    return out


def _flag_reviews(doc: Document, periods: dict[str, FinancialPeriod]) -> int:
    """Re-mark this document's figures: the extraction's own flags, then the
    subtotal checks. Figures from other documents are left as they are."""
    llm = _llm_review_flags(doc.extracted_data)
    flagged = 0
    for period in periods.values():
        mine = [f for f in period.figures if f.source_document_id == doc.id and f.origin != "manual"]
        if not mine:
            continue
        checks = _subtotal_checks({f.line_item: f for f in period.figures})
        for f in mine:
            notes = [n for n in (llm.get((f.line_item, period.label)), checks.get(f.line_item)) if n]
            f.review_note = " ".join(notes) or None
            flagged += bool(notes)
    return flagged


def statement_basis(doc_category: str | None, extracted_basis: str | None) -> str | None:
    """audited / reviewed / management accounts, as the document says; else
    what its classification implies; else unknown (None)."""
    b = (extracted_basis or "").strip().lower()
    if b in ("audited", "reviewed"):
        return b
    if b in ("management", "management accounts", "unaudited"):
        return "management accounts"
    if doc_category == "audit_report":
        return "audited"
    if doc_category == "management_accounts":
        return "management accounts"
    return None


def _differs(existing: FinancialFigure, f: ExtractedFigure) -> bool:
    if existing.currency and f.currency and existing.currency != f.currency:
        # Different currency: not comparable here, and not something to flag
        # as a contradiction (a translated comparative, typically).
        return False
    return not cat.same_value(existing.value, existing.unit_multiplier or 1.0, f.value, f.unit_multiplier)


def _add_discrepancy(db: AsyncSession, doc: Document, f: ExtractedFigure, existing: FinancialFigure | None, kind: str) -> None:
    db.add(FinancialDiscrepancy(
        company_id=doc.company_id,
        period_label=f.period_label,
        line_item=f.item.key,
        current_value=existing.value if existing else None,
        current_currency=existing.currency if existing else None,
        current_unit=existing.unit if existing else None,
        document_value=f.value,
        document_currency=f.currency,
        document_unit=f.unit,
        document_unit_multiplier=f.unit_multiplier,
        document_id=doc.id,
        source_page=f.source_page,
        kind=kind,
    ))


async def sync_company(db: AsyncSession, company_id: uuid.UUID) -> dict[str, int]:
    """Re-read every completed document, oldest first (so newer documents win
    unlocked periods). Locked periods and manual figures are untouched."""
    docs = (await db.execute(
        select(Document)
        .where(Document.company_id == company_id, Document.extraction_status == "completed")
        .order_by(Document.created_at.asc())
    )).scalars().all()
    total = {"documents": 0, "written": 0, "unchanged": 0, "discrepancies": 0, "skipped": 0}
    for d in docs:
        stats = await sync_document(db, d)
        if any(stats.values()):
            total["documents"] += 1
        for k, v in stats.items():
            total[k] = total.get(k, 0) + v
    return total


async def ensure_synced(db: AsyncSession, company_id: uuid.UUID) -> None:
    """First look at a company that predates this store: build it from the
    documents already extracted."""
    has_period = (await db.execute(
        select(FinancialPeriod.id).where(FinancialPeriod.company_id == company_id).limit(1)
    )).scalar_one_or_none()
    if has_period is None:
        await sync_company(db, company_id)


# ─── Analyst actions ─────────────────────────────────────────────────────────

async def _period_by_id(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> FinancialPeriod:
    period = (await db.execute(
        select(FinancialPeriod).where(FinancialPeriod.id == period_id, FinancialPeriod.company_id == company_id)
    )).scalar_one_or_none()
    if period is None:
        raise FinancialsError("Period not found")
    return period


async def set_lock(
    db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID, locked: bool, user_id: uuid.UUID | None, reason: str | None,
) -> FinancialPeriod:
    period = await _period_by_id(db, company_id, period_id)
    if period.locked == locked:
        return period
    if not locked and not (reason or "").strip():
        raise FinancialsError("Give a reason for unlocking a confirmed period")
    period.locked = locked
    period.locked_by = user_id if locked else None
    period.locked_at = datetime.now(timezone.utc) if locked else None
    db.add(FinancialFigureAmendment(
        company_id=company_id,
        period_label=period.label,
        line_item="*",
        reason=(reason or "").strip() or None,
        action="lock" if locked else "unlock",
        was_locked=not locked,
        user_id=user_id,
    ))
    await db.commit()
    await db.refresh(period)
    return period


async def create_period(db: AsyncSession, company_id: uuid.UUID, label: str, end_date: Any = None) -> FinancialPeriod:
    if not (label or "").strip():
        raise FinancialsError("Period label is required")
    period = await get_or_create_period(db, company_id, label)
    if end_date is not None:
        period.end_date = end_date
    await db.commit()
    await db.refresh(period)
    return period


async def edit_figure(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    period_id: uuid.UUID,
    line_item: str,
    value: float | None,
    reason: str | None,
    user_id: uuid.UUID | None,
    currency: str | None = None,
    unit: str | None = None,
    source_page: str | None = None,
) -> FinancialFigure | None:
    """Set (or clear, value=None) one figure by hand. In a locked period this
    needs a reason; every manual change is logged."""
    period = await _period_by_id(db, company_id, period_id)
    if period.locked and not (reason or "").strip():
        raise FinancialsError(f"{period.label} is locked — give a reason for the amendment")
    existing = next((x for x in period.figures if x.line_item == line_item), None)
    old = existing.value if existing else None
    if value is None:
        if existing is not None:
            await db.delete(existing)
    elif existing is None:
        # Default the unit/currency to the period's other figures.
        sibling = next(iter(period.figures), None)
        cur = cat.normalize_currency(currency) if currency else (sibling.currency if sibling else None)
        un = unit if unit is not None else (sibling.unit if sibling else None)
        existing = FinancialFigure(
            company_id=company_id,
            period_id=period.id,
            line_item=line_item,
            value=value,
            currency=cur,
            unit=un,
            unit_multiplier=cat.unit_multiplier(un),
            source_page=source_page,
            origin="manual",
            updated_by=user_id,
        )
        db.add(existing)
    else:
        existing.value = value
        if currency:
            existing.currency = cat.normalize_currency(currency)
        if unit is not None:
            existing.unit = unit
            existing.unit_multiplier = cat.unit_multiplier(unit)
        if source_page is not None:
            existing.source_page = source_page
        existing.origin = "manual"
        existing.updated_by = user_id
        # The analyst has looked at it and set the value.
        existing.review_note = None
    db.add(FinancialFigureAmendment(
        company_id=company_id,
        period_label=period.label,
        line_item=line_item,
        old_value=old,
        new_value=value,
        reason=(reason or "").strip() or None,
        action="edit",
        was_locked=period.locked,
        user_id=user_id,
    ))
    await db.commit()
    return existing if value is not None else None


async def resolve_discrepancy(
    db: AsyncSession, company_id: uuid.UUID, discrepancy_id: uuid.UUID, accept: bool, user_id: uuid.UUID | None, reason: str | None = None,
) -> FinancialDiscrepancy:
    d = (await db.execute(
        select(FinancialDiscrepancy).where(FinancialDiscrepancy.id == discrepancy_id, FinancialDiscrepancy.company_id == company_id)
    )).scalar_one_or_none()
    if d is None:
        raise FinancialsError("Discrepancy not found")
    if d.status != "open":
        return d
    if accept:
        period = await get_or_create_period(db, company_id, d.period_label)
        existing = next((x for x in period.figures if x.line_item == d.line_item), None)
        old = existing.value if existing else None
        doc_name = None
        if d.document_id is not None:
            doc_name = (await db.execute(select(Document.filename).where(Document.id == d.document_id))).scalar_one_or_none()
        if existing is None:
            existing = FinancialFigure(company_id=company_id, period_id=period.id, line_item=d.line_item)
            db.add(existing)
        existing.value = d.document_value
        existing.currency = d.document_currency
        existing.unit = d.document_unit
        existing.unit_multiplier = d.document_unit_multiplier or 1.0
        existing.source_document_id = d.document_id
        existing.source_page = d.source_page
        existing.origin = "extraction"
        existing.updated_by = user_id
        db.add(FinancialFigureAmendment(
            company_id=company_id,
            period_label=d.period_label,
            line_item=d.line_item,
            old_value=old,
            new_value=d.document_value,
            reason=(reason or "").strip() or f"Accepted the value in {doc_name or 'a document'}",
            action="resolve_discrepancy",
            was_locked=period.locked,
            user_id=user_id,
        ))
    d.status = "accepted" if accept else "dismissed"
    d.resolved_by = user_id
    d.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return d


# ─── Read model for the API ──────────────────────────────────────────────────

def _period_sort_key(p: FinancialPeriod) -> tuple:
    order = {"FY": 9, "H2": 8, "Q4": 7, "9M": 6, "Q3": 5, "H1": 4, "Q2": 3, "Q1": 2}
    tag = p.label.split("_")[0] if "_" in p.label else p.label[:2]
    return (p.fiscal_year or 0, 1 if p.period_type == "annual" else 0, order.get(tag, 0), p.label)


async def table(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    await ensure_synced(db, company_id)
    periods = sorted(
        (await db.execute(select(FinancialPeriod).where(FinancialPeriod.company_id == company_id))).scalars().all(),
        key=_period_sort_key,
    )
    docs = (await db.execute(
        select(Document.id, Document.filename, Document.target_period, Document.extraction_status, Document.created_at,
               Document.category, Document.extracted_data["financial_data"]["statement_basis"].astext.label("basis"))
        .where(Document.company_id == company_id)
        .order_by(Document.created_at.desc())
    )).all()
    doc_names = {d.id: d.filename for d in docs}
    doc_basis = {d.id: statement_basis(d.category, d.basis) for d in docs}

    rows: dict[str, dict[str, Any]] = {}
    for li in cat.LINE_ITEMS:
        rows[li.key] = {"key": li.key, "label": li.label, "statement": li.statement, "in_model": li.hist_key is not None, "values": {}}
    for p in periods:
        for f in p.figures:
            if f.line_item not in rows:
                li = cat.item_for(f.line_item)
                rows[f.line_item] = {"key": li.key, "label": li.label, "statement": li.statement, "in_model": False, "values": {}}
            rows[f.line_item]["values"][p.label] = {
                "id": str(f.id),
                "value": f.value,
                "currency": f.currency,
                "unit": f.unit,
                "unit_multiplier": f.unit_multiplier,
                "source_document_id": str(f.source_document_id) if f.source_document_id else None,
                "source_document_name": doc_names.get(f.source_document_id),
                "source_page": f.source_page,
                "source_basis": doc_basis.get(f.source_document_id),
                "review_note": f.review_note,
                "origin": f.origin,
                "updated_at": (f.updated_at or f.created_at).isoformat() if (f.updated_at or f.created_at) else None,
            }

    discrepancies = (await db.execute(
        select(FinancialDiscrepancy)
        .where(FinancialDiscrepancy.company_id == company_id, FinancialDiscrepancy.status == "open")
        .order_by(FinancialDiscrepancy.created_at.desc())
    )).scalars().all()
    amendments = (await db.execute(
        select(FinancialFigureAmendment)
        .where(FinancialFigureAmendment.company_id == company_id)
        .order_by(FinancialFigureAmendment.created_at.desc())
        .limit(200)
    )).scalars().all()

    from app.models.user import User
    user_ids = {a.user_id for a in amendments if a.user_id} | {p.locked_by for p in periods if p.locked_by}
    users = {}
    if user_ids:
        users = {u.id: u.name for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()}

    return {
        "periods": [
            {
                "id": str(p.id),
                "label": p.label,
                "period_type": p.period_type,
                "fiscal_year": p.fiscal_year,
                "end_date": p.end_date.isoformat() if p.end_date else None,
                "locked": p.locked,
                "locked_at": p.locked_at.isoformat() if p.locked_at else None,
                "locked_by": users.get(p.locked_by),
                "figure_count": len(p.figures),
            }
            for p in periods
        ],
        "rows": [r for r in rows.values() if r["values"]] + [
            {**r, "empty": True} for r in rows.values() if not r["values"] and r["key"] in cat.BY_KEY
        ],
        "statements": [{"key": k, "label": v} for k, v in cat.STATEMENT_LABELS.items()],
        "discrepancies": [
            {
                "id": str(d.id),
                "period_label": d.period_label,
                "line_item": d.line_item,
                "line_label": cat.item_for(d.line_item).label,
                "current_value": d.current_value,
                "current_currency": d.current_currency,
                "current_unit": d.current_unit,
                "document_value": d.document_value,
                "document_currency": d.document_currency,
                "document_unit": d.document_unit,
                "document_id": str(d.document_id) if d.document_id else None,
                "document_name": doc_names.get(d.document_id),
                "source_page": d.source_page,
                "kind": d.kind,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in discrepancies
        ],
        "amendments": [
            {
                "id": str(a.id),
                "period_label": a.period_label,
                "line_item": a.line_item,
                "line_label": "Whole period" if a.line_item == "*" else cat.item_for(a.line_item).label,
                "old_value": a.old_value,
                "new_value": a.new_value,
                "reason": a.reason,
                "action": a.action,
                "was_locked": a.was_locked,
                "user": users.get(a.user_id),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in amendments
        ],
        "documents": [
            {"id": str(d.id), "filename": d.filename, "target_period": d.target_period, "extraction_status": d.extraction_status}
            for d in docs
        ],
    }


# ─── Feeding the valuation model ─────────────────────────────────────────────

@dataclass
class HistoryPlan:
    """How confirmed periods map onto historical_fs (index 4 = FY-1, the base year)."""

    slot_labels: list[str | None]  # 5 entries, oldest first
    # slot index → {"label", "figures": [(LineItem, value, multiplier, currency, source)]}
    locked_slots: dict[int, dict[str, Any]] = field(default_factory=dict)

    @property
    def any_locked(self) -> bool:
        return bool(self.locked_slots)


async def history_plan(db: AsyncSession, company_id: uuid.UUID) -> HistoryPlan | None:
    await ensure_synced(db, company_id)
    periods = (await db.execute(
        select(FinancialPeriod).where(
            FinancialPeriod.company_id == company_id,
            FinancialPeriod.period_type == "annual",
            FinancialPeriod.fiscal_year.is_not(None),
        )
    )).scalars().all()
    periods = [p for p in periods if p.figures]
    if not periods:
        return None
    by_year = {p.fiscal_year: p for p in periods}
    latest = max(by_year)
    years = [latest - 4 + i for i in range(5)]
    plan = HistoryPlan(slot_labels=[by_year[y].label if y in by_year else f"FY{y}" for y in years])
    doc_ids = {f.source_document_id for p in periods for f in p.figures if f.source_document_id}
    names = {}
    if doc_ids:
        names = dict((await db.execute(select(Document.id, Document.filename).where(Document.id.in_(doc_ids)))).all())
    for i, y in enumerate(years):
        p = by_year.get(y)
        if p is None or not p.locked:
            continue
        figs = []
        for f in p.figures:
            li = cat.item_for(f.line_item)
            if li.hist_key is None or f.value is None:
                continue
            src = names.get(f.source_document_id) or ("entered by analyst" if f.origin == "manual" else None)
            if src and f.source_page:
                src = f"{src}, p. {f.source_page}" if f.source_page.isdigit() else f"{src}, {f.source_page}"
            figs.append((li, f.value, f.unit_multiplier or 1.0, f.currency, src))
        if figs:
            plan.locked_slots[i] = {"label": p.label, "figures": figs}
    return plan


def prompt_block(plan: HistoryPlan) -> str:
    """Tell the producer which year each historical_fs slot is and which
    figures are confirmed. Values are as reported (currency + unit given)."""
    lines = [
        "HISTORICAL PERIOD MAPPING (AUTHORITATIVE): the historical_fs arrays are oldest first; "
        + ", ".join(f"index {i} = {label or 'n/a'}" for i, label in enumerate(plan.slot_labels))
        + " (index 4 is FY-1, the base year for revenue_y0 and the other *_y0 values).",
    ]
    if plan.any_locked:
        lines.append(
            "CONFIRMED (LOCKED) HISTORICAL FIGURES — the analyst has confirmed these. Emit them EXACTLY in "
            "historical_fs (converted to the workpaper currency and unit, costs and liabilities negative); do "
            "NOT re-derive, restate or 'correct' them from the documents. The pipeline overwrites them anyway."
        )
        for i, slot in sorted(plan.locked_slots.items()):
            parts = []
            for li, value, mult, cur, _src in slot["figures"]:
                unit = "" if mult == 1 else (" '000" if mult == 1e3 else " m" if mult == 1e6 else f" ×{mult:g}")
                parts.append(f"{li.hist_key}={value:,.2f} {cur or ''}{unit}".strip())
            lines.append(f"  - {slot['label']} (index {i}): " + "; ".join(parts))
    return "\n".join(lines)


_Y0_FROM_HIST = {
    "revenue_y0": "revenue",
    "gross_profit_y0": "gross_profit",
    "opex_y0": "opex_total",
    "ebitda_y0": "ebitda",
    "ebit_y0": "ebit",
    "tax_y0": "tax_expense",
    "net_income_y0": "net_income",
}


def apply_plan(payload: dict, plan: HistoryPlan) -> list[str]:
    """Write every locked figure into payload.historical_fs (and the base-year
    *_y0 values when FY-1 is locked), converting currency and unit to the
    workpaper's. Returns notes for anything that could not be applied."""
    if not plan.any_locked:
        return []
    cu = payload.get("currency") or {}
    primary = cat.normalize_currency(cu.get("primary"))
    alt = cat.normalize_currency(cu.get("alt"))
    try:
        fx = float(cu.get("fx_rate_alt")) if cu.get("fx_rate_alt") not in (None, "") else None
    except (TypeError, ValueError):
        fx = None
    wp_mult = cat.unit_multiplier(cu.get("unit"))
    hist = payload.setdefault("historical_fs", {})
    notes: list[str] = []
    applied_labels: list[str] = []
    sources_used: set[str] = set()

    for idx, slot in sorted(plan.locked_slots.items()):
        applied = False
        for li, value, mult, cur, src in slot["figures"]:
            actual = value * mult
            if cur and primary and cur != primary:
                if alt == cur and fx:
                    actual = actual / fx
                else:
                    notes.append(f"{slot['label']} {li.label}: reported in {cur}, no {cur}→{primary} rate in the model — not applied")
                    continue
            wp = actual / (wp_mult or 1.0)
            if li.sign == "cost":
                wp = -abs(wp)
            series = hist.get(li.hist_key)
            if not isinstance(series, list):
                series = [None] * 5
            series = (series + [None] * 5)[:5]
            series[idx] = round(wp, 6)
            hist[li.hist_key] = series
            applied = True
            if src:
                sources_used.add(src)
        if applied:
            applied_labels.append(slot["label"])

    if 4 in plan.locked_slots:
        proj = payload.setdefault("projections", {})
        for y0_key, hist_key in _Y0_FROM_HIST.items():
            series = hist.get(hist_key)
            if isinstance(series, list) and len(series) == 5 and isinstance(series[4], (int, float)):
                proj[y0_key] = series[4]

    if applied_labels:
        sources = payload.setdefault("sources", {})
        detail = f"Confirmed (locked) historical figures for {', '.join(applied_labels)} applied verbatim"
        if sources_used:
            detail += f" from {'; '.join(sorted(sources_used))}"
        sources["historical_fs"] = {
            "source": "Audited financial statements (confirmed)",
            "detail": detail + ".",
            "notes": "Locked by the analyst; not re-derived on this run.",
        }
    return notes


async def confirmed_context_block(db: AsyncSession, company_id: uuid.UUID) -> str:
    """Markdown block of every locked period's figures, for report and chat
    prompts: these numbers win over anything re-read from the documents."""
    periods = sorted(
        (await db.execute(
            select(FinancialPeriod).where(FinancialPeriod.company_id == company_id, FinancialPeriod.locked.is_(True))
        )).scalars().all(),
        key=_period_sort_key,
    )
    periods = [p for p in periods if p.figures]
    if not periods:
        return ""
    keys: list[str] = []
    for li in cat.LINE_ITEMS:
        if any(f.line_item == li.key for p in periods for f in p.figures):
            keys.append(li.key)
    for p in periods:
        for f in p.figures:
            if f.line_item not in keys:
                keys.append(f.line_item)
    head = "| Line item | " + " | ".join(p.label for p in periods) + " |"
    sep = "|---|" + "---|" * len(periods)
    body = []
    for k in keys:
        cells = []
        for p in periods:
            f = next((x for x in p.figures if x.line_item == k), None)
            cells.append("" if f is None or f.value is None else f"{f.value:,.0f}")
        body.append(f"| {cat.item_for(k).label} | " + " | ".join(cells) + " |")
    units = sorted({f"{f.currency or ''} {f.unit or ''}".strip() for p in periods for f in p.figures} - {""})
    return (
        "## Confirmed historical figures (AUTHORITATIVE — locked by the analyst)\n"
        "Use these exact figures for these periods. Where a document shows a different number for a locked "
        "period, the locked figure stands.\n"
        + (f"Currency / unit as reported: {', '.join(units)}\n" if units else "")
        + "\n" + head + "\n" + sep + "\n" + "\n".join(body)
    )
