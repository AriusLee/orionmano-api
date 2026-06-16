"""Compile-knowledge-once layer: distill a company's extracted documents into
canonical markdown pages that downstream skills read instead of re-flattening
the raw extracted_data blob.

Per Karpathy's LLM Wiki gist: every report-generation skill currently re-derives
the same facts (revenue, equity, share count, FPI status) from the raw documents
on every call. That's both expensive (input tokens repeated × N calls) and
quality-eroding (each derivation is independent → cross-section contradictions).

Three starter pages, ordered by leverage:
- profile:        engagement metadata (name, jurisdiction, industry, fiscal year, currency)
- historical-fs:  5-year P&L + BS — feeds gap, DD, valuation
- cap-table:      shares outstanding, classes, top holders — feeds cap-structure analyses

Trigger: api/v1/documents.py::_extract_bg fires recompile_company() on every
extraction completion. Pages are versioned (history table), so audit trail holds.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.client_kb_page import ClientKbPage, ClientKbPageHistory
from app.models.company import Company
from app.models.document import Document
from app.services.ai.client import generate_text, DEEPSEEK_MODEL


# Slugs for the v1 starter set. Order matters — profile compiled first since
# the others may reference its outputs.
PAGE_SLUGS = ("profile", "historical-fs", "cap-table")


# ─── Per-page LLM prompts ────────────────────────────────────────────────────

_BASE_SYSTEM = (
    "You are a financial analyst at a US/Nasdaq IPO advisory firm. Your task is "
    "to distill the provided extracted-document content into a single canonical "
    "knowledge page in clean markdown.\n\n"
    "Rules (in priority order):\n"
    "1. Use ONLY the information present in the extracted documents below. Do "
    "not invent figures, dates, names, or jurisdictions.\n"
    "2. SOURCE AUTHORITY — when documents disagree on the SAME figure: the "
    "audited consolidated financial statements (the Consolidated Statement of "
    "Profit or Loss / Consolidated Balance Sheet found in a prospectus, draft "
    "registration statement / DRS / F-1 / S-1, or audited annual report — the "
    "\"F-pages\") are the PRIMARY, AUTHORITATIVE source. For every line item that "
    "APPEARS on the face of those consolidated statements (revenue, cost of "
    "sales, gross profit, other income, operating/admin expenses, operating "
    "profit, finance costs, profit before tax, tax, net income; and "
    "balance-sheet totals/subtotals), take the figure VERBATIM from the "
    "consolidated statements. Individual account leadsheets, breakdowns, trial "
    "balances, reconciliations and working-paper schedules must NEVER override "
    "those face figures, and you must never blend a leadsheet revenue with a "
    "consolidated gross profit.\n"
    "   HOWEVER — for line items that are NOT separately presented on the face "
    "of the consolidated statements but are needed for analysis (e.g. "
    "depreciation & amortization, breakdowns within cost of sales or operating "
    "expenses, and balance-sheet components such as receivables, payables, "
    "inventory, debt), you SHOULD populate them from the supporting "
    "leadsheets/schedules as SUPPLEMENTARY detail — provided they reconcile "
    "with (do not contradict) the consolidated subtotals. These supplementary "
    "lines fill gaps the face statements leave; they do not override anything. "
    "Do NOT mark such a line \"Not available\" merely because it is absent from "
    "the face statement when a supporting schedule provides it. Briefly cite the "
    "source schedule for supplementary lines.\n"
    "3. When a required field is not present, write \"Not available in current "
    "documents\" — never guess or default to industry norms.\n"
    "4. Numbers, currencies, and dates must match the authoritative source "
    "verbatim. Preserve the original currency and unit (USD'000 vs USD millions "
    "etc).\n"
    "5. Output ONLY the markdown body. No preamble, no code fences, no closing "
    "summary — just the page content starting with the H1.\n"
    "6. Be tight: tables for tabular data, short bullets for lists, no flowery "
    "prose.\n"
)


_PROFILE_USER_TEMPLATE = """Produce the **Company Profile** page using the markdown structure below. Fill each section from the extracted documents; mark "Not available in current documents" where data is missing.

```
# Company Profile

## Identity
- **Legal name:** ...
- **Trade / commercial name:** ... (omit if same as legal)
- **Country of incorporation:** ...
- **Registration / company number:** ...
- **Date of incorporation:** ...

## Industry
- **US classification (Damodaran industry):** ...
- **Global / sector classification:** ...
- **One-line business description:** ...

## Reporting & accounting
- **Reporting currency:** ...
- **Presentation unit:** ... (e.g. USD'000, USD millions, actual)
- **Fiscal year end:** ...
- **Accounting standard:** ... (IFRS / US GAAP / IFRS 9 + IFRS 13)

## Listing
- **Listing target:** ... (e.g. Nasdaq Global Select Market)
- **Issuer classification:** ... (Foreign Private Issuer / US domestic / not yet determined)
- **Auditor:** ... (firm name; PCAOB-registered Y/N)

## Key dates
- **Valuation date (most recent):** ...
- **Last full fiscal year:** ...
- **Most recent interim period:** ...
```

# Extracted documents

{documents_block}
"""


_HISTORICAL_FS_USER_TEMPLATE = """Produce the **Historical Financial Statements** page. Show full-period P&L and balance-sheet line items across every period present in the source documents. Periods on columns, line items on rows. State currency and unit clearly. Use markdown tables.

**AUTHORITATIVE SOURCE (read first):** If any document is a prospectus / DRS / F-1 / S-1 / audited annual report containing a Consolidated Statement of Profit or Loss and Consolidated Balance Sheet, take EVERY headline line item that appears on the face of those statements (revenue, cost of sales, gross profit, other income, operating expenses, operating profit, finance costs, profit before tax, tax, net income, and all balance-sheet totals) from THOSE consolidated statements. Do NOT substitute those face figures with leadsheet/working-paper numbers even when the leadsheets look more granular. The income statement MUST internally reconcile for each period: Revenue − Cost of sales = Gross profit, and Gross profit + Other income − Operating expenses − Finance costs ≈ Profit before tax. If your figures do not tie, you have mixed sources — re-anchor every line on the consolidated statements and use a single consistent source per period.

**TRANSCRIBE, DO NOT RECOMPUTE:** Copy every figure that appears on the face of the consolidated statement EXACTLY as printed. Do NOT recalculate, re-derive, or adjust any face figure — even to make subtotals tie. The reconciliation note above is a check that you have not MIXED sources, not a licence to compute your own numbers. If a value is printed on the statement, transcribe it verbatim.

**LINE-ITEM MAPPING:** Map the statement's "Profit from operation(s)" / "Operating profit" / "Profit from operating activities" verbatim to the **EBIT / Operating profit** row — this is the printed result BEFORE finance costs, and is DISTINCT from Profit before tax (which is AFTER finance costs). Do not put the Profit-before-tax figure in the EBIT row. Leave **EBITDA** as "Not available in current documents" unless the source prints an EBITDA figure — it is a derived metric computed downstream from EBIT + Depreciation & amortization, not something you should calculate here.

**SUPPLEMENTARY DETAIL (do fill these in):** For rows the consolidated statement does NOT itemize — especially **Depreciation & amortization** (often only in the cash-flow statement, PPE/ROU/lease leadsheets, or notes), EBITDA components, expense breakdowns, and balance-sheet components (receivables, payables, inventory, debt) — DO populate them from the supporting leadsheets/schedules or notes when present, and cite the source in parens. These must reconcile with the consolidated subtotals but they fill gaps the face statement leaves. Do not mark Depreciation & amortization "Not available" if a PPE/lease/depreciation schedule supplies it — downstream EBITDA and QoE analysis depend on it.

```
# Historical Financial Statements

**Currency:** ... | **Unit:** ... | **Periods covered:** ...

## Income statement

| Line item | <Period 1> | <Period 2> | <Period 3> | ... |
| --- | --- | --- | --- | --- |
| Revenue | | | | |
| Cost of sales | | | | |
| **Gross profit** | | | | |
| Other income / gains | | | | |
| Selling & distribution | | | | |
| Operating / G&A expenses | | | | |
| Impairments (subtotal) | | | | |
| **EBITDA** | | | | |
| Depreciation & amortization | | | | |
| **EBIT / Operating profit** | | | | |
| Finance costs | | | | |
| Other non-operating | | | | |
| **Profit before tax** | | | | |
| Tax expense | | | | |
| **Net income** | | | | |

## Balance sheet (period-end)

| Line item | <Period 1> | <Period 2> | <Period 3> | ... |
| --- | --- | --- | --- | --- |
| Cash & equivalents | | | | |
| Accounts receivable | | | | |
| Inventory | | | | |
| Other current assets | | | | |
| **Total current assets** | | | | |
| Property, plant & equipment | | | | |
| Intangibles | | | | |
| Other non-current assets | | | | |
| **Total assets** | | | | |
| Accounts payable | | | | |
| Short-term debt | | | | |
| Other current liabilities | | | | |
| **Total current liabilities** | | | | |
| Long-term debt | | | | |
| Other non-current liabilities | | | | |
| **Total liabilities** | | | | |
| Share capital | | | | |
| Retained earnings | | | | |
| **Total equity** | | | | |

## Notes
- (List any audit qualifications, going-concern flags, or material reclassifications visible in the source.)
- (Cite source document filenames in parens, e.g. "(KT FS for valuation.xlsx)")
```

If a period in the source has only P&L (no BS), show the P&L columns and leave the BS column blank for that period.

# Extracted documents

{documents_block}
"""


_CAP_TABLE_USER_TEMPLATE = """Produce the **Capitalization Table** page. Show share counts, classes, ownership, and dilutive instruments visible in the source documents.

```
# Capitalization Table

**As at:** ... (most recent date the source supports) | **Reporting currency:** ...

## Share counts
- **Authorized shares:** ...
- **Issued shares:** ...
- **Outstanding (basic):** ...
- **Outstanding (fully diluted):** ...

## Share classes

| Class | Authorized | Issued | Outstanding | Voting | Liquidation preference | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| ... | | | | | | |

## Shareholders (top by ownership)

| Shareholder | Class | Shares held | % of outstanding (basic) | % fully diluted | Notes |
| --- | --- | --- | --- | --- | --- |
| ... | | | | | |

## Dilutive instruments outstanding

| Instrument | Holder / pool | Underlying shares | Strike / conversion | Vesting / expiry | Notes |
| --- | --- | --- | --- | --- | --- |
| Options | | | | | |
| Warrants | | | | | |
| Convertibles | | | | | |
| SAFEs | | | | | |
| ESOP pool (granted) | | | | | |
| ESOP pool (unallocated) | | | | | |

## Notes
- (Flag any pre-IPO cleanup items: nominee holdings, founder loans, related-party balances, SHA terms with control implications.)
```

If the source documents do not contain a cap-table proper but mention shareholder names or share counts in passing, surface what's available and mark the rest "Not available in current documents".

# Extracted documents

{documents_block}
"""


_PROMPTS: dict[str, str] = {
    "profile": _PROFILE_USER_TEMPLATE,
    "historical-fs": _HISTORICAL_FS_USER_TEMPLATE,
    "cap-table": _CAP_TABLE_USER_TEMPLATE,
}


# ─── Doc context assembly ────────────────────────────────────────────────────

def _build_documents_block(docs: list[Document]) -> tuple[str, list[str]]:
    """Concatenate completed extractions into a single LLM-readable block.
    Returns (block_text, list_of_contributing_doc_ids)."""
    parts: list[str] = []
    contributing: list[str] = []
    for d in docs:
        if d.extraction_status != "completed":
            continue
        data = d.extracted_data or {}
        # Cap each doc's contribution to bound prompt size.
        rendered = json.dumps(data, ensure_ascii=False, indent=2)
        if len(rendered) > 12_000:
            rendered = rendered[:12_000] + "\n... [truncated]"
        parts.append(
            f"## Document: {d.filename}\n"
            f"- **id:** {d.id}\n"
            f"- **category:** {d.category or 'other'}\n"
            f"- **mime_type:** {d.mime_type or 'unknown'}\n\n"
            f"```json\n{rendered}\n```"
        )
        contributing.append(str(d.id))
    if not parts:
        return "(No completed document extractions for this company yet.)", []
    return "\n\n---\n\n".join(parts), contributing


# ─── Single-page compile ─────────────────────────────────────────────────────

async def _compile_one_page(
    *,
    slug: str,
    company_id: uuid.UUID,
    company_name: str,
    documents_block: str,
    contributing_doc_ids: list[str],
) -> dict[str, Any] | None:
    user_prompt = _PROMPTS[slug].format(documents_block=documents_block)
    try:
        body = (await generate_text(
            system_prompt=_BASE_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=4096,
            skill=f"kb_compile:{slug}",
            company_id=company_id,
        )).strip()
    except Exception as e:
        return {"slug": slug, "error": f"{type(e).__name__}: {str(e)[:200]}"}

    if not body:
        return {"slug": slug, "error": "empty response"}

    return {
        "slug": slug,
        "content": body,
        "source_doc_ids": contributing_doc_ids,
        "model": DEEPSEEK_MODEL,
    }


# ─── Public orchestrator ─────────────────────────────────────────────────────

async def recompile_company(company_id: uuid.UUID) -> dict[str, Any]:
    """Recompile every kb page for a company. Designed to be fired-and-forgotten
    after a document extraction completes — failures don't cascade.

    Returns a summary dict for callers that want to inspect (e.g. tests)."""
    async with async_session() as db:
        company = (await db.execute(
            select(Company).where(Company.id == company_id)
        )).scalar_one_or_none()
        if company is None:
            return {"company_id": str(company_id), "error": "company not found"}

        docs = list((await db.execute(
            select(Document).where(Document.company_id == company_id)
        )).scalars().all())

        documents_block, contributing = _build_documents_block(docs)
        if not contributing:
            return {"company_id": str(company_id), "error": "no completed extractions"}

    # LLM calls in parallel — bounded by N=len(PAGE_SLUGS) which is small (3)
    results = await asyncio.gather(*[
        _compile_one_page(
            slug=slug,
            company_id=company_id,
            company_name=company.name,
            documents_block=documents_block,
            contributing_doc_ids=contributing,
        )
        for slug in PAGE_SLUGS
    ])

    # Persist each successful result (overwrite + history snapshot)
    written: list[str] = []
    errors: list[dict[str, str]] = []
    async with async_session() as db:
        for r in results:
            if r is None or "error" in r:
                if r:
                    errors.append({"slug": r["slug"], "error": r["error"]})
                continue
            await _upsert_page(
                db,
                company_id=company_id,
                slug=r["slug"],
                content=r["content"],
                source_doc_ids=r["source_doc_ids"],
                model=r["model"],
            )
            written.append(r["slug"])
        await db.commit()

    return {
        "company_id": str(company_id),
        "pages_written": written,
        "errors": errors,
        "source_doc_count": len(contributing),
    }


async def _upsert_page(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    slug: str,
    content: str,
    source_doc_ids: list[str],
    model: str,
) -> None:
    """Insert or overwrite the (company_id, slug) page. On overwrite, snapshots
    the prior version into ClientKbPageHistory for audit."""
    existing = (await db.execute(
        select(ClientKbPage).where(
            ClientKbPage.company_id == company_id,
            ClientKbPage.slug == slug,
        )
    )).scalar_one_or_none()

    if existing is None:
        db.add(ClientKbPage(
            company_id=company_id,
            slug=slug,
            content=content,
            source_doc_ids=source_doc_ids,
            model=model,
            version=1,
        ))
        return

    # Snapshot prior version then overwrite in place
    db.add(ClientKbPageHistory(
        page_id=existing.id,
        company_id=existing.company_id,
        slug=existing.slug,
        content=existing.content,
        source_doc_ids=existing.source_doc_ids,
        model=existing.model,
        version=existing.version,
    ))
    existing.content = content
    existing.source_doc_ids = source_doc_ids
    existing.model = model
    existing.version = (existing.version or 1) + 1
