# Valuation Framework

This framework guides the preparation of Valuation Reports. It covers the methodologies used, data requirements, and analytical approach for determining enterprise value.

## Valuation Purpose

- Determine the fair market value of the target company
- Support IPO pricing, M&A negotiations, or fundraising discussions
- Provide investors and underwriters with an independent assessment
- Follows standards: **IFRS 13 (Fair Value Measurement)** and **ASC 820**

## Valuation Methodologies

### 1. Discounted Cash Flow (DCF) Analysis
The primary intrinsic valuation methodology.

**Process:**
1. Project free cash flows for 5-10 years based on management projections
2. Determine terminal value using either:
   - **Gordon Growth Model:** TV = FCF(n+1) / (WACC - g)
   - **Exit Multiple Method:** TV = EBITDA(n) × Exit Multiple
3. Discount all cash flows to present value using WACC
4. Sum PV of projected FCFs + PV of terminal value = Enterprise Value

**Key Inputs:**
| Input | Source | Considerations |
|-------|--------|---------------|
| Revenue projections | Management + analyst adjustment | Sensitize growth assumptions |
| Margin assumptions | Historical trend + management guidance | Benchmark to industry |
| Capital expenditure | Management capex plan | Maintenance vs. growth capex |
| Working capital | Historical CCC trends | Normalize for seasonal effects |
| WACC | Calculated (see below) | Multiple scenarios |
| Terminal growth rate | GDP growth proxy | Typically 2-3% for mature markets |

**WACC Calculation:**
```
WACC = (E/V × Ke) + (D/V × Kd × (1-T))

Where:
Ke = Risk-free rate + β × ERP + Size premium + Country risk premium + Company-specific risk
Kd = Pre-tax cost of debt
T = Marginal tax rate
E/V = Equity weight
D/V = Debt weight
```

**Risk-Free Rate Sources:**
- US: 10-year Treasury yield
- Malaysia: 10-year Malaysian Government Securities (MGS)
- Hong Kong: 10-year HKSAR Exchange Fund Notes

**Beta Estimation:**
- Identify 5-10 comparable public companies
- Obtain raw levered betas (2-5 year weekly or monthly)
- Unlever using comparable company D/E ratios: βu = βL / [1 + (1-T) × D/E]
- Re-lever at target company's D/E: βL = βu × [1 + (1-T) × D/E]

### 2. Comparable Company Analysis (Trading Multiples)
Market-based approach using public company peers.

**Process:**
1. Identify 8-15 comparable public companies
2. Screen by: industry, size, geography, growth profile, profitability
3. Collect current trading multiples
4. Apply relevant multiples to target company's metrics
5. Derive implied enterprise/equity value range

**Key Multiples:**
| Multiple | Formula | When Most Useful |
|----------|---------|-----------------|
| P/E | Price / EPS | Profitable companies with stable earnings |
| EV/EBITDA | Enterprise Value / EBITDA | Capital-intensive businesses, cross-border comparison |
| EV/Revenue | Enterprise Value / Revenue | High-growth or pre-profit companies |
| P/B or P/NTA | Price / Book Value or NTA | Asset-heavy companies, financial institutions |
| EV/EBIT | Enterprise Value / EBIT | When D&A is meaningful differentiator |

**Comparable Selection Criteria:**
- Same industry classification (SIC/NAICS/GICS)
- Similar business model and revenue mix
- Comparable size (revenue within 0.5x-3x)
- Similar growth profile
- Same or comparable geographic markets
- Publicly listed with available data

### 3. Precedent Transaction Analysis
Based on M&A transactions in the sector.

**Process:**
1. Identify 5-15 relevant M&A transactions in the last 3-5 years
2. Calculate implied transaction multiples
3. Adjust for control premium, synergies, market conditions
4. Apply multiples to target company

**Data Points per Transaction:**
- Acquirer and target names
- Transaction date
- Transaction value (enterprise value)
- Revenue multiple (EV/Revenue)
- EBITDA multiple (EV/EBITDA)
- Premium paid (vs. pre-announcement trading price)
- Transaction rationale (strategic, financial, synergy-driven)

### 4. Asset-Based Approach (NAV/NTA)
Floor valuation based on balance sheet values.

**Process:**
1. Adjust book values to fair market values:
   - Revalue real estate and property to market
   - Assess intangible asset fair values (brand, IP, customer relationships)
   - Mark-to-market investments
   - Adjust receivables for collectability
   - Adjust liabilities for contingencies
2. Calculate adjusted NAV = Adjusted Assets - Adjusted Liabilities
3. Consider liquidation discount if applicable

**Best Used For:**
- Asset-heavy businesses
- Holding companies
- Floor/minimum valuation reference
- Distressed situations

## Valuation Summary

### Valuation Range
Present a "football field" summary showing:
- DCF range (base, upside, downside)
- Comparable company range (25th-75th percentile)
- Precedent transaction range
- NAV reference point
- **Selected valuation range** with justification

### Sensitivity Analysis
Create 2D sensitivity tables for:
- **DCF:** WACC vs. Terminal Growth Rate
- **DCF:** Revenue Growth vs. EBITDA Margin
- **Multiples:** Selected multiple vs. base metric

### Key Assumptions Disclosure
Clearly state all material assumptions:
- Revenue growth rates by segment
- Margin expansion/contraction assumptions
- WACC components and sources
- Terminal value methodology and inputs
- Comparable company/transaction selection criteria

## Valuation Report Sections

1. Executive Summary (key conclusion, range, methodology weights)
2. Company Overview (brief, referencing DD report)
3. Industry Context (brief, referencing Industry Report)
4. Valuation Methodology Selection and Rationale
5. DCF Analysis (detailed)
6. Comparable Company Analysis (detailed)
7. Precedent Transaction Analysis (if applicable)
8. Asset-Based Approach (if applicable)
9. Valuation Reconciliation and Conclusion
10. Sensitivity Analysis
11. Key Assumptions and Limitations
12. Appendices (comparable company details, DCF model, beta calculation)
