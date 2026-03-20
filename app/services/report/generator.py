import os
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.document import Document
from app.models.report import Report, ReportSection
from app.services.ai.client import generate_text


REPORT_TITLES = {
    "sales_deck": "Sales Deck",
    "kickoff_deck": "Kick-off Meeting Deck",
    "industry_report": "Industry Expert Report",
    "dd_report": "Due Diligence Report",
    "valuation_report": "Valuation Report",
    "teaser": "Company Teaser",
    "company_deck": "Company Deck",
}

# Tier-based section definitions: { report_type: { tier: [(key, title)] } }
REPORT_SECTIONS = {
    "industry_report": {
        "essential": [
            ("executive_summary", "Executive Summary"),
            ("industry_overview", "Industry Overview"),
            ("recommendations", "Strategic Recommendations"),
        ],
        "standard": [
            ("scope_of_services", "Scope of Services"),
            ("executive_summary", "Executive Summary"),
            ("industry_overview", "Industry Overview and Market Context"),
            ("market_size", "Global Market Size and Trajectory"),
            ("growth_drivers", "Market Growth Drivers"),
            ("competitive_landscape", "Competitive Landscape"),
            ("industry_trends", "Industry Trends"),
            ("recommendations", "Strategic Recommendations"),
            ("conclusion", "Conclusion"),
        ],
        "premium": [
            ("scope_of_services", "Scope of Services"),
            ("executive_summary", "Executive Summary"),
            ("industry_overview", "Industry Overview and Market Context"),
            ("market_size", "Global Market Size and Trajectory"),
            ("geographic_distribution", "Geographic Market Distribution"),
            ("growth_drivers", "Market Growth Drivers and Structural Tailwinds"),
            ("segment_deep_dive", "Market Segment Deep Dive"),
            ("competitive_landscape", "Competitive Market Structure and Dynamics"),
            ("industry_trends", "Industry Trends and Evolution"),
            ("challenges", "Market Challenges and Headwinds"),
            ("outlook", "Market Outlook and Future Opportunities"),
            ("recommendations", "Strategic Recommendations"),
            ("conclusion", "Conclusion"),
        ],
    },
    "dd_report": {
        "essential": [
            ("executive_summary", "Executive Summary"),
            ("business_overview", "Business Overview"),
            ("key_findings", "Key Findings and Suggestions"),
        ],
        "standard": [
            ("scope", "Scope of Engagement"),
            ("engagement_overview", "Engagement Overview"),
            ("business_overview", "Business Overview"),
            ("financials_bs", "Key Financials — Balance Sheet"),
            ("financials_is", "Key Financials — Income Statement"),
            ("financials_cf", "Key Financials — Cash Flow Statement"),
            ("internal_controls", "Internal Control Evaluation"),
            ("key_findings", "Key Findings and Suggestions"),
        ],
        "premium": [
            ("scope", "Scope of Engagement"),
            ("engagement_overview", "Engagement Overview"),
            ("business_overview", "Business Overview"),
            ("financials_bs", "Key Financials — Balance Sheet"),
            ("financials_is", "Key Financials — Income Statement"),
            ("financials_cf", "Key Financials — Cash Flow Statement"),
            ("financials_focus", "Key Financials — Focus Areas"),
            ("internal_controls", "Internal Control Evaluation"),
            ("legal_proceedings", "Legal Proceedings and Prior Fundraising"),
            ("taxation", "Taxation"),
            ("key_findings", "Key Findings and Suggestions"),
        ],
    },
    "valuation_report": {
        "essential": [
            ("value_summary", "Value Summary"),
            ("dcf_summary", "DCF Analysis Summary"),
            ("conclusion", "Valuation Conclusion"),
        ],
        "standard": [
            ("executive_summary", "Executive Summary"),
            ("financial_projections", "Financial Projection Highlights"),
            ("dcf_analysis", "DCF Analysis — FCFF & Present Value"),
            ("wacc", "Discount Rate / WACC Derivation"),
            ("coco_benchmarking", "Comparable Company Benchmarking"),
            ("implied_multiples", "Implied Multiples Cross-Check"),
            ("ev_equity_bridge", "EV-to-Equity Bridge (Net Debt, DLOM, DLOC)"),
            ("sensitivity", "Sensitivity Analysis"),
            ("assumptions", "Key Assumptions and Limitations"),
        ],
        "premium": [
            ("executive_summary", "Executive Summary"),
            ("company_overview", "Company & Historical Financials Overview"),
            ("financial_projections", "Financial Projection Highlights"),
            ("dcf_analysis", "DCF Analysis — FCFF & Present Value"),
            ("terminal_value", "Terminal Value Analysis"),
            ("wacc", "Discount Rate / WACC Build-Up"),
            ("coco_selection", "Comparable Company Selection & Rationale"),
            ("coco_benchmarking", "CoCo Multiples & Fundamentals Benchmarking"),
            ("implied_multiples", "Implied Multiples Cross-Check"),
            ("ev_equity_bridge", "EV-to-Equity Bridge (Net Debt, Surplus Assets, DLOM, DLOC)"),
            ("backtesting", "Back-Testing — Projections vs Actuals"),
            ("sensitivity", "Sensitivity Analysis (WACC vs Terminal Growth)"),
            ("parallel_analysis", "Parallel / Independent Analysis"),
            ("assumptions", "Key Assumptions and Limitations"),
        ],
    },
    "sales_deck": {
        "standard": [
            ("about_orionmano", "About Orionmano"),
            ("understanding_business", "Understanding Your Business"),
            ("opportunity", "Your Opportunity"),
            ("proposed_scope", "Proposed Scope of Services"),
            ("approach", "Our Approach"),
            ("deliverables", "Deliverables"),
            ("timeline", "Engagement Timeline"),
            ("next_steps", "Next Steps"),
        ],
    },
    "kickoff_deck": {
        "standard": [
            ("engagement_overview", "Engagement Overview"),
            ("scope_of_services", "Scope of Services"),
            ("company_overview", "Company at a Glance"),
            ("engagement_phases", "Engagement Phases"),
            ("information_requirements", "Information Requirements"),
            ("deliverables_summary", "Deliverables Summary"),
            ("next_steps", "Immediate Next Steps"),
        ],
    },
    "teaser": {
        "essential": [
            ("company_snapshot", "Company Snapshot"),
            ("investment_highlights", "Investment Highlights"),
            ("transaction_overview", "Transaction Overview"),
        ],
        "standard": [
            ("company_snapshot", "Company Snapshot"),
            ("investment_highlights", "Investment Highlights"),
            ("key_financials", "Key Financial Metrics"),
            ("revenue_breakdown", "Revenue Breakdown"),
            ("market_opportunity", "Market Opportunity"),
            ("competitive_advantages", "Competitive Advantages"),
            ("transaction_overview", "Transaction Overview"),
        ],
        "premium": [
            ("company_snapshot", "Company Snapshot"),
            ("investment_highlights", "Investment Highlights"),
            ("key_financials", "Key Financial Metrics"),
            ("revenue_breakdown", "Revenue Breakdown"),
            ("market_opportunity", "Market Opportunity"),
            ("competitive_advantages", "Competitive Advantages"),
            ("management_team", "Management Team"),
            ("growth_strategy", "Growth Strategy"),
            ("transaction_overview", "Transaction Overview"),
        ],
    },
}


def _get_sections(report_type: str, tier: str) -> list[tuple[str, str]]:
    type_sections = REPORT_SECTIONS.get(report_type, {})
    if tier in type_sections:
        return type_sections[tier]
    return type_sections.get("standard", [])


def _load_template(report_type: str) -> str:
    template_map = {
        "sales_deck": "01-sales-deck.md",
        "kickoff_deck": "02-kickoff-deck.md",
        "industry_report": "03-industry-report.md",
        "dd_report": "04-dd-report.md",
        "valuation_report": "05-valuation-report.md",
        "teaser": "06-company-teaser.md",
        "company_deck": "07-company-deck.md",
    }
    kb_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "knowledge-base", "05-report-templates", template_map.get(report_type, "")
    )
    try:
        with open(kb_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _build_company_context(company: Company, documents: list[Document]) -> str:
    parts = [f"Company: {company.name}"]
    if company.industry:
        parts.append(f"Industry: {company.industry}")
    if company.sub_industry:
        parts.append(f"Sub-industry: {company.sub_industry}")
    if company.country:
        parts.append(f"Country: {company.country}")
    if company.description:
        parts.append(f"Description: {company.description}")
    if company.website:
        parts.append(f"Website: {company.website}")
    if company.engagement_type:
        parts.append(f"Engagement: {company.engagement_type}")
    if company.target_exchange:
        parts.append(f"Target Exchange: {company.target_exchange}")

    for doc in documents:
        if doc.extracted_data and doc.extraction_status == "completed":
            parts.append(f"\n--- Extracted from {doc.filename} ---")
            parts.append(json.dumps(doc.extracted_data, indent=1, default=str)[:3000])

    return "\n".join(parts)


TIER_INSTRUCTIONS = {
    "essential": "Write concisely. 2-3 pages total. Focus on key findings only.",
    "standard": "Write detailed analysis. 5-8 pages total. Include data-driven insights.",
    "premium": "Write comprehensive deep-dive. 10-15 pages total. Include benchmarks, risk analysis, and detailed action plans.",
}


async def generate_report_bg(
    db: AsyncSession,
    company_id: UUID,
    report_type: str,
    report_id: UUID,
) -> None:
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        return

    try:
        comp_result = await db.execute(select(Company).where(Company.id == company_id))
        company = comp_result.scalar_one_or_none()
        if not company:
            report.status = "failed"
            report.error_message = "Company not found"
            await db.commit()
            return

        doc_result = await db.execute(select(Document).where(Document.company_id == company_id))
        documents = list(doc_result.scalars().all())

        tier = report.tier or "standard"
        report.title = f"{company.name} — {REPORT_TITLES.get(report_type, report_type)}"
        report.status = "generating"
        await db.commit()

        template = _load_template(report_type)
        company_context = _build_company_context(company, documents)
        sections = _get_sections(report_type, tier)
        tier_instruction = TIER_INSTRUCTIONS.get(tier, TIER_INSTRUCTIONS["standard"])

        # Load supplementary knowledge for valuation reports
        extra_knowledge = ""
        if report_type == "valuation_report":
            val_ref_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..", "knowledge-base", "04-valuation", "valuation-model-reference.md"
            )
            try:
                with open(val_ref_path, "r") as f:
                    extra_knowledge = f"\n\n## Orionmano Valuation Model Reference\n{f.read()[:3000]}"
            except FileNotFoundError:
                pass

        system_prompt = f"""You are a senior financial advisor at Orionmano Assurance Services (Hong Kong).
Generate professional report content. Be concise, data-driven, and specific.
Use markdown formatting. Reference actual company data when available.
Follow IFRS 9 and IFRS 13 standards for fair value analysis.

Tier: {tier.upper()} — {tier_instruction}

## Report Template Reference
{template[:2000]}{extra_knowledge}

## Company Data
{company_context}"""

        max_tokens_per_section = {"essential": 800, "standard": 1500, "premium": 2500}.get(tier, 1500)

        for i, (section_key, section_title) in enumerate(sections):
            report.progress_message = f"Generating {i+1}/{len(sections)}: {section_title}"
            await db.commit()

            content = await generate_text(
                system_prompt=system_prompt,
                user_prompt=f'Write the "{section_title}" section. Be professional and concise. Markdown only. No preamble.',
                max_tokens=max_tokens_per_section,
            )

            section = ReportSection(
                report_id=report.id,
                section_key=section_key,
                section_title=section_title,
                content=content,
                sort_order=i,
            )
            db.add(section)
            await db.commit()

        report.status = "draft"
        report.progress_message = None

    except Exception as e:
        report.status = "failed"
        report.error_message = str(e)

    await db.commit()
