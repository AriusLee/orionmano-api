# Risk Assessment & Auto-Flag Framework

This framework defines how the AI identifies and flags risks during the due diligence process. Flags are surfaced in the Key Findings and Suggestions section of the DD report.

## Risk Categories

### 1. Concentration Risk
- **Customer concentration** — top 5 customers > 60% of revenue
- **Supplier concentration** — top 3-5 suppliers represent significant share of purchases; related-party suppliers
- **Geographic concentration** — over-reliance on single market
- **Revenue type concentration** — heavy dependence on non-recurring revenue streams
- **Product concentration** — single product/service dominance

### 2. Financial Risk
- **Liquidity** — current ratio < 1.0, negative working capital, cash runway concerns
- **Leverage** — debt-to-equity > 2.0, net debt-to-EBITDA > 3.5
- **Interest coverage** — EBITDA / finance costs < 3.0
- **Cash flow** — negative free cash flow, operating CF insufficient for debt service
- **Profitability** — declining margins, loss-making history, unsustainable cost structure
- **Foreign exchange** — significant unhedged FX exposure

### 3. Accounting & Reporting Risk
- **Revenue recognition** — aggressive recognition policies, material deferred revenue changes
- **Receivables quality** — rapid AR growth without corresponding revenue growth, aged receivables, inadequate ECL
- **Asset impairment** — indicators of impairment not addressed, optimistic residual values
- **Classification** — misclassification of debt as equity, operating vs financing lease, current vs non-current
- **Related-party transactions** — pricing not at arm's length, undisclosed RPTs, circular transactions
- **Audit qualification** — qualified opinion, emphasis of matter paragraphs

### 4. Compliance & Legal Risk
- **Internal controls** — material weaknesses, absence of documented policies
- **Tax** — underprovision, transfer pricing exposure, non-compliance with filing deadlines
- **Legal proceedings** — pending litigation, regulatory investigations, contingent liabilities
- **KYC/AML** — missing vendor/customer qualification, inadequate screening
- **Regulatory** — non-compliance with sector-specific regulations

### 5. Operational Risk
- **Key person dependency** — over-reliance on founder or small management team
- **Technology** — outdated systems, cybersecurity vulnerabilities, no DRP
- **Scalability** — operations not scalable without significant investment
- **Contract risk** — key contracts expiring without renewal certainty

### 6. Corporate Governance Risk
- **Board independence** — insufficient independent directors
- **Segregation of duties** — inadequate segregation in small teams
- **Approval frameworks** — informal or undocumented approval processes
- **ESG** — no sustainability reporting or initiatives

## Key Findings Table Format

The DD report summarizes critical findings in a structured table:

| Column | Description |
|--------|------------|
| **#** | Sequential finding number (by severity) |
| **Finding** | Description of the issue identified |
| **Analysis** | Why this matters — impact on financials, compliance, or deal |
| **Management's Response** | What management has said or done about it |
| **Actionable Suggestions** | Specific, measurable recommendations with timelines |

## Severity Classification

| Level | Definition | Example |
|-------|-----------|---------|
| **Critical** | Could prevent or materially delay the transaction; requires immediate remediation | Material misstatement, legal non-compliance, SOX material weakness |
| **High** | Significant risk that needs attention before transaction close | High concentration, missing internal controls, debt covenant breach risk |
| **Medium** | Important improvement area but not a deal-blocker | Process inefficiencies, documentation gaps, IT control weaknesses |
| **Low** | Best practice recommendation for post-transaction improvement | Automation opportunities, enhanced reporting, policy updates |

## Auto-Flag Triggers

The AI should automatically flag the following conditions when detected in financial data:

### Financial Statement Flags
- Revenue growth > 50% YoY (investigate sustainability)
- Gross margin change > 10pp YoY (investigate driver)
- AR growth significantly exceeding revenue growth (collection risk)
- Negative working capital (liquidity concern)
- Current ratio < 0.6 (severe liquidity constraint)
- Finance costs growing faster than debt (rate risk or misclassification)
- Material one-off revenue items (quality of earnings)
- Significant related party balances (arm's length assessment needed)

### Operational Flags
- Top customer > 30% of revenue (concentration)
- No formal internal control documentation (SOX risk for US listings)
- Missing vendor/customer qualification records (compliance risk)
- Convertible instruments approaching maturity (dilution or cash obligation)
- Tax losses expiring within assessment period (planning opportunity)

### Governance Flags
- < 2 independent directors (governance weakness)
- No audit committee established (required for most listings)
- Missing whistleblower mechanism (governance best practice)
- Informal change management for IT systems (data integrity risk)
