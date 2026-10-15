"""Market Data Supported report (Eric 2026-10, item 4).

For one valuation version, check each key assumption against live market data
found with Claude's web search tool, and keep what was found as
MarketEvidence rows: an assessment (supported / partially / not supported /
insufficient data), the market range, a short finding, and every source with
URL, publisher and date. Then generate the valuation report in its
"market_supported" variant, which adds a Market Data Support section and a
sources appendix built from these rows.

The existing DuckDuckGo search (services/ai/web_search.py, cached 90 days)
stays for the industry report; this uses live search because the point is
current, citable evidence.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.company import Company
from app.models.market_evidence import MarketEvidence
from app.models.report import Report
from app.models.valuation_version import ValuationVersion
from app.services.valuation_model import model_io, versions

logger = logging.getLogger(__name__)

_CONCURRENCY = 3
_MAX_SEARCHES = 5
_tasks: set[asyncio.Task] = set()

ASSESSMENTS = ("supported", "partially_supported", "not_supported", "insufficient_data")


def _pct(v: Any) -> str:
    return f"{v * 100:.2f}%" if isinstance(v, (int, float)) else "—"


def _array(inputs: dict, path: tuple[str, ...]) -> list:
    node: Any = inputs
    for p in path:
        node = node.get(p) if isinstance(node, dict) else None
    return node if isinstance(node, list) else []


def _series_display(vals: list) -> str:
    nums = [v for v in vals if isinstance(v, (int, float))]
    if not nums:
        return "—"
    return ", ".join(f"Y{i + 1} {v * 100:.1f}%" for i, v in enumerate(vals) if isinstance(v, (int, float)))


@dataclass(frozen=True)
class Assumption:
    key: str
    label: str
    source_keys: tuple[str, ...]  # keys in inputs.sources holding the model's stated basis
    guidance: str
    value: Callable[[dict], tuple[float | None, str]]


def _param(key: str) -> Callable[[dict], tuple[float | None, str]]:
    def get(inputs: dict) -> tuple[float | None, str]:
        v = model_io.param_value(inputs, key)
        return v, model_io.format_param(key, v)
    return get


def _series(path: tuple[str, ...]) -> Callable[[dict], tuple[float | None, str]]:
    def get(inputs: dict) -> tuple[float | None, str]:
        vals = _array(inputs, path)
        nums = [v for v in vals if isinstance(v, (int, float))]
        return (sum(nums) / len(nums) if nums else None), _series_display(vals)
    return get


ASSUMPTIONS: tuple[Assumption, ...] = (
    Assumption("revenue_growth", "Revenue growth (Y1–Y5)", ("revenue_growth_y1", "revenue_growth"),
               "Industry and market growth forecasts (CAGR) for the company's sector and geography from research houses, "
               "industry bodies or listed peers' guidance; and peers' recent revenue growth.",
               _series(("projections", "revenue_growth"))),
    Assumption("gross_margin", "Gross margin (Y1–Y5)", ("gross_margin_y1", "gross_margin"),
               "Gross margins of listed peers and the sector (latest annual reports, sector averages).",
               _series(("projections", "gross_margin"))),
    Assumption("terminal_growth_rate", "Terminal growth rate", ("terminal_growth_rate",),
               "Long-run nominal GDP growth and inflation expectations for the operating jurisdiction (IMF WEO, central bank, consensus).",
               _param("terminal_growth_rate")),
    Assumption("risk_free_rate", "Risk-free rate", ("risk_free_rate",),
               "Government bond yield matching the currency and horizon at the valuation date (e.g. US 10-year Treasury for USD).",
               _param("risk_free_rate")),
    Assumption("equity_risk_premium", "Equity risk premium", ("equity_risk_premium",),
               "Damodaran implied ERP, Kroll recommended ERP, or other published ERP surveys near the valuation date.",
               _param("equity_risk_premium")),
    Assumption("country_risk_premium", "Country risk premium", ("country_risk_premium",),
               "Damodaran country risk premium for the operating country, or sovereign default spreads.",
               _param("country_risk_premium")),
    Assumption("unlevered_beta_pm", "Unlevered beta", ("unlevered_beta_per_mgmt", "unlevered_beta_pm"),
               "Damodaran industry unlevered betas for the sector (US / Global / Asia) and listed peers' betas.",
               _param("unlevered_beta_pm")),
    Assumption("size_premium_pm", "Size premium", ("size_premium_per_mgmt", "size_premium_pm"),
               "Kroll (Duff & Phelps) CRSP size premia by decile for a company of this market capitalisation.",
               _param("size_premium_pm")),
    Assumption("specific_risk_premium_pm", "Company-specific risk premium", ("specific_risk_premium_per_mgmt", "specific_risk_premium_pm"),
               "Published practitioner ranges for company-specific risk premia in private-company / pre-IPO valuations.",
               _param("specific_risk_premium_pm")),
    Assumption("pretax_cost_of_debt_pm", "Pre-tax cost of debt", ("pretax_cost_of_debt_pm", "pretax_cost_of_debt"),
               "Bank lending rates / corporate bond yields for similar credit quality in the borrowing currency at the valuation date.",
               _param("pretax_cost_of_debt_pm")),
    Assumption("dlom_pct", "Discount for lack of marketability", ("dlom_pct",),
               "DLOM studies — restricted-stock and pre-IPO studies, option-based models — and the ranges they report.",
               _param("dlom_pct")),
    Assumption("dloc_pct", "Discount for lack of control", ("dloc_pct",),
               "Control premium studies (e.g. FactSet Mergerstat) and the implied minority discounts.",
               _param("dloc_pct")),
)
BY_KEY = {a.key: a for a in ASSUMPTIONS}

_SYSTEM = """You are a valuation research analyst. Check ONE assumption of a company valuation against current market data, using web search.

Search for primary or reputable sources (central banks, government statistics, IMF, Damodaran/NYU Stern, Kroll, listed companies' filings, recognised research houses). Prefer data dated as close as possible to the valuation date; always record each source's date. Do not rely on memory for figures — every figure you state must come from a source you found.

Then judge the value the model uses:
- "supported": within the range the market data indicates
- "partially_supported": defensible but at the edge of, or only partly covered by, the evidence
- "not_supported": outside what the evidence supports
- "insufficient_data": you could not find adequate evidence

Return ONLY a JSON object, no prose before or after:
{
  "assessment": "supported | partially_supported | not_supported | insufficient_data",
  "market_range": "the range or point the evidence indicates, e.g. 4.2%–4.6%",
  "finding": "2-4 sentences: what the evidence shows and how the model's value compares",
  "sources": [{"url": "...", "title": "...", "publisher": "...", "published_date": "YYYY-MM-DD or as precise as known", "quote": "the figure or sentence relied on, under 30 words"}]
}"""


def _stated_basis(inputs: dict, a: Assumption) -> str:
    sources = inputs.get("sources") or {}
    for k in a.source_keys:
        v = sources.get(k)
        if isinstance(v, dict):
            return " · ".join(str(v.get(x)) for x in ("source", "detail", "rationale") if v.get(x))
        if v:
            return str(v)
    return "not stated"


def _citations_from(response: Any) -> list[dict[str, Any]]:
    """URLs the search actually returned, as a fallback when the JSON omits sources."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        content = getattr(block, "content", None)
        if not isinstance(content, list):
            continue
        for r in content:
            url = getattr(r, "url", None)
            if url and url not in seen:
                seen.add(url)
                out.append({"url": url, "title": getattr(r, "title", None), "publisher": None,
                            "published_date": getattr(r, "page_age", None), "quote": None})
    return out[:6]


async def _research(evidence_id: uuid.UUID, context: str, inputs: dict) -> None:
    async with async_session() as db:
        ev = (await db.execute(select(MarketEvidence).where(MarketEvidence.id == evidence_id))).scalar_one_or_none()
        if ev is None:
            return
        a = BY_KEY[ev.assumption_key]
        value_display = ev.value_display
    user = (
        f"{context}\n\n# Assumption to check\n{a.label}: {value_display}\n"
        f"The model's stated basis: {_stated_basis(inputs, a)}\n\n# Where to look\n{a.guidance}"
    )
    try:
        parsed, response = await model_io.ask_claude_json(
            _SYSTEM, user, max_tokens=6000,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": _MAX_SEARCHES}],
        )
        if not isinstance(parsed, dict):
            # The research ran but the verdict wasn't clean JSON (cut off, or
            # prose around it). Turn the notes into the JSON without searching again.
            notes = "\n".join(
                b.text for b in getattr(response, "content", []) or []
                if getattr(b, "type", None) == "text" and getattr(b, "text", None)
            )
            if notes.strip():
                parsed, _ = await model_io.ask_claude_json(
                    _SYSTEM,
                    f"{user}\n\n# Your research notes\n{notes[-20000:]}\n\n"
                    "Using ONLY these notes (no new figures), output the JSON object now.",
                    max_tokens=3000,
                )
        if not isinstance(parsed, dict):
            raise ValueError(f"no JSON verdict returned (stop reason: {getattr(response, 'stop_reason', '?')})")
        assessment = str(parsed.get("assessment") or "").strip().lower().replace(" ", "_")
        if assessment not in ASSESSMENTS:
            assessment = "insufficient_data"
        sources = [s for s in (parsed.get("sources") or []) if isinstance(s, dict) and s.get("url")]
        if not sources:
            sources = _citations_from(response)
        async with async_session() as db:
            ev = (await db.execute(select(MarketEvidence).where(MarketEvidence.id == evidence_id))).scalar_one()
            ev.assessment = assessment
            ev.market_range = str(parsed.get("market_range") or "")[:200] or None
            ev.finding = str(parsed.get("finding") or "").strip() or None
            ev.sources = sources[:8]
            ev.error = None
            ev.searched_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as e:
        logger.warning("market evidence for %s failed: %s", evidence_id, e)
        async with async_session() as db:
            ev = (await db.execute(select(MarketEvidence).where(MarketEvidence.id == evidence_id))).scalar_one()
            ev.assessment = "failed"
            ev.error = f"{type(e).__name__}: {str(e)[:300]}"
            await db.commit()


async def _context(db: AsyncSession, version: ValuationVersion) -> str:
    company = (await db.execute(select(Company).where(Company.id == version.company_id))).scalar_one()
    eng = (version.inputs or {}).get("engagement") or {}
    return (
        "# Company\n"
        f"{eng.get('company_name') or company.name} — industry: {eng.get('company_industry_us') or company.industry or 'n/a'}; "
        f"country: {eng.get('company_country') or company.country}; listing target: {eng.get('exchange_platform') or company.target_exchange or 'n/a'}; "
        f"valuation date: {eng.get('valuation_date') or 'n/a'}; currency: {version.currency or 'n/a'}.\n"
        f"Business: {(company.description or '')[:600]}"
    )


async def run_bg(version_id: uuid.UUID, user_id: uuid.UUID | None, keys: list[str] | None, make_report: bool) -> None:
    """Research every assumption (or `keys`) of a version, then (optionally)
    generate the Market Data Supported report for it."""
    async with async_session() as db:
        version = (await db.execute(select(ValuationVersion).where(ValuationVersion.id == version_id))).scalar_one_or_none()
        if version is None:
            return
        rows = (await db.execute(select(MarketEvidence).where(MarketEvidence.version_id == version_id))).scalars().all()
        targets = [r for r in rows if r.assessment == "pending" and (keys is None or r.assumption_key in keys)]
        context = await _context(db, version)
        inputs = version.inputs
        ids = [r.id for r in targets]
        company_id = version.company_id

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def one(eid: uuid.UUID) -> None:
        async with sem:
            await _research(eid, context, inputs)

    await asyncio.gather(*(one(i) for i in ids))

    if make_report:
        await create_report(company_id, version_id, user_id)


async def start(db: AsyncSession, company_id: uuid.UUID, version_id: uuid.UUID | None, user_id: uuid.UUID | None,
                keys: list[str] | None = None, make_report: bool = True) -> ValuationVersion:
    """Queue research for a version (default: the active one). Re-running an
    assumption replaces its earlier evidence."""
    version = (await versions.get_version(db, company_id, version_id)) if version_id else await versions.active_version(db, company_id)
    if version is None:
        raise ValueError("Generate a valuation workpaper first")
    wanted = [a for a in ASSUMPTIONS if keys is None or a.key in keys]
    await db.execute(delete(MarketEvidence).where(
        MarketEvidence.version_id == version.id,
        MarketEvidence.assumption_key.in_([a.key for a in wanted]),
    ))
    for a in wanted:
        value, display = a.value(version.inputs or {})
        if value is None and display == "—":
            continue
        db.add(MarketEvidence(
            company_id=company_id,
            version_id=version.id,
            assumption_key=a.key,
            label=a.label,
            value_used=value,
            value_display=display,
            assessment="pending",
        ))
    await db.commit()
    task = asyncio.create_task(run_bg(version.id, user_id, [a.key for a in wanted] if keys else None, make_report))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return version


async def create_report(company_id: uuid.UUID, version_id: uuid.UUID, user_id: uuid.UUID | None) -> uuid.UUID:
    async with async_session() as db:
        company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one()
        report = Report(
            company_id=company_id,
            report_type="valuation_report",
            tier=company.report_tier or "standard",
            title=f"{company.name} — Valuation Report (Market Data Supported)",
            status="pending",
            created_by=user_id,
            valuation_version_id=version_id,
            variant="market_supported",
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        rid = report.id
    from app.services.report.generator import generate_report_bg
    async with async_session() as db:
        await generate_report_bg(db, company_id, "valuation_report", rid)
    return rid


async def evidence_for(db: AsyncSession, version_id: uuid.UUID) -> list[MarketEvidence]:
    rows = (await db.execute(select(MarketEvidence).where(MarketEvidence.version_id == version_id))).scalars().all()
    order = {a.key: i for i, a in enumerate(ASSUMPTIONS)}
    return sorted(rows, key=lambda r: order.get(r.assumption_key, 99))


def evidence_dict(r: MarketEvidence) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "assumption_key": r.assumption_key,
        "label": r.label,
        "value_used": r.value_used,
        "value_display": r.value_display,
        "assessment": r.assessment,
        "market_range": r.market_range,
        "finding": r.finding,
        "sources": r.sources or [],
        "searched_at": r.searched_at.isoformat() if r.searched_at else None,
        "error": r.error,
    }


ASSESSMENT_LABELS = {
    "supported": "Supported",
    "partially_supported": "Partially supported",
    "not_supported": "Not supported",
    "insufficient_data": "Insufficient data",
    "pending": "Pending",
    "failed": "Search failed",
}


async def report_context_block(db: AsyncSession, version_id: uuid.UUID) -> str:
    """The evidence as a context block for the market_supported report."""
    rows = [r for r in await evidence_for(db, version_id) if r.assessment not in ("pending", "failed")]
    if not rows:
        return ""
    parts = ["\n\n## Market Data Evidence (AUTHORITATIVE for the Market Data Support section — gathered by live web search)"]
    n = 0
    for r in rows:
        parts.append(
            f"\n### {r.label}\n- Value used in the model: {r.value_display}\n"
            f"- Assessment: {ASSESSMENT_LABELS.get(r.assessment, r.assessment)}\n"
            f"- Market range: {r.market_range or 'n/a'}\n- Finding: {r.finding or ''}"
        )
        for s in r.sources or []:
            n += 1
            parts.append(
                f"  - Source S{n}: {s.get('publisher') or s.get('title') or ''} — \"{s.get('title') or ''}\" "
                f"({s.get('published_date') or 'date n/a'}) {s.get('url')}"
                + (f" — \"{s.get('quote')}\"" if s.get("quote") else "")
            )
    return "\n".join(parts)
