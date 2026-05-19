# Valuation Report Template

**Audience:** Customer, Underwriter, Investor
**Format:** PDF/Word, **~40 pages target (Eric 2026-05-19 #10c)**
**Purpose:** Independent valuation of the target company

## Concision rule (Eric 2026-05-19 #10c)

The analyst must be able to review every number end-to-end. Aim for ~40 pages total — never exceed 45. Achieve this by:

- **Tables over prose** wherever a table communicates the same content with fewer words. The DCF / comps / WACC sections are largely tabular by nature.
- **One assumption = one sentence + one source citation**, not a paragraph. Use the rationale field from the inputs JSON verbatim where possible.
- **No restating context** — Company Overview cross-references the DD Report ("see DD Report §2.1"), Industry Context cross-references the Industry Report ("see Industry Report §3.2"). Don't reproduce.
- **Skip "considered but not applied" methodologies** when they're not material. A one-line note in the methodology section is sufficient.
- **Appendices belong in the xlsx**, not the PDF. The workpaper IS the detailed model — the report's appendix should only carry irreducible reference tables (e.g., comp profiles), not the full DCF cascade. Cap appendices at 5 pages total.

## Document Structure

### Front Matter
- Cover Page (same style as DD Report, with valuation-themed icon)
- Important Notice and Disclaimer
- Engagement Letter
- Table of Contents

### Main Body

#### 1. Executive Summary (2 pages)
- Valuation conclusion (range and point estimate)
- Methodologies applied and weighting
- Key assumptions summary
- Valuation date and currency
- Summary valuation table:

| Methodology | Low | Mid | High | Weight |
|-------------|-----|-----|------|--------|
| DCF | $XXM | $XXM | $XXM | XX% |
| Comparable Companies | $XXM | $XXM | $XXM | XX% |
| Precedent Transactions | $XXM | $XXM | $XXM | XX% |
| **Weighted Average** | **$XXM** | **$XXM** | **$XXM** | **100%** |

- Implied per-share value (pre/post-IPO)
- Key value drivers and sensitivities

#### 2. Company Overview (2 pages)
- Brief business description (reference DD Report for detail)
- Corporate structure
- Key financial highlights (3-year summary)
- Growth trajectory
- Management assessment

#### 3. Industry Context (1-2 pages — cross-reference Industry Report)
- Market opportunity summary (reference Industry Report)
- Growth outlook
- Competitive positioning
- Key industry multiples

#### 4. Valuation Methodology Selection (1 page)
- Rationale for selected methodologies
- Weighting justification
- Methodologies considered but not applied (with reasons)
- Compliance with IFRS 13 / ASC 820

#### 5. Discounted Cash Flow Analysis (6 pages — mostly tabular)
- **5.1 Revenue Projections** — by segment with assumptions
- **5.2 Profitability Projections** — margin assumptions
- **5.3 Working Capital Projections** — efficiency ratio assumptions
- **5.4 Capital Expenditure Projections**
- **5.5 Free Cash Flow Schedule** — 5-10 year projection table
- **5.6 WACC Calculation:**
  - Risk-free rate (source, value)
  - Equity risk premium (source, value)
  - Beta (comparable betas, unlevering/relevering)
  - Size premium
  - Country risk premium
  - Company-specific risk premium
  - Cost of equity (Ke)
  - Cost of debt (Kd)
  - Target capital structure
  - WACC result
- **5.7 Terminal Value**
  - Method selected (Gordon Growth / Exit Multiple)
  - Assumptions
  - Terminal value calculation
  - Terminal value as % of total EV
- **5.8 DCF Valuation Summary**
  - PV of projected cash flows
  - PV of terminal value
  - Enterprise value
  - Bridge to equity value (- net debt, + non-operating assets, - minority interests)
  - Equity value

#### 6. Comparable Company Analysis (4 pages)
- **6.1 Comparable Company Selection** — criteria and rationale
- **6.2 Comparable Company Summary Table:**

| Company | Country | Mkt Cap | EV | Rev | EBITDA | EV/Rev | EV/EBITDA | P/E | Growth |
|---------|---------|---------|----|----|--------|--------|-----------|-----|--------|
| Comp 1 | | | | | | | | | |
| ... | | | | | | | | | |
| **Mean** | | | | | | | | | |
| **Median** | | | | | | | | | |

- **6.3 Multiple Selection** — which multiples used and why
- **6.4 Applied Multiples** — premium/discount to median with justification
- **6.5 Implied Valuation** — application to target company metrics

#### 7. Precedent Transaction Analysis (2-3 pages, if applicable)
- **7.1 Transaction Selection Criteria**
- **7.2 Transaction Summary Table**
- **7.3 Multiple Analysis** — control premium considerations
- **7.4 Implied Valuation**

#### 8. Asset-Based Approach (1-2 pages, if applicable — skip entirely when DCF + Comps already cover the engagement)
- Adjusted NAV calculation
- Key adjustments from book value

#### 9. Valuation Reconciliation (2 pages)
- **Football field chart** — visual showing ranges from each methodology
- **Weighting rationale**
- **Selected valuation range**
- **Bridge from Enterprise Value to Equity Value:**
  - Enterprise Value
  - Less: Net Debt
  - Less: Minority Interests
  - Plus: Non-operating Assets
  - = Equity Value
- **Per-share value** (pre and post IPO if applicable)

#### 10. Sensitivity Analysis (1-2 pages — tables only, minimal prose)
- **WACC vs. Terminal Growth Rate sensitivity table**
- **Revenue Growth vs. EBITDA Margin sensitivity table**
- **Multiple vs. Base Metric sensitivity table**
- Key observations from sensitivity analysis

#### 11. Key Assumptions and Limitations (1 page)
- Complete list of material assumptions
- Scope limitations
- Reliance on management projections caveat
- Market data currency

#### Appendices (5 pages MAX)
The xlsx workpaper IS the detailed model. Only include appendices that aren't already in the workpaper:
- A. Comparable company profiles (one-page table — company, ticker, business_description, key multiples, source)
- B. Precedent transaction details (when material)
- C. Disclaimer / engagement scope (legal boilerplate)

DO NOT include in PDF:
- Full DCF cascade (in xlsx)
- WACC build-up detail (in xlsx)
- Beta calculation detail (in xlsx)
- Financial projection detail (in xlsx)

Cross-reference the xlsx for these: "See [Workpaper].xlsx, 'DCF' sheet for the full cascade."
