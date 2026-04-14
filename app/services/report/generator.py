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
        else:
            system_prompt = f"""You are a senior financial advisor at Orionmano Assurance Services (Hong Kong).
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
        memory_rules = await retrieve_memories(db, company_id=company_id, skill_name="generate_gap_analysis" if report_type == "gap_analysis" else f"generate_{report_type}")
        if memory_rules:
            rules_text = "\n".join(f"- {r}" for r in memory_rules)
            system_prompt += f"\n\n## Guidelines from past feedback (follow these strictly):\n{rules_text}\n"

        max_tokens_per_section = {"essential": 800, "standard": 1500, "premium": 2500}.get(tier, 1500)
        # Gap analysis needs more tokens for the new detailed sections
        if report_type == "gap_analysis":
            max_tokens_per_section = {"essential": 1000, "standard": 2000, "premium": 3000}.get(tier, 2000)

        # Gap analysis user prompt — no citation instruction
        gap_user_suffix = (
            " Do NOT use inline citation numbers like [1], [2]. "
            "State the basis of information naturally (e.g., 'Based on FY2025 audited financials' or 'Per management representations'). "
            "If information is not available, clearly state 'Information Required' and describe what data is needed."
        ) if report_type == "gap_analysis" else (
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
                if report_type == "gap_analysis":
                    section_instruction = GAP_SECTION_INSTRUCTIONS.get(section_key, "")

                content = await generate_text(
                    system_prompt=system_prompt,
                    user_prompt=f'Write the "{section_title}" section. Be professional and concise. Markdown only. No preamble.{gap_user_suffix}\n{section_instruction}',
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

    except Exception as e:
        report.status = "failed"
        report.error_message = str(e)

    await db.commit()
