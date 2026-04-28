import asyncio
import os
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.document import Document
from app.models.report import Report, ReportSection
from app.services.ai.client import generate_text
from app.services.ai.web_search import web_search, format_search_results


REPORT_TITLES = {
    "gap_analysis": "Gap Analysis",
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
    "gap_analysis": {
        "essential": [
            ("listing_path", "Assumptions & Listing Path"),
            ("financial_highlights", "Financial Position & Gap Assessment"),
            ("equity_bridge", "Financial Bridge to Listing Threshold"),
            ("scorecard", "IPO Readiness Scorecard"),
            ("gaps_recommendations", "Critical Gaps & Priority Actions"),
            ("conclusion", "Conclusion & Readiness Assessment"),
        ],
        "standard": [
            ("listing_path", "Assumptions & Listing Path"),
            ("fpi_regime", "FPI Status & Reporting Regime"),
            ("nasdaq_requirements", "Nasdaq Listing Requirements — Financial Standards"),
            ("financial_highlights", "Financial Analysis — Financial Highlights"),
            ("other_metrics", "Financial Analysis — Other Metrics"),
            ("equity_bridge", "Financial Bridge to Listing Threshold"),
            ("entity_structure", "Entity Structure & Cap Table Assessment"),
            ("audit_readiness", "Audit & Accounting Readiness"),
            ("scorecard", "IPO Readiness Scorecard"),
            ("financial_gaps", "Financial Gaps & Recommendations"),
            ("governance_gaps", "Governance Gaps & Recommendations"),
            ("reporting_gaps", "Reporting & Disclosure Gaps"),
            ("legal_compliance", "Legal & Regulatory Compliance Map"),
            ("industry_gaps", "Industry-Specific Gaps"),
            ("transaction_feasibility", "Transaction Feasibility & Peer Positioning"),
            ("roadmap", "Implementation Roadmap & Timeline"),
            ("conclusion", "Conclusion & Readiness Assessment"),
        ],
        "premium": [
            ("listing_path", "Assumptions & Listing Path"),
            ("fpi_regime", "FPI Status & Reporting Regime"),
            ("nasdaq_requirements", "Nasdaq Listing Requirements — Financial Standards"),
            ("financial_highlights", "Financial Analysis — Financial Highlights"),
            ("other_metrics", "Financial Analysis — Other Metrics"),
            ("equity_bridge", "Financial Bridge to Listing Threshold"),
            ("entity_structure", "Entity Structure & Cap Table Assessment"),
            ("cap_table_analysis", "Cap Table Listability & Pre-IPO Cleanup"),
            ("audit_readiness", "Audit & Accounting Readiness"),
            ("scorecard", "IPO Readiness Scorecard"),
            ("financial_gaps", "Financial Gaps & Recommendations"),
            ("governance_gaps", "Governance Gaps & Recommendations"),
            ("reporting_gaps", "Reporting & Disclosure Gaps"),
            ("legal_compliance", "Legal & Regulatory Compliance Map"),
            ("industry_gaps", "Industry-Specific Gaps"),
            ("peer_comps", "Peer Comparables & Valuation Reality Check"),
            ("transaction_feasibility", "Transaction Feasibility & Bankability Analysis"),
            ("roadmap", "Implementation Roadmap & Timeline"),
            ("conclusion", "Conclusion & Readiness Assessment"),
        ],
    },
    "industry_report": {
        "essential": [
            ("sources_of_information", "Sources of Information"),
            ("executive_summary", "Executive Summary"),
            ("industry_overview", "Industry Overview"),
            ("competitive_landscape", "Competitive Landscape"),
            ("strategic_recommendations", "Strategic Recommendations"),
        ],
        "standard": [
            ("sources_of_information", "Sources of Information"),
            ("executive_summary", "Executive Summary"),
            ("industry_definition_scope", "Industry Definition and Scope"),
            ("value_chain", "Industry Value Chain"),
            ("market_size_trajectory", "Market Size and Growth Trajectory"),
            ("growth_drivers", "Market Growth Drivers"),
            ("competitive_landscape", "Competitive Landscape"),
            ("industry_trends", "Industry Trends"),
            ("entry_barriers", "Key Entry Barriers"),
            ("market_outlook", "Market Outlook"),
            ("strategic_recommendations", "Strategic Recommendations"),
        ],
        "premium": [
            ("sources_of_information", "Sources of Information"),
            ("executive_summary", "Executive Summary"),
            ("industry_definition_scope", "Industry Definition and Scope"),
            ("value_chain", "Industry Value Chain — Upstream, Midstream, Downstream"),
            ("market_size_trajectory", "Market Size and Growth Trajectory"),
            ("geographic_distribution", "Geographic Market Distribution"),
            ("market_segments", "Market Segment Deep Dive"),
            ("growth_drivers", "Market Growth Drivers and Structural Tailwinds"),
            ("competitive_landscape_matrix", "Competitive Landscape — Player Archetypes and Capability Matrix"),
            ("competitive_benchmarking", "Competitive Landscape — Financial Benchmarking of Named Peers"),
            ("industry_trends", "Industry Trends and Evolution"),
            ("entry_barriers", "Key Entry Barriers"),
            ("challenges_headwinds", "Market Challenges and Headwinds"),
            ("market_outlook", "Market Outlook and Future Opportunities"),
            ("strategic_recommendations", "Strategic Recommendations"),
        ],
    },
    "dd_report": {
        "essential": [
            ("executive_summary", "Executive Summary"),
            ("scope_basis", "Scope, Basis and Limitations"),
            ("qoe_bridge", "Quality of Earnings — Adjusted EBITDA Bridge"),
            ("net_debt_nwc", "Net Debt + Working Capital"),
            ("key_findings", "Key Findings and Suggestions"),
        ],
        "standard": [
            ("executive_summary", "Executive Summary"),
            ("scope_basis", "Scope, Basis and Limitations"),
            ("business_overview", "Business Overview"),
            ("qoe_bridge", "Quality of Earnings — Adjusted EBITDA Bridge"),
            ("revenue_quality", "Revenue Quality — Concentration, Cohorts, Recognition"),
            ("working_capital", "Working Capital — Trend, Days Metrics, Peg"),
            ("net_debt", "Net Debt + Debt-Like Items"),
            ("balance_sheet_review", "Balance Sheet Review"),
            ("internal_controls", "Internal Control Evaluation"),
            ("key_findings", "Key Findings and Suggestions"),
        ],
        "premium": [
            ("executive_summary", "Executive Summary"),
            ("scope_basis", "Scope, Basis and Limitations"),
            ("business_overview", "Business Overview"),
            ("qoe_bridge", "Quality of Earnings — Adjusted EBITDA Bridge"),
            ("revenue_quality", "Revenue Quality — Concentration, Cohorts, Recognition"),
            ("cost_margin", "Cost & Margin Analysis"),
            ("working_capital", "Working Capital — Trend, Days Metrics, Peg"),
            ("net_debt", "Net Debt + Debt-Like Items"),
            ("proof_of_cash", "Proof of Cash"),
            ("balance_sheet_review", "Balance Sheet Review"),
            ("capex", "Capex — Maintenance vs Growth"),
            ("accounting_policies", "Accounting Policies — Judgment Areas"),
            ("taxation", "Taxation"),
            ("internal_controls", "Internal Control Evaluation"),
            ("commitments_contingencies", "Commitments and Contingencies"),
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
        "gap_analysis": "00-gap-analysis.md",
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


def _build_source_registry(documents: list[Document], web_results: list[dict] | None = None) -> tuple[str, str]:
    """Build a numbered source registry and return (registry_text, references_section).

    Returns:
        registry_text: Source list for the system prompt so the AI knows how to cite.
        references_section: Formatted "Sources & References" markdown section for the report.
    """
    sources = []
    ref_lines = []
    idx = 1

    # Document sources
    for doc in documents:
        if doc.extracted_data and doc.extraction_status == "completed":
            doc_type = ""
            if isinstance(doc.extracted_data, dict):
                doc_type = doc.extracted_data.get("document_type", "")
            label = f"{doc.filename}"
            if doc_type:
                label += f" ({doc_type})"
            sources.append(f"[{idx}] {label}")
            ref_lines.append(f"{idx}. {label} — Provided by company management")
            idx += 1

    # Web search sources
    if web_results:
        for r in web_results:
            if r.get("url"):
                title = r.get("title", "Web source")
                url = r["url"]
                sources.append(f"[{idx}] {title} — {url}")
                ref_lines.append(f"{idx}. {title} — {url}")
                idx += 1

    registry_text = ""
    if sources:
        registry_text = "## Available Sources (use these citation numbers)\n" + "\n".join(sources)

    references_section = ""
    if ref_lines:
        references_section = "## Sources & References\n\n" + "\n".join(ref_lines)

    return registry_text, references_section


TIER_INSTRUCTIONS = {
    "essential": "Write concisely. 2-3 pages total. Focus on key findings only.",
    "standard": "Write detailed analysis. 5-8 pages total. Include data-driven insights.",
    "premium": "Write comprehensive deep-dive. 10-15 pages total. Include benchmarks, risk analysis, and detailed action plans.",
}


# ──────────────────────────────────────────────────────────────
# Gap Analysis — dedicated prompt & per-section instructions
# ──────────────────────────────────────────────────────────────

def _build_gap_analysis_prompt(
    company, documents, tier, tier_instruction, template,
    gap_knowledge, web_context, company_context,
) -> str:
    """Build a specialised system prompt for gap analysis reports."""
    return f"""You are a senior financial advisor at Orionmano Assurance Services (Hong Kong), specialising in Nasdaq IPO advisory and pre-IPO gap analysis for Asia-Pacific companies.

## YOUR ROLE
You are writing a **transaction-grade gap analysis** — a document that will be presented to prospects and used for advisory decision-making. This is NOT an AI research memo or narrative summary. It must read like a professional advisory memo that a senior banker or securities lawyer would take seriously.

## CRITICAL RULES

### 1. DATA CONSISTENCY (MANDATORY)
Before writing ANY section, establish a single set of canonical numbers from the available data and use them consistently throughout the ENTIRE report:
- Pick ONE shareholders' equity figure and use it everywhere
- Pick ONE exchange rate and use it everywhere
- Pick ONE revenue figure and use it everywhere
- Pick ONE net income/loss figure and use it everywhere
- If data conflicts exist in the source materials, pick the most recent audited figure and note the discrepancy once
- NEVER let the same metric appear with different values on different pages

### 2. NO INLINE CITATIONS
Do NOT use numbered inline citations like [1], [2], [3]. Instead, state the basis naturally:
- "Based on FY20XX audited financial statements..."
- "Per management representations..."
- "According to Nasdaq Listing Rule 5505..."
- "Based on publicly available information..."

### 3. INFORMATION GAP HANDLING
When data is not available (e.g., no cap table provided, no org chart, no audit reports):
- Do NOT fabricate or assume data
- Clearly flag it as **"Information Required"** with a description of what is needed
- Explain WHY this information matters for the gap analysis
- Provide the analytical framework so the section is useful even without the data
- Example: "**Information Required:** Full cap table with all share classes, convertible instruments, SAFEs, warrants, and ESOP details. Without this, public float feasibility and pre-IPO restructuring needs cannot be assessed."

### 4. TIMELINE AWARENESS
- The report date is today's date — all action timelines must be FORWARD-LOOKING from today
- Never write timelines that reference dates in the past
- Use relative timeframes (e.g., "Within 3-6 months", "Pre-filing") rather than specific quarter/year if unsure of the engagement start date

### 5. FPI-AWARE ANALYSIS
When analysing a non-US company for Nasdaq listing, always consider Foreign Private Issuer (FPI) status:
- FPI can use IFRS as issued by IASB (not required to convert to US GAAP). SEC explicitly allows this.
- FPI has home country practice exemptions for many Nasdaq corporate governance rules (but NOT for audit committee independence)
- Reg FD does NOT apply to FPIs — do not recommend establishing a Reg FD policy for FPI companies
- FPIs file on 20-F (annual) and 6-K (interim), NOT 10-K/10-Q/8-K
- FPIs are not required to file quarterly earnings reports in the typical 10-Q format
- Always state whether the company likely qualifies as FPI and what implications that has

### 6. LISTING PATH SPECIFICITY
Do not assume "Nasdaq Capital Market + F-1" by default. The report must explicitly address:
- Which Nasdaq tier (Capital Market / Global Market / Global Select Market) and why
- Whether F-1 (FPI) or S-1 (domestic) registration path
- Whether existing entity can list directly or needs topco restructure / redomicile / holdco insertion
- IPO mechanism: firm commitment, best efforts, direct listing, or de-SPAC optionality
- Note: Even if a company meets quantitative standards, Nasdaq retains discretion to impose additional conditions or deny listing based on investor protection concerns

### 7. TRANSACTION-GRADE DEPTH
Each gap must include:
- **Current State** — what exists today, with specific data points where available
- **Requirement** — the specific Nasdaq rule, SEC regulation, or market standard
- **Gap** — the specific shortfall, quantified where possible
- **Required Action** — concrete, actionable steps (not generic advice)
- **Severity** — Critical / High / Medium / Low
- **Owner** — who is responsible (e.g., Company / Legal Counsel / Auditor / Underwriter)

### 8. WORKPLAN FORMAT
The conclusion workplan must be structured by workstreams, not generic bullet points. Each workstream should specify: current state, red flags, required actions, owner, estimated effort, priority (must-have vs good-to-have), and timing (pre-filing / filing / pre-roadshow).

Tier: {tier.upper()} — {tier_instruction}

## Report Template Reference
{template[:3000]}{gap_knowledge}
{web_context}

## Company Data
{company_context}"""


GAP_SECTION_INSTRUCTIONS = {
    "listing_path": """Write the Listing Path Assumptions section. This is the MOST IMPORTANT section — it sets the foundation for the entire analysis. Cover:
1. Recommended Nasdaq tier (Capital Market / Global Market / Global Select) with rationale based on the company's financials
2. Registration path: F-1 (Foreign Private Issuer) vs S-1 — determine if the company qualifies as FPI
3. Listing vehicle: Can the existing entity list directly, or is a topco restructure / redomicile / holdco insertion needed?
4. IPO mechanism: Firm commitment IPO, best efforts, direct listing, or de-SPAC — recommend with rationale
5. Key assumption dependencies: What must be true for this path to work?
If entity structure information is not available, state what's needed and provide the framework for analysis.""",

    "fpi_regime": """Write the FPI Status & Reporting Regime section. Determine if the company likely qualifies as a Foreign Private Issuer under SEC rules and the implications:
1. FPI qualification test (ownership test + business contacts test)
2. If FPI: can use IFRS (no US GAAP conversion required), files 20-F/6-K (not 10-K/10-Q/8-K), Reg FD does NOT apply
3. Corporate governance exemptions available under home country practice (but audit committee independence still required)
4. Interim reporting differences — FPIs are not in the typical quarterly 10-Q cycle
5. Implications for disclosure architecture, compliance costs, and timeline
If company jurisdiction suggests FPI status, explicitly state which requirements can be relaxed vs which are non-negotiable.""",

    "nasdaq_requirements": """Write the Nasdaq Listing Requirements table comparing all three financial standards (Shareholders' Capital, Market Capitalization, Net Income) against the company's current position. Include exchange rate. Identify which standard is most achievable.""",

    "financial_highlights": """Write the Financial Highlights section with a comparison table. Use ONLY the canonical numbers established for this report. Show YoY changes where multi-year data is available. Include: Revenue, Gross Profit, Gross Margin, Operating Income/Loss, Net Income/Loss, Total Assets, Shareholders' Equity, Cash & Equivalents, Monthly Burn Rate (if loss-making), Cash Runway.""",

    "other_metrics": """Write the Other Financial Metrics section covering operational and health indicators: Gross Profit Margin trend, Operating Margin trend, Monthly Operating Burn, Cash Runway, Revenue Concentration (top customer), User/Customer metrics if available, Market Context. Flag concerning patterns with severity ratings.""",

    "equity_bridge": """Write the Financial Bridge to Listing Threshold section. This is CRITICAL — build a step-by-step bridge:
1. Current shareholders' equity (single canonical figure)
2. + Planned fundraising (Series A or other)
3. - Estimated IPO costs and fees (USD 1.5-2.5M typical)
4. - Debt cleanup / restructuring adjustments
5. +/- Operating results between now and listing
6. = Pro forma equity at listing
7. Compare against Nasdaq threshold — is there still a gap?
If equity figures are unclear or conflicting, note the discrepancy and show the bridge under best-case and worst-case scenarios. Do NOT let the reader think one fundraising round automatically closes the gap without showing the math.""",

    "entity_structure": """Write the Entity Structure & Cap Table Assessment. Cover:
1. Ultimate listing entity — who/what will be the listed vehicle?
2. Operating subsidiaries and their jurisdictions
3. Nominee / trust / layered holding structures
4. Dormant entities / historical liabilities
5. Founder loans / shareholder advances / intercompany balances
6. VIE structures / revenue pass-through / principal-agent issues
7. Where are key licenses, contracts, IP held — operating sub or parent/founder?
If org chart or entity information is not provided, flag as Information Required and explain why this analysis is critical for listing feasibility.""",

    "cap_table_analysis": """Write the Cap Table Listability & Pre-IPO Cleanup section. Cover:
1. Fully diluted share count and ownership breakdown
2. Convertible notes / SAFEs / preference shares / warrants / ESOP
3. Liquidation preferences / anti-dilution / ratchet provisions
4. Super voting / non-standard voting rights
5. Founder / investor / related party concentration
6. Public float feasibility — can a meaningful float be created?
7. Pre-IPO actions needed: share consolidation, reverse split, class simplification, debt-to-equity conversion
If cap table is not provided, flag as Information Required and describe exactly what data is needed.""",

    "audit_readiness": """Write the Audit & Accounting Readiness section. This must go DEEPER than "get a PCAOB audit". Cover:
1. Can 2-3 years of audited FS be obtained? Any going concern / qualified opinion risk?
2. IFRS vs US GAAP path (considering FPI status)
3. Revenue recognition complexity — identify specific issues for this company's business model
4. Deferred revenue / wallet balances / user credits / prepaid items
5. Token / digital asset / rewards liability accounting (if applicable)
6. Principal vs agent determination for marketplace/platform models
7. Related-party balances — can they be cleaned?
8. Tax / SST / transfer pricing / withholding tax exposure
9. Consolidation basis — any issues?
10. Internal controls readiness for SOX 302/404 compliance""",

    "scorecard": """Write the IPO Readiness Scorecard section. This is a visual summary of the company's readiness across all dimensions.

Create a table with the following format:

| Dimension | Rating | Key Finding | Critical Actions |
|-----------|--------|-------------|-----------------|

**Dimensions to rate (all required):**
1. **Financial Position** — equity, profitability, cash runway vs Nasdaq thresholds
2. **Corporate Structure** — entity structure, cap table, listing vehicle readiness
3. **Audit & Accounting** — PCAOB readiness, GAAP/IFRS compliance, internal controls
4. **Governance & Board** — independence, committees, policies
5. **Legal & Regulatory** — licensing, compliance, IP, pending issues
6. **Reporting & Disclosure** — SEC filing readiness, IR function, KPI framework
7. **Market Readiness** — peer positioning, valuation defensibility, institutional narrative
8. **Transaction Feasibility** — underwriter appetite, deal size viability, public float

**Rating scale (use these exact labels and emoji):**
- 🟢 **Ready** — meets requirements, no material gaps
- 🟡 **Conditional** — achievable with specific remediation within 6 months
- 🔴 **Not Ready** — significant gaps requiring major work (>6 months) or fundamental restructuring
- ⚪ **Information Required** — cannot assess without additional data

After the table, provide:
1. **Overall Readiness Rating:** Ready / Conditionally Ready / Not Ready
2. **Estimated Time to IPO Readiness:** X-Y months from today
3. **Estimated Total Remediation Cost:** USD X-Y range (sum of all workstream costs)
4. **Go/No-Go Recommendation:** Clear judgment with conditions""",

    "financial_gaps": """Write the Financial Gaps & Recommendations section in a structured table format. For each gap include: Metric, Company's Current Position, Nasdaq Requirement, Gap Assessment (with severity: CRITICAL/HIGH/MEDIUM), Strategic Recommendations with specific action items, and **Estimated Remediation Cost** (provide a USD range, e.g., "USD 50K-100K for audit conversion" or "USD 0 — internal process change"). Every recommendation must have a cost estimate, even if it's "$0 — internal effort" or "TBD — dependent on scope".""",

    "governance_gaps": """Write the Governance Gaps & Recommendations section. For each gap use the format: Gap title, Current State, Nasdaq Requirement (cite specific rule numbers like Rule 5605, 5630), Risk if not addressed, Required Action with timeline and owner, and **Estimated Cost** (e.g., independent director compensation: USD 30K-60K/year per director, D&O insurance: USD 50K-200K/year, committee setup: USD 10K-30K legal fees).""",

    "reporting_gaps": """Write the Reporting & Disclosure Gaps section considering FPI status. Cover: Financial reporting standards conversion, PCAOB audit requirements, SEC filing obligations (20-F/6-K for FPI, not 10-K/10-Q), internal controls over financial reporting (ICFR/COSO), governance disclosure, KPI and non-financial metric disclosure requirements, risk factor disclosure requirements. For each gap, include **Estimated Cost** (e.g., PCAOB audit: USD 200K-500K, GAAP/IFRS conversion: USD 100K-300K, SOX readiness: USD 150K-400K, IR function setup: USD 50K-150K/year).""",

    "legal_compliance": """Write the Legal & Regulatory Compliance Map section. This must be SPECIFIC to the company's industry and jurisdictions, not generic. Cover:
1. Industry-specific licensing requirements per jurisdiction
2. Regulatory boundaries (e.g., gaming/betting, financial services, crypto/token regulations)
3. AML/KYC/data privacy/cybersecurity obligations
4. IP ownership completeness (code, brand, content, software)
5. Key contract dependencies (publishers, payment channels, app stores)
6. Pending disputes / threatened claims / founder legal history
Present as a compliance checklist with status (Compliant / Gap / Information Required) per item. For each gap, include **Estimated Cost** (e.g., legal opinion: USD 20K-50K, licensing application: USD 10K-50K, IP registration: USD 5K-20K, regulatory counsel retainer: USD 50K-150K).""",

    "industry_gaps": """Write the Industry-Specific Gaps section. These must be unique to this company — not generic industry commentary. Each gap must reference specific company data or clearly flag where data is missing. Focus on what would concern an institutional investor or underwriter about THIS specific company. For each gap, include **Estimated Remediation Cost** with a USD range.""",

    "peer_comps": """Write the Peer Comparables & Valuation Reality Check section. Cover:
1. Identify 5-8 listed peer companies (Nasdaq/NYSE/global) in similar sectors
2. Compare: revenue scale, gross margin, EBITDA profile, EV/Revenue multiples
3. How would investors categorize this company's story?
4. Is the target market cap / valuation realistic given peer trading levels?
5. What valuation range is defensible for underwriting purposes?
If insufficient data, provide the peer identification framework and note what financial data is needed for a proper comparison.""",

    "transaction_feasibility": """Write the Transaction Feasibility & Bankability Analysis section. This is what the client really cares about — not just "can we theoretically list" but "will this deal actually work":
1. Public float requirement and feasibility
2. Minimum viable raise size for underwriter interest
3. Post-fees working capital — does the company have 12-18 months runway after IPO costs?
4. Is the deal too small / too niche / too hard to sell to institutional investors?
5. Prospectus narrative strength — is there enough institutional story?
6. Auditor willingness (will a PCAOB firm sign off?)
7. Legal counsel appetite (will a reputable securities firm take this?)
This section distinguishes listing eligibility from transaction feasibility.""",

    "roadmap": """Write the Implementation Roadmap & Timeline section. This combines the workplan with a visual timeline.

### Part 1: Workstream Summary Table

Create a table with ALL workstreams:

| # | Workstream | Status | Severity | Est. Cost (USD) | Owner | Timeline | Phase |
|---|-----------|--------|----------|-----------------|-------|----------|-------|

**Workstreams (all required):**
1. Corporate Restructuring (topco, holdco, redomicile)
2. Capital Raising & Equity Bridge
3. Audit & Accounting Conversion (PCAOB, GAAP/IFRS)
4. Internal Controls & SOX Readiness
5. Board & Governance Setup
6. Legal & Regulatory Cleanup
7. Cap Table Cleanup & Simplification
8. Financial Systems & Close Process
9. IPO Narrative & Investor Materials
10. Transaction Team Assembly (underwriter, counsel, auditor)

**Status:** 🟢 On Track / 🟡 Action Needed / 🔴 Critical / ⚪ Not Started
**Phase:** Immediate / Pre-filing / Filing / Pre-roadshow

### Part 2: Gantt-Style Timeline

Create a TEXT-BASED Gantt chart showing all workstreams across a timeline. Use this format:

```
Phase:        | IMMEDIATE  | PRE-FILING    | FILING      | PRE-ROADSHOW |
Timeline:     | Month 1-3  | Month 4-8     | Month 9-12  | Month 13-15  |
─────────────────────────────────────────────────────────────────────────
Restructuring |████████████|               |             |              |
Cap Raise     |████████████|███████████████|             |              |
Audit/PCAOB   |            |███████████████|█████████████|              |
SOX/Controls  |            |███████████████|█████████████|              |
Governance    |████████████|███████████████|             |              |
Legal/Reg     |████████████|███████████████|             |              |
Cap Table     |████████████|               |             |              |
Fin Systems   |            |███████████████|█████████████|              |
IPO Materials |            |               |█████████████|██████████████|
Deal Team     |            |███████████████|█████████████|██████████████|
```

Adjust the bars based on the company's actual situation. Show dependencies (e.g., "Audit cannot start until Restructuring is complete").

### Part 3: Cost Summary

| Category | Estimated Range (USD) |
|----------|----------------------|
| Advisory & Consulting | $XXK - $XXK |
| Legal (Securities + Corporate) | $XXK - $XXK |
| Audit (PCAOB + SOX) | $XXK - $XXK |
| Governance (Directors, D&O) | $XXK - $XXK |
| Regulatory & Licensing | $XXK - $XXK |
| IPO Transaction Costs | $XXK - $XXK |
| **Total Estimated Cost** | **$X.XM - $X.XM** |

### Part 4: Critical Path & Dependencies

List the 3-5 items that are on the CRITICAL PATH — if any of these slip, the entire IPO timeline shifts. Show dependencies between workstreams.""",

    "conclusion": """Write the Conclusion & Readiness Assessment. Structure as:
1. Strengths — what makes the IPO story credible
2. Critical blockers — the 3-5 issues that MUST be resolved before filing
3. Overall readiness rating: Ready / Conditionally Ready / Not Ready (with rationale)
4. Recommended next steps (numbered, prioritized, with owners)
5. Realistic timeline estimate for IPO readiness given identified gaps
Be direct and honest — this is for decision-making, not marketing.""",
}


# Sections that must run first (they establish canonical data for everything else)
GAP_SEQUENTIAL_SECTIONS = {
    "listing_path", "fpi_regime", "nasdaq_requirements",
    "financial_highlights", "other_metrics", "equity_bridge",
}

# Sections that benefit from deepseek-reasoner (chain-of-thought reasoning)
# These involve complex financial math, multi-step logic, or judgment calls
GAP_REASONER_SECTIONS = {
    "equity_bridge",        # multi-step financial bridge math
    "cap_table_analysis",   # complex structural assessment
    "audit_readiness",      # deep accounting analysis
    "scorecard",            # multi-dimension judgment + go/no-go recommendation
    "peer_comps",           # valuation cross-checks and comparables
    "transaction_feasibility",  # multi-factor feasibility judgment
    "roadmap",              # cost aggregation + dependency analysis + timeline
}

# Max concurrent API calls (DeepSeek rate-limits aggressively on free/low tiers)
MAX_CONCURRENT = 2


# ──────────────────────────────────────────────────────────────
# DD Report — Transaction-grade FDD prompt
# ──────────────────────────────────────────────────────────────

def _build_dd_prompt(
    company, documents, tier, tier_instruction, template,
    company_context,
) -> str:
    """Build a transaction-grade system prompt for due diligence reports.

    Modeled on _build_gap_analysis_prompt — the DD report must pass the
    "would a senior banker / IC take this seriously?" test, not the
    "does this sound like a research memo?" test.
    """
    return f"""You are a senior transaction services partner at Orionmano Assurance Services (Hong Kong-based), specialising in Nasdaq IPO advisory and pre-IPO financial due diligence for Asia-Pacific companies.

## YOUR ROLE
You are writing a **transaction-grade Independent Financial Due Diligence Report** for an underwriter, audit committee, or investment committee in connection with a Nasdaq IPO (Form S-1 / F-1) or pre-IPO private placement. This is NOT an AI research memo. It must read like a Big 4 / FTI / A&M FDD report that a senior banker or IC would take seriously and act upon.

## QUALITY BAR — THE 10 MARKERS

Top-tier FDD is distinguished from "research memo" output by these markers. Apply them where the data permits; flag as Information Required where it does not.

1. **Trial-balance level analysis** — when TB is available, rebuild the income statement bottom-up at month-end granularity. When only audited annuals are available, say so and flag the loss of analytical depth.
2. **Monthly trending** — annual numbers hide everything (seasonality, channel stuffing, run-rate inflections). Always prefer monthly.
3. **GL-level investigation of unusual entries** — surface manual journal entries, period-end adjustments, large round-numbered postings.
4. **Tie-outs to source documents** — every adjustment cites a source artefact (invoice, contract, board minutes, payroll register, bank confirmation).
5. **Sensitivity tables** — quantify uncertainty: Adjusted EBITDA at ±5/10%, NWC peg at three seasonality assumptions, net debt under contested treatments.
6. **Customer / SKU / geography deep-dives** — when revenue concentration data exists, name the top 5/10/20 customers and analyse each.
7. **Accounting policy section** discussing judgment areas — revenue recognition, capitalisation, depreciable lives, lease classification, deferred tax.
8. **Proof of cash** — bank statements tied to revenue and EBITDA over 12+ months when bank data is available.
9. **Adjustments rejected with rationale** — a bridge that accepts every management add-back is unsigned by the diligence team. Reject or modify with explicit one-line reasons (insufficient documentation, recurring in nature, double-counted, fails 2-quarter run-rate threshold).
10. **Forward-looking pivot** — close each analytical section by mapping the historical observation to forward-period implications.

## CRITICAL RULES

### 1. DATA CONSISTENCY (MANDATORY)
Before writing ANY section, establish a single set of canonical numbers and use them throughout the entire report:
- Pick ONE revenue figure and use it everywhere
- Pick ONE EBITDA figure (reported) and ONE Adjusted EBITDA figure
- Pick ONE net debt figure and ONE NWC figure at the latest balance sheet date
- Pick ONE FX rate and use it everywhere; state the rate and the as-of date in the basis section
- If source materials conflict, pick the most recent audited figure and note the discrepancy ONCE in the scope/basis section
- NEVER let the same metric appear with different values on different pages

### 2. NO INLINE CITATIONS
Do NOT use numbered inline citations like [1], [2], [3]. Do NOT use `[^n]` footnote syntax. Do NOT use `<cite/>` tags. State the basis naturally:
- "Based on FY2024 audited consolidated income statement..."
- "Per the trial balance dated 2025-12-31..."
- "Per management representations on 2026-MM-DD..."
- "Per the bank confirmation dated 2026-MM-DD..."
- "Per the customer master file extract dated 2026-MM-DD..."

### 3. INFORMATION REQUIRED PATTERN
When data is unavailable (no trial balance, no monthly accounts, no customer master, no bank statements):
- Do NOT fabricate or assume data
- Clearly flag as **"Information Required:"** with one sentence on what is needed and why it is material
- Provide the analytical framework so the section is still useful
- Example: "**Information Required:** Customer-level revenue export for the trailing 24 months. Without this, top-N concentration, cohort retention, and pricing×volume decomposition cannot be computed."

### 4. FORWARD-LOOKING TIMELINE
The report date is today. All recommended actions and timelines must be forward-looking from today. Never write timelines that reference past dates as future actions.

### 5. NASDAQ-ALIGNED REGULATORY PERIMETER
- Reference Nasdaq Listing Rules (5505/5605/5630/etc.), SEC requirements (Reg S-X, Reg S-K, F-1/S-1, 20-F/6-K), PCAOB audit standards, US GAAP / IFRS-as-issued-by-IASB
- Do NOT reference HKEX, HKSIR, SEHK, Bursa Malaysia, or any other non-US listing regime as the regulatory perimeter
- For non-US issuers, consider FPI (Foreign Private Issuer) status implications: IFRS acceptance, 20-F/6-K filing, Reg FD inapplicability, audit committee independence still required
- Where the issuer prepares under MFRS or local GAAP, flag the US GAAP / IFRS reconciliation that will be required for SEC filing — this is operationally relevant for DD scope

### 6. THE QoE BRIDGE IS THE CENTERPIECE
The Quality of Earnings section produces a **dual-column EBITDA bridge** (management-proposed vs Orionmano-validated). This is the single most-read artefact in the report. Every adjustment must:
- Classify into one of the FIVE canonical buckets:
  1. Non-recurring / one-time
  2. Owner / management compensation normalisation
  3. Run-rate adjustments (≥2 quarters of demonstrated performance required)
  4. Pro forma adjustments (known contracted future changes)
  5. Accounting policy / GAAP–IFRS adjustments
- State the source artefact (invoice, contract, payroll register, etc.)
- Show management's proposed amount AND Orionmano's validated amount, with one-line rationale on any rejection or modification

### 7. FINDINGS PRIORITISATION
Every observation classifies as one of these exact labels:
- **Deal-breaker** — may make the transaction infeasible without resolution
- **Price-impacting** — should drive a purchase-price or valuation adjustment
- **Informational** — buyer awareness item, does not block the deal

### 8. NET DEBT + DEBT-LIKE ITEMS
Net debt is bank debt + bonds + finance leases − cash, **plus debt-like items**. Always include the debt-like items schedule covering: deferred revenue, customer deposits, accrued bonuses, accrued severance/PTO, operating lease liabilities (post-IFRS 16), unfunded pensions, earn-outs, declared unpaid dividends, litigation reserves where loss probable, restricted cash (deducted from cash), factoring/receivables financing, customer rebates/chargebacks. Each item: quantified, source-cited, classified by buyer-vs-seller dispute treatment.

### 9. WORKING CAPITAL PEG
NWC analysis must include monthly trend (12–24 months), days metrics (DSO/DIO/DPO) by month, recommended peg basis with rationale, and sensitivity at ±5%/±10%. Flag the "peg trap" — a growing business needs an escalating peg.

### 10. WRITING TONE
- Third-person, transactional, data-dense
- No first person, no marketing language, no AI disclaimers, no hedging fillers ("it is worth noting that...")
- Specific numbers, specific names, specific dates
- Bold underlined headers for line-item analysis
- Markdown tables for any quantitative exhibit

Tier: {tier.upper()} — {tier_instruction}

## Report Template Reference
{template[:4000]}

## Company Data
{company_context}"""


DD_SECTION_INSTRUCTIONS = {
    "executive_summary": """Write the Executive Summary — the single-most-read section. Order MUST be:
1. **Deal context** (1 short paragraph) — issuer, transaction (Nasdaq IPO target tier / pre-IPO round), engagement scope.
2. **Headline numbers** in a markdown table:
   - Reported EBITDA → Adjusted EBITDA (Orionmano-validated), with delta in absolute and %
   - Net debt + debt-like items at latest balance sheet date
   - Recommended target NWC peg
   - QoE adjustment ratio = (Adjusted − Reported) / Reported
3. **Matters for buyer attention** — three labelled lists:
   - Deal-breakers
   - Price-impacting
   - Informational
4. **Recommended next-step diligence** — what additional procedures should be commissioned before pricing.

Use only canonical numbers established for this report. Where numbers are not yet derivable, write "Information Required: [what's needed]" instead of fabricating.""",

    "scope_basis": """Write the Scope, Basis and Limitations section. Cover:
1. **Engagement scope** — five workstreams: A. Corporate & Organization, B. Business Operations, C. Financial Statement & Accounting Policy Review, D. Internal Control & Risk Assessment, E. Targeted Procedures.
2. **Time period covered** — primary period (audited FY years), supplementary (LTM/management accounts), comparative.
3. **Sources relied upon** — itemised with as-of dates: audited FS, management accounts, trial balance, bank statements, customer contracts, board minutes, payroll register, etc. Where a source was NOT made available, list under "Information Required".
4. **Procedures performed** — financial analysis, operational review, market/commercial analysis, interviews.
5. **Canonical numbers** — state ONCE the single set of numbers that will be used throughout the report (Revenue FYxx, EBITDA FYxx, Net Debt as at xx, NWC as at xx, FX rate xxx).
6. **Limitations and restrictions** — explicit, including any data-not-provided gaps and the analytical implications.""",

    "business_overview": """Write the Business Overview. Concise — anchor a new reader before the QoE. Cover: corporate structure (entities, jurisdictions, ownership %), business model (revenue model, key products/services, value chain position), operating footprint, customer base overview (concentration detailed in the Revenue Quality section, not here), supplier base overview, key contracts (material customers, suppliers, IP licences, leases), management team (names, tenure, prior credentials), strategic milestones (funding rounds, M&A history, key product launches). If any element is not in the source material, flag as Information Required.""",

    "qoe_bridge": """Write the Quality of Earnings — Adjusted EBITDA Bridge section. THIS IS THE CENTERPIECE OF THE REPORT.

Produce a **dual-column markdown table** with these exact columns:
| Adjustment | Bucket | Management-Proposed | Orionmano-Validated | Source / Basis | Comment |

Rows:
1. Start with "Reported EBITDA (audited)" — anchor to the audited figure.
2. List each adjustment, one per row, classified into ONE of the five canonical buckets:
   - (1) Non-recurring / one-time
   - (2) Owner-comp normalisation
   - (3) Run-rate (require ≥2 quarters of demonstrated performance)
   - (4) Pro forma
   - (5) Accounting policy / GAAP–IFRS
3. End with "Adjusted EBITDA" subtotal — both columns.

For each adjustment row:
- State the management-proposed amount AND the Orionmano-validated amount.
- If validated < proposed, give a one-line rationale (insufficient documentation / recurring in nature / double-counted / fails 2-quarter run-rate threshold / supportive analytical evidence absent).
- Cite the source artefact (specific document, dated).

After the table, add:
- **Forward-looking pivot** — which add-backs persist into forward periods, which drop out, what this means for forward Adjusted EBITDA run-rate.
- **Key judgment areas** — 2–3 bullets on the most material analytical calls.

If trial balance / detailed financial data is not available, flag clearly as "Information Required" and provide the analytical framework with placeholder rows showing what adjustments WOULD typically be evaluated for this kind of business.""",

    "revenue_quality": """Write the Revenue Quality section. Cover:
1. **Customer concentration** — Top 5, Top 10, Top 20 customers as % of revenue, presented in a markdown table. Top customer >25% should be flagged as deal-breaker level. If customer-level data not available, flag Information Required.
2. **Cohort retention** — customers grouped by acquisition year, with NRR by cohort, gross retention, expansion vs contraction. Markdown table preferred.
3. **Pricing × volume × mix decomposition** — split revenue growth into ASP change × unit change × mix change. Reveals durability of growth.
4. **Recurring vs one-time** — split revenue into contracted recurring (subscription/MRC), repeat non-contracted, one-time/project. Each carries a different valuation multiple.
5. **Revenue recognition policy** — point-in-time vs over-time per ASC 606 / IFRS 15. Note any cut-off testing concerns (channel stuffing, Q4 spike pattern).""",

    "cost_margin": """Write the Cost & Margin Analysis section. Cover:
1. **Monthly gross margin trend** — minimum 36 months, presented as a markdown table or note "Information Required: monthly P&L for last 36 months" if only annual is available. Annual hides seasonality, channel stuffing, run-rate inflections.
2. **Margin decomposition** — input cost inflation, pricing actions, mix, volume leverage, one-time effects. Quantify each driver where possible.
3. **Cost composition** — fixed vs variable, headcount-to-revenue ratio.
4. **Sensitivity** — gross margin at ±5% / ±10% on key input assumptions, customer-Y leaving scenario, pricing reverting to industry mean.""",

    "working_capital": """Write the Working Capital section — trend, days metrics, peg. Cover:
1. **Monthly NWC trend** — trailing 18–24 months, markdown table. Long enough to capture seasonality. Flag Information Required if only annuals are available.
2. **Days metrics by month** — DSO, DIO, DPO. Detects pre-close manipulation (unusual receivables stretch, payables compression).
3. **Recommended peg** — basis (TTM monthly average / trailing-6-month / seasonally-adjusted) with rationale. Provide the recommended peg figure. Sensitivity at ±5% / ±10%.
4. **Peg trap warning** — if business is growing, peg should escalate. Stale 12-month average punishes the buyer who inherits higher working capital need.
5. **Closing-mechanic recommendation** — estimated closing NWC delivery, true-up window (60–90 days post-close).""",

    "net_debt": """Write the Net Debt + Debt-Like Items section. Produce the schedule as a markdown table with columns: Item | Amount | Source | Buyer Comment.

Lines (include all that are applicable):
- Bank borrowings (current + non-current)
- Bonds / notes
- Finance lease liabilities
- Less: Cash and cash equivalents
- Less: Restricted cash (then add back as debt-like)
- **Sub-total: Bank net debt**
- Plus debt-like items:
  - Deferred revenue
  - Customer deposits
  - Accrued bonuses (unpaid earned)
  - Accrued severance / unpaid PTO
  - Operating lease liabilities (IFRS 16) — flag as buyer-vs-seller contested
  - Unfunded pension / post-retirement obligations
  - Earn-outs from prior acquisitions
  - Declared but unpaid dividends
  - Litigation reserves (loss probable per legal opinion)
  - Factoring / receivables financing (off-balance-sheet)
  - Customer rebates / chargebacks accrued
- **Total Net Debt + Debt-Like Items**

Each item: quantified, source-cited, with one-line buyer-vs-seller dispute classification. Accrued bonus and deferred revenue are typically the most contested in practice — call those out explicitly.""",

    "proof_of_cash": """Write the Proof of Cash section. Reconcile bank statement deposits and disbursements to reported revenue and EBITDA over 12+ months.

Output should include:
1. Reconciliation table: Reported Revenue (P&L) → Bank Deposits Tied to Sales → Variance, by quarter or month
2. Reconciliation: EBITDA → Operating Cash Flow → Variance
3. Discussion of unreconciled items >5% of revenue or EBITDA
4. Flags for: revenue recognised but not deposited, deposits not accounted for in revenue, large round-number transfers, intercompany flows masquerading as third-party

If bank statements are not available, flag clearly as Information Required: bank statements for the trailing 12 months for all material operating accounts. Without these, proof of cash cannot be performed and a key forensic-grade procedure is missing from the report.""",

    "balance_sheet_review": """Write the Balance Sheet Review — account-by-account walk of every material balance. For each line, follow the per-line-item pattern:
1. State the change (absolute + % YoY)
2. Explain the driver
3. Assess reasonableness
4. Flag risks (collectability, impairment, classification, disclosure)

Cover (omit lines not material to this business): AR (aging, ECL adequacy, concentration, RPT exposure), prepayments (RPT exposure, IPO-cost prepayments), inventory (aging, NRV, obsolescence), PPE (additions/disposals, utilisation, impairment indicators), intangibles (nature, amortisation policy, internally generated vs acquired), ROU assets, investments (classification, impairment), goodwill (impairment testing), AP (aging, RPT), other payables / accruals (deferred rev, customer deposits, IPO accruals), borrowings (covenants, repayment schedule, fixed/floating), convertibles (terms, classification), lease liabilities, deferred tax.

Use bold underlined headers per line item. Include a Focus Areas table at the end summarising the material items requiring further scrutiny.""",

    "capex": """Write the Capex section. Cover:
1. **Maintenance vs growth split** — 3-year history with categorisation. Critical for FCF defensibility.
2. Capex / revenue ratio benchmarked against peer trading levels
3. Capex composition by category (PPE, software, M&A)
4. Forward capex plan disclosed by management — assess reasonableness against historical run-rate and growth strategy
5. **Forward-looking pivot** — what should buyer underwrite as forward maintenance capex floor for valuation purposes.""",

    "accounting_policies": """Write the Accounting Policies — Judgment Areas section. For each material policy: (a) state the current treatment, (b) is it consistent with peer comps, (c) is it aggressive or conservative, (d) how would a buyer apply it differently, (e) what happens upon US GAAP / IFRS reconciliation for SEC filing.

Cover the following where relevant:
- Revenue recognition (ASC 606 / IFRS 15) — performance obligations, variable consideration, principal vs agent determination
- Capitalisation of software / R&D
- Inventory valuation (LIFO/FIFO, NRV)
- Depreciable lives
- Lease classification (IFRS 16 / ASC 842) — finance vs operating, discount rate
- Deferred tax recognition
- Impairment testing assumptions (CGU allocation, key assumptions)

For Asia-Pacific issuers preparing under MFRS or local GAAP, explicitly flag the US GAAP / IFRS reconciliation that will be required for SEC F-1 filing.""",

    "taxation": """Write the Taxation section. Cover:
1. Effective tax rate reconciliation by year (markdown table with each component)
2. Tax loss carryforwards — movement table, DTA recognition status, expiry timeline
3. Tax jurisdictions analysis — for each material jurisdiction: applicable rates, key considerations, compliance status
4. Open tax audits / disputes
5. Transfer pricing arrangements — documentation status, intercompany pricing methodology, risk exposure
6. Indirect tax (VAT/GST/SST) — registration, compliance, refund position
7. Withholding tax — cross-border flows
8. **Pre-listing structure tax considerations** — Cayman / BVI topco / opco re-organisation tax cost; this is operationally critical for Nasdaq-bound issuers.""",

    "internal_controls": """Write the Internal Control Evaluation. For each business cycle relevant to this business, produce a markdown table with columns:
| Control Point | Risk | Control Target | Control Description | Evaluation | Suggestion |

Cycles typically covered (omit those not applicable):
1. Revenue and Accounts Receivable
2. Procurement and Accounts Payable
3. Inventory Management
4. Fixed Assets Management
5. Treasury and Cash Management
6. Human Resources and Payroll
7. Information Technology General Controls (ITGC) — IAM, change management, backup/DRP, cybersecurity
8. Financial Reporting Controls

For Nasdaq IPO context, also flag SOX 302 / 404 readiness:
- Section 302 — CEO/CFO certification readiness (financial reporting reliability)
- Section 404 — ICFR documentation, walkthroughs, key control identification, testing readiness
- For EGCs (Emerging Growth Companies, <$1.235B revenue): 404(b) auditor attestation deferred up to 5 years, but 404(a) management assessment still required.""",

    "commitments_contingencies": """Write the Commitments and Contingencies section. Cover:
1. **Open litigation** — case-by-case (parties, claim, quantum exposure, status, management's view, Orionmano view on probability and magnitude)
2. **Threatened claims** known to management
3. **Guarantees and indemnities** (intra-group, third-party)
4. **Off-balance-sheet exposures** — factoring, sale-leaseback, securitisation, parent-company guarantees
5. **Environmental / regulatory contingencies**
6. **Founder / shareholder / related-party legal history** — directorship disqualifications, regulatory sanctions, prior litigation involving controlling persons (relevant for SEC bad-actor disclosure)""",

    "net_debt_nwc": """Write the combined Net Debt + Working Capital section (Essential tier).

Part 1: **Net Debt + Debt-Like Items** schedule — markdown table with Item | Amount | Source | Buyer Comment. Cover bank debt, leases, less cash, plus the standard debt-like items (deferred revenue, customer deposits, accrued bonuses, lease liabilities, unfunded pensions, earn-outs, declared unpaid dividends, litigation reserves, restricted cash, factoring).

Part 2: **Working Capital** — recommended peg with basis (TTM monthly average preferred), days metrics if computable (DSO/DIO/DPO), sensitivity at ±5% / ±10%.

Together these set the purchase-price mechanism for a cash-free, debt-free deal: Equity Value = Enterprise Value − Net Debt + (Working Capital − Peg).

If monthly data is not available, flag Information Required and produce the schedule based on available annual data with explicit caveats.""",

    "key_findings": """Write the Key Findings and Suggestions section. Produce a markdown table:
| # | Priority | Finding | Analysis | Management's Response | Actionable Suggestion |

Where Priority is exactly one of: **Deal-breaker** / **Price-impacting** / **Informational** (not "high/medium/low").

Typically 5–10 findings, ordered by priority (deal-breakers first). Each row must be self-contained — a reader skimming this page only must understand the issue and what to do. Be direct and specific; no generic advice.""",
}


# ──────────────────────────────────────────────────────────────
# Industry Expert Report — Frost & Sullivan / CIC-style prompt
# ──────────────────────────────────────────────────────────────

INDUSTRY_SECTION_INSTRUCTIONS = {
    "sources_of_information": """Write the Sources of Information preamble in the style used by the "Industry" chapter of a Nasdaq Form S-1 / F-1 IPO prospectus.

Open with a short statement that the industry information in this report is derived from public market research, official publications, trade associations, and Orionmano's own research. State that Orionmano Industries is the imprint under which this analysis is published.

Then cover in short paragraphs:
1. **Research methodology** — Primary research (expert interviews, industry participant conversations) and secondary research (public company reports, government statistics, trade associations, news and academic research).
2. **Base assumptions** — Enumerate the explicit macro assumptions under which forecasts were prepared (e.g., (i) steady GDP growth in the relevant geography, (ii) no material geopolitical disruption, (iii) continuation of current regulatory regime).
3. **Data currency** — State the as-of date of the analysis.
4. **Limitations** — Note that forward-looking statements are inherently uncertain.

Do NOT name any paid/proprietary database. Do NOT cite client management. Do NOT use <cite/> tags in this section — it is a methodology preamble, not a factual-claim section.""",

    "executive_summary": """Write the Executive Summary. 4–6 punchy findings, each with a specific data point and a <cite/> tag. Cover: (1) headline market size and dual CAGR (historical and forecast), (2) key structural growth driver, (3) competitive-structure observation (consolidated vs fragmented; top-N share), (4) one material trend, (5) one challenge, (6) outlook line. End with one sentence framing the report's scope.""",

    "industry_definition_scope": """Define the industry precisely.
- Scope boundaries: what is IN scope and what is explicitly OUT of scope
- Key products / services / categories in the industry
- Primary end-customer segments
- Relationship to adjacent industries
- Unit of measurement used throughout the report (retail sales, ex-factory, revenue, GMV, etc.) — state explicitly
Every quantitative statement must carry a <cite/> tag.""",

    "industry_overview": """Combined overview covering definition, market size (with dual CAGR), key segments, and competitive structure at a high level. Use this for essential-tier reports only. Every numeric claim cited via <cite/>.""",

    "value_chain": """Describe the industry value chain explicitly as **Upstream**, **Midstream**, **Downstream**, each as its own subsection with:
- Activities and participants at that stage
- Key inputs/outputs
- Margin profile (high/low and why)
- Concentration or fragmentation
Conclude with a short paragraph on where economic value accrues and why. Cite structural claims via <cite/> where external evidence exists.""",

    "market_size_trajectory": """Present the market-size trajectory in Frost & Sullivan exhibit style.

Open with a paragraph stating the global market size in the most recent full year and the historical CAGR (at least 5 years back) and forecast CAGR (at least 5 years forward), with dual-CAGR format:
"The [industry] market was valued at [unit] [X] in [year], growing at a CAGR of A.B% over [historical window], and is projected to reach [unit] [Y] by [forecast year], representing a CAGR of C.D% over [forecast window]."

Then emit BOTH a chart block AND a markdown table for the trajectory:

```chart
{"type":"bar","title":"Exhibit 1: [Industry] Market Size, [start]–[end]F","x_label":"Year","y_label":"Market Size","y_unit":"[unit]","data":[{"x":"20YY","Market Size":N},{"x":"20YY","Market Size":N}],"series":["Market Size"],"annotations":["Historical CAGR A.B%","Forecast CAGR C.D%"],"source_note":"Source: Orionmano Industries"}
```

Followed by the markdown table: Year | Market Size ([unit]) | YoY Growth. Include at least 3 historical years and 3 forecast years (matching the chart data).

Discuss the inflection points in the curve. Every numeric claim requires a <cite/> tag.""",

    "geographic_distribution": """Break the market down by geography. Name specific regions/countries with their share of the total (as a %) and each region's local CAGR.

Emit a chart block showing share-of-global by region, then the full table:

```chart
{"type":"horizontal-bar","title":"Exhibit: Regional Market Share","x_label":"Share of Global","y_label":"Region","y_unit":"%","data":[{"x":"North America","Share":34.2},{"x":"Europe Union","Share":22.1}],"series":["Share"],"source_note":"Source: Orionmano Industries"}
```

Followed by markdown table: Region | Market Size ([unit]) | Share of Global (%) | Historical CAGR | Forecast CAGR.

Discuss which regions are gaining share and why. Every figure cited via <cite/>.""",

    "market_segments": """Deep dive by market segment. For EACH major segment, produce:
- Segment name and definition
- Market size (latest year) and CAGR (dual: historical + forecast)
- Share of the overall market
- Key sub-segments or product categories
- Margin / unit-economics commentary where known publicly

Emit ONE summary chart at the top showing segment shares (pie):

```chart
{"type":"pie","title":"Exhibit: Market Share by Segment, [latest year]","x_label":"Segment","y_label":"Share","y_unit":"%","data":[{"x":"Segment A","Share":42},{"x":"Segment B","Share":31}],"series":["Share"],"source_note":"Source: Orionmano Industries"}
```

Then for the largest 1–2 segments, also emit a stacked-bar chart showing their growth trajectory:

```chart
{"type":"stacked-bar","title":"Exhibit: [Top Segments] Trajectory, [start]–[end]F","x_label":"Year","y_label":"Market Size","y_unit":"[unit]","data":[{"x":"20YY","Segment A":N,"Segment B":N}],"series":["Segment A","Segment B"],"source_note":"Source: Orionmano Industries"}
```

Followed by per-segment markdown tables. Every figure cited via <cite/>.""",

    "growth_drivers": """Identify 4–6 structural growth drivers. For each:
- Name the driver (bold)
- Quantify its impact with at least one external data point under a <cite/> tag
- Explain the mechanism linking it to industry growth
Avoid generic drivers ("digital transformation"); be specific to the industry.""",

    "competitive_landscape": """Combined competitive landscape for standard/essential tiers:
1. Market structure (consolidated vs fragmented; Top-N market share with a <cite/>)
2. Player archetypes — classify participants into 2–4 cohorts (e.g., global incumbents, regional specialists, new entrants)
3. Named leading players (3–6) with a one-line positioning for each
4. Basis of competition (price, technology, distribution, brand)
Emit an "**Exhibit: Leading Players**" markdown table: Player | Headquarters | Positioning | Key Strength.""",

    "competitive_landscape_matrix": """Competitive landscape Part 1 — player archetypes and capability matrix.

Classify industry participants into archetypes (e.g., "Global [X]s", "Regional specialists", "Vertically integrated players", "Digital-native entrants"). For each archetype give 2–3 representative named companies.

Then emit "**Exhibit: Capability and Presence Matrix**" as a markdown table with:
- Rows = 6–10 named leading players
- Columns = capability/presence dimensions relevant to the industry (e.g., for CRDMO: Drug Discovery | Drug Development | Commercial Manufacturing | Innovator Focus | Global Reach)
- Cells = presence indicator: **Strong** / **Limited** / **Negligible** (use bold labels, not emoji)

Every factual assertion about specific companies must carry a <cite/> tag.""",

    "competitive_benchmarking": """Competitive landscape Part 2 — financial benchmarking of named peers.

Emit TWO chart blocks then the full table.

Chart 1 — Revenue scale comparison (bar):
```chart
{"type":"bar","title":"Exhibit: Revenue Scale of Select Peers","x_label":"Company","y_label":"Revenue","y_unit":"USD M","data":[{"x":"Peer A","Revenue":5632},{"x":"Peer B","Revenue":1611}],"series":["Revenue"],"source_note":"Source: Orionmano Industries"}
```

Chart 2 — Margin comparison (bar with two series):
```chart
{"type":"bar","title":"Exhibit: Profitability of Select Peers","x_label":"Company","y_label":"Margin","y_unit":"%","data":[{"x":"Peer A","EBITDA Margin":33.3,"PAT Margin":26.8},{"x":"Peer B","EBITDA Margin":24.6,"PAT Margin":13.7}],"series":["EBITDA Margin","PAT Margin"],"source_note":"Source: Orionmano Industries"}
```

Then "**Exhibit: Financial Benchmarking of Select Peers**" as a markdown table:
- Rows = 5–8 named public peers
- Columns = Revenue (latest year, with unit) | Revenue CAGR (last 2–3 years) | EBITDA Margin | PAT Margin | Revenue Growth (YoY) | ROE or ROCE
- Include the reporting period under each company name
- Footnotes to the table must spell out the specific accounting basis (IFRS/US GAAP), FX rates used, and fiscal-year conventions

Follow with 2–3 paragraphs interpreting: who leads on scale, who leads on margin, growth-vs-profitability trade-off, regional patterns.

Every figure requires a <cite/> tag tied to a public source. If public financials are unavailable for a company, mark the cell "n/d" (not disclosed) — do not fabricate. Omit the company entirely from chart blocks if its values are n/d (charts cannot render n/d).""",

    "industry_trends": """Identify 4–6 industry trends. For each:
- Trend name (bold)
- What is happening, with a quantitative anchor (<cite/>)
- Who is driving it (which player archetype or demand segment)
- Implication for competitive dynamics
Avoid buzzwords without data.""",

    "entry_barriers": """Discuss 4–6 key barriers to entry. Order by severity (highest first). For each:
- Barrier name (bold)
- Mechanism (why it matters)
- Empirical evidence or quantification where possible (<cite/>)
- How incumbents exploit this barrier
Include capital intensity, regulatory, technology/IP, brand/trust, distribution-access, and scale-economics barriers as relevant.""",

    "challenges_headwinds": """4–6 challenges facing the industry. For each: name, description, quantification or evidence (<cite/>), which player cohort is most exposed. Include macro, regulatory, input-cost, and demand-side headwinds. Be balanced — do not only list risks the target company is insulated from.""",

    "market_outlook": """Forward-looking assessment. Structure:
1. **Base-case trajectory** — reiterate forecast CAGR with <cite/>
2. **Upside scenarios** — 2–3 catalysts that could accelerate growth
3. **Downside scenarios** — 2–3 risks that could slow or reverse growth
4. **Structural endpoints** — where the industry is heading over 5–10 years (consolidation, digital share, geographic mix shift, product-mix shift)
No new data here without <cite/>; synthesize from earlier sections.""",

    "strategic_recommendations": """Strategic recommendations for participants in this industry. 4–6 concrete recommendations, each with:
- Recommendation title (bold)
- Rationale grounded in findings from earlier sections (reference sections by name, not by citation — internal cross-reference)
- Which cohort or company profile this applies to
- Execution considerations
This section synthesizes; it does not introduce new external data. Minimal <cite/> usage here — cite only new facts not established earlier.""",
}


# Sections that benefit from deepseek-reasoner (dense analysis + cross-section synthesis)
INDUSTRY_REASONER_SECTIONS = {
    "competitive_benchmarking",
    "market_outlook",
    "strategic_recommendations",
}


def _build_industry_report_prompt(
    company,
    tier: str,
    tier_instruction: str,
    template: str,
    web_context: str,
    company_context: str,
) -> str:
    """Build the Frost & Sullivan / CIC-style system prompt for industry reports."""
    return f"""You are a senior research analyst at **Orionmano Industries**, an independent industry research imprint publishing on industries.omassurance.com.

You are drafting a section of an **Independent Industry Expert Report** — the institutional-grade document that accompanies Nasdaq IPO prospectuses (the "Industry" chapter typical of Form S-1 / F-1 filings) and equivalent international filings. Match the voice, density, and structure of Frost & Sullivan and China Insights Consultancy (CIC) reports.

## VOICE AND STYLE
- Third-person, analytical, data-dense. No first person. No marketing language. No AI disclaimers. No hedging fillers ("it is worth noting that…").
- Every quantitative claim carries a specific number and a citation.
- Prefer specific company and product names over generic categories.
- Use markdown. Use bold for exhibit labels and emphasis.

## STRUCTURAL PATTERNS TO FOLLOW

### Dual CAGR
Always present historical and forecast CAGR side-by-side:
"The market grew from [unit] X in 20YY to [unit] Y in 20YY, a CAGR of A.B%, and is expected to reach [unit] Z by 20YYE, representing a CAGR of C.D% over 20YY–20YYE."

### Exhibits — Charts AND Tables
Reference every data exhibit as "**Exhibit N: [description]**". Source note line in italics underneath.

For ANY quantitative exhibit you would normally show as a chart in a Frost & Sullivan report (market-size trajectory, market shares, segment splits, peer benchmarking, geographic distribution), you MUST emit BOTH:

1. A `chart` fenced JSON block (rendered as an actual chart by the system), AND
2. A markdown table immediately below it (so the same data is readable in PDF / fallback views).

Chart spec format (use this EXACT schema):

```chart
{{
  "type": "bar" | "stacked-bar" | "line" | "pie" | "horizontal-bar",
  "title": "Exhibit N: [description]",
  "x_label": "string",
  "y_label": "string",
  "y_unit": "USD M" | "RMB Bn" | "%" | etc.,
  "data": [
    {{"x": "2024", "Market Size": 6.86}},
    {{"x": "2025", "Market Size": 7.72}}
  ],
  "series": ["Market Size"],
  "annotations": ["CAGR 2024-2032: 12.6%"],
  "source_note": "Source: Orionmano Industries"
}}
```

Rules for chart blocks:
- For time-series → `bar` or `line`. x = year (string). One key per series.
- For market-share → `pie` or `horizontal-bar`. Each data row has `x` (segment name) and a single value series (usually "Share").
- For benchmarking → `bar` (one row per peer, multiple series for revenue/margin/etc).
- For nested segmentation over time → `stacked-bar`. Each data row has `x` (year) and one key per stack segment.
- `data` MUST contain only numeric values for series (no strings, no "n/a"). If a value is unknown, omit the row.
- `annotations` is optional — short text labels rendered as captions.
- `source_note` is optional but recommended.

### Nested Segmentation
Break markets down on more than one dimension (e.g., Global → Geography → Segment → Sub-segment). Each level gets its own size and CAGR.

## CITATION PROTOCOL — MANDATORY

Every quantitative claim, market statistic, trend assertion, and external fact MUST carry an inline `<cite/>` tag in the following exact format:

  `<cite topic="kebab-case-topic-identifier" claim="The specific factual claim with numbers included in one sentence."/>`

### Tag Rules
1. One `<cite/>` tag per distinct factual claim. Placed IMMEDIATELY after the claim, inline (not at end of paragraph).
2. `topic` — a stable kebab-case identifier naming the subject matter. Examples:
   - `global-cosmetics-market-size-2023`
   - `china-skincare-cagr-2023-2028`
   - `mainland-china-perfume-top-5-share`
   - `crdmo-industry-outsourcing-trend`
   Use the SAME topic value across sections when citing the same underlying subject so articles can be reused.
3. `claim` — the specific factual statement, one sentence, including the numbers. Do NOT put double-quote characters inside the claim value. If you need a quote, rephrase.
4. Every number in your output must carry a `<cite/>`. If you cannot substantiate a number, do not state it.
5. DO NOT use `[1]`, `[2]`, `[^1]` or footnote syntax directly — the system converts `<cite/>` tags to footnotes automatically.

### Forbidden Sources
- Do NOT cite paid or proprietary databases (IQVIA, Bloomberg, Refinitiv, Frost & Sullivan proprietary, CIC proprietary, Gartner, internal client documents).
- Do NOT cite the target company's internal documents or management representations.
- The citation system maps every `<cite/>` to a public Orionmano article — you never pick the source directly.

### Example
"The global cosmetics market reached RMB 953.7 billion in 2023, growing at a CAGR of 6.6% over 2018–2023, and is expected to reach RMB 1,402.5 billion by 2028 at a CAGR of 8.0% over 2023–2028.<cite topic="mainland-china-cosmetics-market-size" claim="Mainland China cosmetics market grew from RMB 693.5bn in 2018 to RMB 953.7bn in 2023 (CAGR 6.6%), and is expected to reach RMB 1,402.5bn by 2028 (CAGR 8.0%)."/>"

## TIER
Tier: **{tier.upper()}** — {tier_instruction}

## INDUSTRY REPORT TEMPLATE
{template[:2500]}

## PUBLIC WEB RESEARCH (background only — do NOT quote these sources directly; use them to form your claims, then cite via `<cite/>` tags)
{web_context}

## TARGET COMPANY CONTEXT (for framing the industry, not for citing)
{company_context}

REMEMBER: This is an INDUSTRY report, not a company report. Focus on the industry. The target company context tells you which industry, geography, and segment to analyze — but the report is about the industry, and only references the target company in the Strategic Recommendations section.
"""


async def _generate_gap_parallel(
    db: AsyncSession,
    report: "Report",
    sections: list[tuple[str, str]],
    system_prompt: str,
    gap_user_suffix: str,
    max_tokens: int,
) -> None:
    """Generate gap analysis sections in two passes:
    Pass 1: Sequential — foundation sections that establish canonical data
    Pass 2: Parallel — all remaining sections (with foundation content as context)

    Cuts total generation time from ~8min to ~3min for a 16-section report.
    """
    import asyncio

    total = len(sections)
    foundation_content: list[str] = []

    # Pass 1: Generate foundation sections sequentially
    sequential_sections = []
    parallel_sections = []
    for i, (key, title) in enumerate(sections):
        if key in GAP_SEQUENTIAL_SECTIONS:
            sequential_sections.append((i, key, title))
        else:
            parallel_sections.append((i, key, title))

    report.progress_message = f"Pass 1/{2}: Establishing data foundations (0/{len(sequential_sections)})"
    await db.commit()

    for idx, (sort_order, section_key, section_title) in enumerate(sequential_sections):
        use_reasoner = section_key in GAP_REASONER_SECTIONS
        model_tag = " [R1]" if use_reasoner else ""
        report.progress_message = f"Pass 1/2: {idx+1}/{len(sequential_sections)} — {section_title}{model_tag}"
        await db.commit()

        section_instruction = GAP_SECTION_INSTRUCTIONS.get(section_key, "")
        content = await generate_text(
            system_prompt=system_prompt,
            user_prompt=f'Write the "{section_title}" section. Be professional and concise. Markdown only. No preamble.{gap_user_suffix}\n{section_instruction}',
            max_tokens=max_tokens,
            use_reasoner=use_reasoner,
        )

        section = ReportSection(
            report_id=report.id,
            section_key=section_key,
            section_title=section_title,
            content=content,
            sort_order=sort_order,
        )
        db.add(section)
        await db.commit()
        foundation_content.append(f"### {section_title}\n{content[:1500]}")

    # Build a condensed summary of foundation sections for parallel context
    foundation_summary = "\n\n".join(foundation_content)
    parallel_system_prompt = system_prompt + (
        f"\n\n## ALREADY GENERATED SECTIONS (use these as canonical reference — do NOT contradict any numbers or assumptions here):\n{foundation_summary}"
    )

    # Pass 2: Generate remaining sections in parallel batches
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _gen_section(sort_order: int, section_key: str, section_title: str) -> ReportSection:
        async with semaphore:
            use_reasoner = section_key in GAP_REASONER_SECTIONS
            section_instruction = GAP_SECTION_INSTRUCTIONS.get(section_key, "")
            content = await generate_text(
                system_prompt=parallel_system_prompt,
                user_prompt=f'Write the "{section_title}" section. Be professional and concise. Markdown only. No preamble.{gap_user_suffix}\n{section_instruction}',
                max_tokens=max_tokens,
                use_reasoner=use_reasoner,
            )
            return ReportSection(
                report_id=report.id,
                section_key=section_key,
                section_title=section_title,
                content=content,
                sort_order=sort_order,
            )

    # Process parallel sections in small batches, saving after each batch
    batch_size = MAX_CONCURRENT
    for batch_start in range(0, len(parallel_sections), batch_size):
        batch = parallel_sections[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(parallel_sections) + batch_size - 1) // batch_size
        batch_labels = []
        for _, k, t in batch:
            tag = " [R1]" if k in GAP_REASONER_SECTIONS else ""
            batch_labels.append(f"{t}{tag}")
        report.progress_message = f"Pass 2/2: Batch {batch_num}/{total_batches} — {' + '.join(batch_labels)}"
        await db.commit()

        tasks = [_gen_section(so, k, t) for so, k, t in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                sort_order, key, title = batch[i]
                section = ReportSection(
                    report_id=report.id,
                    section_key=key,
                    section_title=title,
                    content=f"*Generation failed: {str(result)}*",
                    sort_order=sort_order,
                )
                db.add(section)
            else:
                db.add(result)

        await db.commit()


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

        # Web search enrichment for industry-related reports
        web_context = ""
        if report_type in ("industry_report", "gap_analysis") and company.industry:
            try:
                query = f"{company.industry} industry market size trends {company.country or 'global'} 2025"
                results = await web_search(query, max_results=5)
                web_context = format_search_results(results)
            except Exception:
                web_context = ""

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

        # Load gap analysis framework for gap_analysis reports
        gap_knowledge = ""
        if report_type == "gap_analysis":
            gap_framework_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..", "knowledge-base", "02-due-diligence", "gap-analysis.md"
            )
            try:
                with open(gap_framework_path, "r") as f:
                    gap_knowledge = f"\n\n## Gap Analysis Framework\n{f.read()[:3000]}"
            except FileNotFoundError:
                pass

        # Build source registry for citations (not used for gap_analysis)
        web_results_list = []
        if web_context:
            import re
            for match in re.finditer(r"### Source \d+: (.+?)\nURL: (.+?)\n", web_context):
                web_results_list.append({"title": match.group(1), "url": match.group(2)})

        source_registry, references_section = _build_source_registry(documents, web_results_list or None)

        # Build report-type-specific system prompt
        if report_type == "gap_analysis":
            system_prompt = _build_gap_analysis_prompt(
                company, documents, tier, tier_instruction, template,
                gap_knowledge, web_context, company_context,
            )
            # Gap analysis: no citations, no references section
            references_section = ""
        elif report_type == "dd_report":
            system_prompt = _build_dd_prompt(
                company, documents, tier, tier_instruction, template,
                company_context,
            )
            # DD report: no citations, natural basis statements only
            references_section = ""
        elif report_type == "industry_report":
            system_prompt = _build_industry_report_prompt(
                company, tier, tier_instruction, template, web_context, company_context,
            )
            # Industry reports use inline <cite/> -> per-section GFM footnotes.
            # No numbered-source registry, no end-of-doc references section.
            references_section = ""
        else:
            system_prompt = f"""You are a senior financial advisor at Orionmano Assurance Services (Hong Kong-based), specialising in Nasdaq IPO advisory for Asia-Pacific companies. All deliverables target Nasdaq listing standards (Capital Market / Global Market / Global Select Market), SEC registration (S-1 / F-1 / 20-F / 6-K), PCAOB-audited financials, and US GAAP / IFRS reconciliation paths. Do NOT reference HKEX, HKSIR, SEHK, Bursa Malaysia, or other non-US listing regimes as the regulatory perimeter.
Generate professional report content. Be concise, data-driven, and specific.
Use markdown formatting. Reference actual company data when available.
Follow IFRS 9 and IFRS 13 standards for fair value analysis.

## CITATION REQUIREMENTS (MANDATORY)
You MUST cite sources for all claims, data points, and analysis using inline numbered references.
- Use the format [1], [2], [3] etc. to cite sources inline within your text.
- Every financial figure, metric, or data point MUST have a citation to its source document.
- Every market data point, industry statistic, or external fact MUST have a citation.
- Place the citation number immediately after the relevant claim or data point.
- A single sentence may have multiple citations if it draws from multiple sources.
- If you cannot attribute a claim to a specific source, state the basis (e.g., "Based on management representations" or "Industry standard practice").

Example: "Revenue increased 23% YoY to RM 12.1M [1], outpacing the industry average of 15% [4]."

{source_registry}

Tier: {tier.upper()} — {tier_instruction}

## Report Template Reference
{template[:2000]}{extra_knowledge}
{web_context}

## Company Data
{company_context}"""

        # Retrieve memories for this skill
        from app.services.agent.memory import retrieve_memories
        memory_skill_name = (
            "generate_gap_analysis" if report_type == "gap_analysis"
            else "generate_dd_report" if report_type == "dd_report"
            else f"generate_{report_type}"
        )
        memory_rules = await retrieve_memories(db, company_id=company_id, skill_name=memory_skill_name)
        if memory_rules:
            rules_text = "\n".join(f"- {r}" for r in memory_rules)
            system_prompt += f"\n\n## Guidelines from past feedback (follow these strictly):\n{rules_text}\n"

        max_tokens_per_section = {"essential": 800, "standard": 1500, "premium": 2500}.get(tier, 1500)
        # Gap analysis and DD report need more tokens for the detailed transaction-grade sections
        if report_type in ("gap_analysis", "dd_report"):
            max_tokens_per_section = {"essential": 1000, "standard": 2000, "premium": 3000}.get(tier, 2000)

        # Per-report-type user-prompt suffix
        if report_type in ("gap_analysis", "dd_report"):
            gap_user_suffix = (
                " Do NOT use inline citation numbers like [1], [2]. "
                "State the basis of information naturally (e.g., 'Based on FY2025 audited financials' or 'Per management representations'). "
                "If information is not available, clearly state 'Information Required' and describe what data is needed."
            )
        elif report_type == "industry_report":
            gap_user_suffix = (
                " IMPORTANT: cite every quantitative claim using inline `<cite topic=\"kebab-case\" claim=\"...\"/>` tags as specified. "
                "Do NOT use [1], [2], or [^n] syntax. Do NOT cite paid/proprietary databases or client documents. "
                "The citation system converts your `<cite/>` tags to footnotes automatically."
            )
        else:
            gap_user_suffix = (
                " IMPORTANT: Cite all data points and claims using inline [n] references to the numbered sources provided."
            )

        # --- Two-pass generation for gap analysis (parallel batches) ---
        if report_type == "gap_analysis" and len(sections) > 5:
            await _generate_gap_parallel(
                db, report, sections, system_prompt, gap_user_suffix, max_tokens_per_section,
            )
        else:
            # Standard sequential generation for other report types
            for i, (section_key, section_title) in enumerate(sections):
                report.progress_message = f"Generating {i+1}/{len(sections)}: {section_title}"
                await db.commit()

                section_instruction = ""
                use_reasoner = False
                if report_type == "gap_analysis":
                    section_instruction = GAP_SECTION_INSTRUCTIONS.get(section_key, "")
                elif report_type == "dd_report":
                    section_instruction = DD_SECTION_INSTRUCTIONS.get(section_key, "")
                elif report_type == "industry_report":
                    section_instruction = INDUSTRY_SECTION_INSTRUCTIONS.get(section_key, "")
                    use_reasoner = section_key in INDUSTRY_REASONER_SECTIONS

                content = await generate_text(
                    system_prompt=system_prompt,
                    user_prompt=f'Write the "{section_title}" section. Be professional and concise. Markdown only. No preamble.{gap_user_suffix}\n{section_instruction}',
                    max_tokens=max_tokens_per_section,
                    use_reasoner=use_reasoner,
                )

                # Industry reports: resolve <cite/> tags into GFM footnotes and
                # create PublishedArticle stubs for later body generation.
                if report_type == "industry_report":
                    from app.services.report.citations import process_cite_tags
                    content, _ = await process_cite_tags(
                        db, content, report_id=report.id
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

        # Append Sources & References section (not for gap_analysis)
        if references_section:
            ref_section = ReportSection(
                report_id=report.id,
                section_key="references",
                section_title="Sources & References",
                content=references_section,
                sort_order=len(sections),
            )
            db.add(ref_section)
            await db.commit()

        report.status = "draft"
        report.progress_message = None
        await db.commit()

        # Industry reports: kick off background article-body generation for
        # every PublishedArticle stub this report created. Detached from the
        # current session so the report is returned to the UI immediately.
        if report_type == "industry_report":
            from app.services.article.generator import generate_pending_articles_for_report
            asyncio.create_task(generate_pending_articles_for_report(report.id))

    except Exception as e:
        report.status = "failed"
        report.error_message = str(e)

    await db.commit()
