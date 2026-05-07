# Due Diligence Report Template (Transaction-Grade)

**Audience:** Underwriter / underwriter's counsel, audit committee, transaction sponsor, institutional investors performing pre-IPO buy-side review
**Format:** PDF/Word, 35–55 pages
**Purpose:** Independent transaction-grade financial due diligence supporting a Nasdaq IPO (Form S-1 / F-1) or pre-IPO private placement. Quality bar: a senior banker or investment committee must take the document seriously.

> **Quality test:** the report must pass *"would a senior banker / IC take this seriously?"* — not *"does it sound like a research memo?"*. The single most important artefact in this report is the **dual-column EBITDA bridge** (Section 5). A report without that bridge is research, not diligence.

---

## House Rules (apply to every section)

1. **No inline citations.** Do NOT use `[1]`, `[2]`, `[^n]` or footnote numbers. State the basis of information naturally:
   - "Based on FY2024 audited consolidated income statement…"
   - "Per management representations on 2026-MM-DD…"
   - "Per the trial balance dated 2025-12-31…"
   - "Per the bank confirmation dated 2026-MM-DD…"
2. **Data consistency is mandatory.** Pick ONE canonical figure per metric (revenue, EBITDA, net income, total equity, net debt, NWC, FX rate) and use it consistently throughout. If source materials conflict, pick the most recent audited figure and note the discrepancy ONCE in the scope/basis section.
3. **Information Required pattern.** Where information is unavailable, write **"Information Required:"** with a one-sentence description of what is needed and why it is material. Do not fabricate.
4. **Forward-looking timeline.** All recommended actions and timelines must be forward-looking from the report date. Never reference past dates as future actions.
5. **Nasdaq-aligned regulatory perimeter.** Reference Nasdaq Listing Rules (5505/5605/5630/etc.), SEC requirements (Reg S-X, Reg S-K, F-1/S-1, 20-F/6-K), PCAOB audit standards, US GAAP / IFRS-as-issued-by-IASB. Do NOT reference HKEX / HKSIR / SEHK / Bursa as the regulatory perimeter.
6. **Findings prioritisation.** Every observation classifies as one of: **Deal-breaker** / **Price-impacting** / **Informational**. Use these exact labels.

---

## Document Structure

### Front Matter

#### Cover Page (Page 1)
- ORIONMANO logo + "Assurance Services" tagline
- Industry-relevant icon
- **"Project [Code Name]"**
- "Independent Financial Due Diligence Report"
- "Transaction Services | [Date]"
- "Strictly Private and Confidential" bottom right

#### Important Notice (Page 2)
- Reliance language — limited to addressee party (typically the underwriter, sponsor, or issuer)
- Confidentiality and engagement agreement reference
- Draft status notice (square brackets for outstanding items)
- No-reliance disclaimer for non-addressee parties
- Limitation of liability

#### Engagement Letter (Page 3)
- Addressed to: [Client Company / Underwriter]
- "Dear Sirs, Project [Code Name]"
- Scope reference, period covered, as-of date
- Information basis, limitations, draft confirmation
- Signature: [Partner Name], Engagement Partner, Date

---

### Main Body

#### 1. Executive Summary (Pages 4–8)

The single-most-read section. Must contain in this order:

1. **Deal context** — issuer name, transaction (Nasdaq IPO target tier / pre-IPO round), engagement scope.
2. **Headline numbers (quantified):**
   - Reported EBITDA → **Adjusted EBITDA** (Orionmano-validated). State the delta in absolute and %.
   - **Net debt + debt-like items** at most recent balance sheet date.
   - **Recommended target NWC peg.**
   - **Quality of Earnings adjustment ratio** = (Adjusted EBITDA − Reported EBITDA) ÷ Reported EBITDA.
3. **Matters for buyer attention** — categorised list:
   - **Deal-breakers** — items that may make the transaction infeasible without resolution
   - **Price-impacting** — items that should drive a purchase-price or valuation adjustment
   - **Informational** — items the buyer should be aware of but do not block the deal
4. **Recommended next-step diligence** — what additional procedures the buyer / underwriter should commission before pricing.

#### 2. Scope, Basis and Limitations (Pages 9–10)

- **Engagement scope** — five workstreams (per dd-framework.md): A. Corporate & Organization, B. Business Operations, C. Financial Statement & Accounting Policy Review, D. Internal Control & Risk Assessment, E. Targeted Procedures
- **Time period covered:**
  - Primary period — fiscal years covered by audited financial statements (typically 2–3 years)
  - Supplementary period — most recent management accounts (LTM or interim)
  - Comparative period — prior-year data for trend analysis
- **Sources relied upon** — itemised list (audited FS, management accounts, trial balance, bank statements, customer contracts, board minutes, payroll register, etc.) with as-of dates
- **Procedures performed** — financial analysis, operational review, market/commercial analysis, interviews
- **Canonical numbers** — state once, the single set of numbers used throughout
- **Limitations and restrictions** — explicit, including any data-not-provided gaps

#### 3. Business Overview (Pages 11–16)

Concise — 4–5 pages. Anchors a new reader in the business before the QoE.

- Corporate structure diagram (legal entities, jurisdictions, ownership %)
- Business model — revenue model, key products/services, value chain position
- Operating footprint — countries, sites, headcount
- Customer base overview (concentration is detailed in Section 6)
- Supplier base overview
- Key contracts — material customers, suppliers, IP licences, lease arrangements
- Management team — names, tenure, prior credentials
- Strategic milestones — funding rounds, M&A history, key product launches
- Site visit observations (with photos if performed)

#### 4. Quality of Earnings — Dual-Column EBITDA Bridge (Pages 17–24)

**The centerpiece of the report.** This section earns the report's fee.

**4.1 Bridge presentation.** Always show two columns side-by-side:

| Adjustment | Bucket | Management-Proposed | Orionmano-Validated | Source / Basis | Comment |
|---|---|---|---|---|---|
| Reported EBITDA (audited) | — | X | X | FY24 audited IS | Starting point |
| One-off settlement, NLT vs ABC | (1) Non-recurring | +200 | +200 | Settlement agreement dated 2024-MM-DD | Accepted |
| Owner CEO comp normalization | (2) Owner-comp | +180 | +90 | Payroll register; market comp survey range $200–280K | Modified — market range supports $250K, not management's $180K full add-back |
| Major customer signed Sep-24 | (3) Run-rate | +150 | 0 | Contract dated 2024-09-MM | Rejected — only 2 months of demonstrated performance vs 2-quarter rule of thumb |
| Post-close rent elimination | (4) Pro forma | +60 | +60 | Lease termination agreement | Accepted |
| Capitalised software cost | (5) Accounting policy | +0 | -45 | Trial balance / fixed asset register | Orionmano adjustment: $45K was inappropriately capitalised, should be expensed |
| **Adjusted EBITDA** | — | **X + Σmgmt** | **X + Σvalidated** | | |

**4.2 The five canonical adjustment buckets.** Every adjustment classifies into exactly one:

1. **Non-recurring / one-time** — legal settlements, M&A transaction costs, restructuring severance, fire/flood loss, COVID-period PPP/ERC, asset gains/losses, write-offs of obsolete inventory. *Source*: invoices, board minutes, settlement agreements.
2. **Owner / management compensation normalisation** — restating founder/owner pay to market; stripping personal expenses run through the business (vehicles, country club, family travel). *Source*: payroll registers, T&E ledgers, comp surveys.
3. **Run-rate adjustments** — annualising mid-period events. **Rule of thumb: requires ≥2 quarters of demonstrated performance.**
4. **Pro forma adjustments** — known *contracted* future changes (post-close rent elimination, discontinued line, signed price increase, public-company costs to be incurred post-IPO).
5. **Accounting policy / GAAP–IFRS** — ASC 606 / IFRS 15 cut-off, capitalised vs expensed software, LIFO/FIFO, lease classification (IFRS 16 / ASC 842), capitalised R&D, deferred revenue pace. Particularly relevant where the issuer will need to reconcile MFRS or local-GAAP financials to US GAAP / IFRS for SEC filing.

**4.3 Rejected adjustments.** A bridge that accepts every management add-back is unsigned by the diligence team. Each rejection or modification gets a one-line rationale: *insufficient documentation*, *recurring in nature*, *double-counted*, *supportive analytical evidence absent*, *fails 2-quarter run-rate threshold*, etc.

**4.4 Forward-looking pivot.** Close the section by mapping the historical bridge to forward-period implications: which add-backs persist, which drop out, what this means for forward Adjusted EBITDA run-rate.

#### 5. Revenue Quality (Pages 25–28)

- **Customer concentration** — Top 5, Top 10, Top 20 as % of revenue. Top customer >25% = deal-breaker flag. Page-per-customer for top 5 (revenue, growth, contract length, contract terms, churn risk).
- **Cohort retention** — customers grouped by acquisition year, NRR by cohort, gross retention, expansion vs contraction.
- **Pricing × volume × mix decomposition** — revenue growth split into ASP change × unit change × mix change.
- **Recurring vs one-time** — contracted recurring (subscription, MRC), repeat non-contracted, one-time/project. Each carries a different valuation multiple.
- **Revenue recognition policy** — point-in-time vs over-time, deferred revenue adequacy, cut-off testing especially around period-end (channel stuffing detection).

#### 6. Cost & Margin Analysis (Pages 29–31)

- **Monthly gross margin trend** — 36 months minimum, not annual. Annual hides everything.
- **Margin decomposition** — input cost inflation, pricing actions, mix, volume leverage, one-time effects.
- **Cost composition** — fixed vs variable, headcount-to-revenue ratio.
- **Sensitivity** — gross margin at ±5% / ±10% on key input assumptions, customer Y leaving, pricing reverting to industry mean.

#### 7. Working Capital — Trend, Days, Peg (Pages 32–34)

- **Monthly NWC trend** — trailing 18–24 months, long enough for seasonality.
- **Days metrics by month** — DSO, DIO, DPO. Detects pre-close manipulation (unusual receivables stretch, payables compression).
- **Recommended peg** — basis (TTM monthly average / trailing-6-month / seasonally-adjusted), with rationale. Sensitivity at ±5% / ±10%.
- **Peg trap warning** — if the business is growing, the peg should escalate. Stale 12-month average punishes the buyer who inherits higher working capital need.
- **Closing-mechanic recommendation** — estimated closing NWC delivery, true-up window (60–90 days post-close).

#### 8. Net Debt + Debt-Like Items (Pages 35–37)

| Item | Amount | Source | Buyer Comment |
|---|---|---|---|
| Bank borrowings | X | Loan facility / bank confirmation | |
| Bonds / notes | X | | |
| Finance lease liabilities | X | Lease schedule | |
| **Less:** Cash and cash equivalents | (X) | Bank confirmation | |
| **Less:** Restricted cash | added back | | Restricted = not freely available, treat as debt-like |
| **Sub-total: Bank net debt** | X | | |
| **Plus debt-like items:** | | | |
| Deferred revenue | X | TB | Cash collected, obligation not yet earned |
| Customer deposits | X | TB | Pre-paid by customer |
| Accrued bonuses (unpaid earned) | X | Payroll | |
| Accrued severance / unpaid PTO | X | Payroll | |
| Operating lease liabilities (IFRS 16) | X | Lease schedule | Treatment varies — flag for negotiation |
| Unfunded pension / post-retirement | X | Actuarial report | |
| Earn-outs from prior acquisitions | X | SPA | |
| Declared but unpaid dividends | X | Board minutes | |
| Litigation reserves (loss probable) | X | Legal opinion | |
| Factoring / receivables financing | X | Off-BS | Off-balance-sheet |
| Customer rebates / chargebacks | X | TB | |
| **Total Net Debt + Debt-Like Items** | X | | |

Each item: quantified, source-cited, and classified by likely buyer-vs-seller dispute treatment. The accrued-bonus and deferred-revenue lines are typically the most contested in practice.

#### 9. Proof of Cash (Pages 38–39)

Bank statements for 12+ months reconciled to reported revenue and EBITDA. Reveals revenue recognised but not deposited, or deposits not accounted for. Document any unreconciled items >5% of revenue or EBITDA.

#### 10. Balance Sheet Review (Pages 40–43)

Account-by-account walk of every material balance. Per-line-item analysis (per the Financial Analysis Framework):
- State the change (absolute + % YoY)
- Explain the driver
- Assess reasonableness
- Flag risks (collectability, impairment, classification, disclosure)

Cover: AR (aging, ECL, concentration), prepayments (RPT exposure), inventory (aging, NRV, obsolescence), PPE (additions/disposals, utilisation, impairment), intangibles, ROU assets, investments, AP (aging, RPT), other payables / accruals (deferred rev, customer deposits, IPO-related accruals), borrowings (covenants, repayment schedule), convertibles (terms, classification), lease liabilities, deferred tax.

#### 11. Capex (Page 44)

- **Maintenance vs growth split** — feeds the free-cash-flow argument.
- 3-year capex history with categorisation
- Capex / revenue ratio benchmarked to peer trading levels
- Forward capex plan

#### 12. Accounting Policies — Judgment Areas (Pages 45–46)

Discuss each material judgment area: is the policy consistent with peer comps; is it aggressive; how would a buyer apply it differently; what happens upon US GAAP / IFRS reconciliation for SEC filing.

- Revenue recognition (ASC 606 / IFRS 15) — performance obligations, variable consideration, principal vs agent
- Capitalisation of software / R&D
- Inventory valuation (LIFO/FIFO, NRV)
- Depreciable lives
- Lease classification (IFRS 16 / ASC 842) — finance vs operating, discount rate
- Deferred tax recognition
- Impairment testing assumptions

#### 13. Tax (Pages 47–49)

- Effective tax rate reconciliation by year
- Tax loss carryforwards — movement, DTA recognition status, expiry timeline
- Tax jurisdictions analysis — applicable rates, key considerations, compliance status
- Open tax audits / disputes
- Transfer pricing arrangements — documentation status, intercompany pricing
- Indirect tax exposure (VAT/GST/SST) — registration, compliance, refund position
- Withholding tax — cross-border flows
- Pre-listing structure tax considerations (Cayman / BVI topco / opco re-organisation tax cost)

#### 14. Internal Control Evaluation (Pages 50–53)

Business cycle tables — one cycle per page. Per the Internal Controls framework:

| Control Point | Risk | Control Target | Control Description | Evaluation | Suggestion |

Cycles typically covered (relevance varies by business):
1. Revenue and Accounts Receivable
2. Procurement and Accounts Payable
3. Inventory Management (if applicable)
4. Fixed Assets Management
5. Treasury and Cash Management
6. Human Resources and Payroll
7. Information Technology General Controls (ITGC)
8. Financial Reporting Controls

For Nasdaq IPO context, also flag SOX 302 / 404 readiness (CEO/CFO certification, ICFR documentation and testing).

#### 15. Commitments and Contingencies (Page 54)

- Open litigation — case-by-case (parties, claim, exposure, status, management's view, Orionmano view)
- Threatened claims known to management
- Guarantees and indemnities (intra-group, third-party)
- Off-balance-sheet exposures (factoring, sale-leaseback, securitisation)
- Environmental / regulatory contingencies
- Founder / shareholder / related-party legal history

#### 16. Key Findings and Suggestions (Pages 55–56)

Summary table — each row is one finding:

| # | Priority | Finding | Analysis | Management's Response | Actionable Suggestion |

Where **Priority** is one of: **Deal-breaker** / **Price-impacting** / **Informational**.

Typically 5–10 key findings, ordered by priority. Each row should be self-contained — a reader skimming this page only must understand the issue.

#### 17. Appendix / Databook (Page 57+)

The structured exhibit set — body prose cross-references the databook. Without one, the report reads as opinion; with one, as forensic.

- Monthly trial-balance trending (36 months)
- Customer concentration table (top 20 by revenue, growth, contract length)
- Top 20 manual journal entries (each with one-line explanation)
- Debt-like items detailed schedule with source documents
- NWC monthly trend with days metrics
- Capex by category
- Tax rate reconciliation detailed table
- Allowance for doubtful accounts — provision movement, aging analysis
- Glossary of terms
- Information relied upon list (with as-of dates)

---

## Formatting Standards

- ORIONMANO header on every page
- Page numbers centred at bottom
- "Strictly Private and Confidential" bottom right on every page
- Financial tables: dark navy header row, alternating white/light-gray rows
- Amounts in thousands with currency prefix (e.g., "USD'000", "MYR'000", "RMB'000")
- Always state the FX rate used and the as-of date in the basis section
- Use bold underlined headers for each line item analysis
- Two-column layout for line-item financial sections (table left, narrative right)
- Professional, objective, transactional writing tone — no hedging, no marketing language, no first person, no AI disclaimers
