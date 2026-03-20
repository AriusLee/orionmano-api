"""Post-extraction intelligence: auto-fill company profile, risk flags, executive summary."""

import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.document import Document
from app.services.ai.client import generate_text


async def auto_fill_company(db: AsyncSession, company_id: UUID) -> dict:
    """After extraction, auto-fill company fields from extracted data."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        return {}

    doc_result = await db.execute(
        select(Document).where(
            Document.company_id == company_id,
            Document.extraction_status == "completed",
        )
    )
    documents = list(doc_result.scalars().all())
    if not documents:
        return {}

    # Merge all extracted company_info
    merged = {}
    for doc in documents:
        if not doc.extracted_data:
            continue
        info = doc.extracted_data.get("company_info", {})
        if isinstance(info, dict):
            for k, v in info.items():
                if v and not merged.get(k):
                    merged[k] = v

    # Auto-fill empty fields
    updated = {}
    if not company.legal_name and merged.get("legal_name"):
        company.legal_name = merged["legal_name"]
        updated["legal_name"] = merged["legal_name"]
    if not company.industry and merged.get("industry"):
        company.industry = merged["industry"]
        updated["industry"] = merged["industry"]
    if not company.description and merged.get("description"):
        company.description = merged["description"]
        updated["description"] = merged["description"]
    if not company.website and merged.get("website"):
        company.website = merged["website"]
        updated["website"] = merged["website"]
    if not company.registration_number and merged.get("registration_number"):
        company.registration_number = merged["registration_number"]
        updated["registration_number"] = merged["registration_number"]

    if updated:
        await db.commit()

    return updated


def detect_risk_flags(extracted_data: dict) -> list[dict]:
    """Detect risk flags from extracted financial data. Returns list of {severity, title, detail}."""
    flags = []
    fin = extracted_data.get("financial_data", {})
    if not fin or not isinstance(fin, dict):
        return flags

    # Helper to get latest value from period dict
    def latest(d):
        if not isinstance(d, dict):
            return None
        vals = [(k, v) for k, v in d.items() if v is not None and isinstance(v, (int, float))]
        if not vals:
            return None
        vals.sort(key=lambda x: x[0], reverse=True)
        return vals[0][1]

    def prev(d):
        if not isinstance(d, dict):
            return None
        vals = [(k, v) for k, v in d.items() if v is not None and isinstance(v, (int, float))]
        if len(vals) < 2:
            return None
        vals.sort(key=lambda x: x[0], reverse=True)
        return vals[1][1]

    # Check income statement
    is_data = fin.get("income_statement", {})
    if isinstance(is_data, dict):
        revenue = latest(is_data.get("revenue", {}))
        prev_rev = prev(is_data.get("revenue", {}))
        net_income = latest(is_data.get("net_income", {}))
        gross_profit = latest(is_data.get("gross_profit", {}))

        if net_income is not None and net_income < 0:
            flags.append({"severity": "high", "title": "Net Loss", "detail": f"Company reported a net loss of {net_income:,.0f}"})

        if revenue and prev_rev and prev_rev > 0:
            growth = (revenue - prev_rev) / abs(prev_rev)
            if growth < -0.1:
                flags.append({"severity": "high", "title": "Revenue Decline", "detail": f"Revenue declined {growth*100:.1f}% year-over-year"})
            elif growth > 1.0:
                flags.append({"severity": "medium", "title": "Rapid Revenue Growth", "detail": f"Revenue grew {growth*100:.0f}% — sustainability to verify"})

        if revenue and gross_profit and revenue > 0:
            gm = gross_profit / revenue
            if gm < 0.2:
                flags.append({"severity": "medium", "title": "Low Gross Margin", "detail": f"Gross margin at {gm*100:.1f}% — below 20% threshold"})

    # Check balance sheet
    bs = fin.get("balance_sheet", {})
    if isinstance(bs, dict):
        total_assets = latest(bs.get("total_assets", {}))
        total_liabilities = latest(bs.get("total_liabilities", {}))
        current_assets = latest(bs.get("current_assets", {}))
        current_liabilities = latest(bs.get("current_liabilities", {}))
        cash = latest(bs.get("cash", {}))

        if total_assets and total_liabilities and total_assets > 0:
            de = total_liabilities / (total_assets - total_liabilities) if total_assets > total_liabilities else 99
            if de > 2.0:
                flags.append({"severity": "high", "title": "High Leverage", "detail": f"Debt-to-equity ratio of {de:.1f}x exceeds 2.0x threshold"})

        if current_assets and current_liabilities and current_liabilities != 0:
            cr = current_assets / abs(current_liabilities)
            if cr < 1.0:
                flags.append({"severity": "high", "title": "Liquidity Risk", "detail": f"Current ratio of {cr:.2f} — below 1.0, negative working capital"})

        if total_assets and cash and total_assets > 0:
            cash_pct = cash / total_assets
            if cash_pct < 0.05:
                flags.append({"severity": "medium", "title": "Low Cash Position", "detail": f"Cash is only {cash_pct*100:.1f}% of total assets"})

    # Check cash flow
    cf = fin.get("cash_flow", {})
    if isinstance(cf, dict):
        operating = latest(cf.get("operating", {}))
        if operating is not None and operating < 0:
            flags.append({"severity": "high", "title": "Negative Operating Cash Flow", "detail": f"Operating cash flow is {operating:,.0f}"})

    # Check key findings from extraction
    findings = extracted_data.get("key_findings", [])
    if isinstance(findings, list):
        for f in findings[:3]:
            if isinstance(f, str) and any(w in f.lower() for w in ["risk", "concern", "weak", "negative", "decline", "loss"]):
                flags.append({"severity": "medium", "title": "Noted Finding", "detail": f})

    return flags


async def generate_executive_summary(db: AsyncSession, company_id: UUID) -> str:
    """Generate a brief AI executive summary from all extracted data."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        return ""

    doc_result = await db.execute(
        select(Document).where(
            Document.company_id == company_id,
            Document.extraction_status == "completed",
        )
    )
    documents = list(doc_result.scalars().all())
    if not documents:
        return ""

    # Build context
    context_parts = [f"Company: {company.name}"]
    if company.industry:
        context_parts.append(f"Industry: {company.industry}")
    if company.country:
        context_parts.append(f"Country: {company.country}")
    if company.description:
        context_parts.append(f"Description: {company.description}")

    for doc in documents:
        if doc.extracted_data:
            context_parts.append(f"\n--- {doc.filename} ---")
            context_parts.append(json.dumps(doc.extracted_data, default=str)[:2000])

    context = "\n".join(context_parts)

    summary = await generate_text(
        system_prompt="You are a senior financial advisor. Write a concise 3-4 sentence executive summary of this company based on the available data. Be specific with numbers. Professional tone.",
        user_prompt=f"Write an executive summary:\n\n{context}",
        max_tokens=300,
    )
    return summary
