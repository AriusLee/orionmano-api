# Financial Modeling Framework

This framework guides the construction of financial models used in valuation reports. The financial model interprets the future value of the company based on historical performance, management projections, and market data.

## Model Structure

### Three-Statement Model
Build an integrated financial model connecting:
1. **Income Statement** (P&L projections)
2. **Balance Sheet** (projected positions)
3. **Cash Flow Statement** (derived from P&L and BS changes)

### Projection Period
- **Explicit forecast:** 5-10 years (typically 5 for mature, 7-10 for high-growth)
- **Terminal year:** Normalized steady-state assumptions
- **Base year:** Latest audited financials (with adjustments if needed)

## Revenue Modeling

### Bottom-Up Revenue Build
For each revenue segment, model separately:

**Subscription/Recurring Revenue:**
```
Revenue = Beginning Subscribers × Retention Rate × ARPU
        + New Subscribers × ARPU × (Months Active / 12)
```

**Product/Equipment Sales:**
```
Revenue = Units Sold × Average Selling Price
```

**Service Revenue:**
```
Revenue = Active Contracts × Average Contract Value
```

**Licensing/Franchise Revenue:**
```
Revenue = Initial License Fee (one-off)
        + Ongoing Royalties (% of franchisee revenue)
        + Support Services (recurring)
```

### Revenue Assumptions to Document
- Growth rate by segment with rationale
- Pricing assumptions (inflation, market dynamics)
- Volume assumptions (market penetration, capacity constraints)
- Geographic expansion timeline
- New product/service launch timeline
- Churn rate for subscription businesses
- Revenue concentration changes over time

## Cost Modeling

### Cost of Revenue/COGS
- Model as % of revenue (gross margin approach) or bottom-up by component
- Consider:
  - Input cost inflation
  - Economies of scale
  - Mix shift between high/low margin segments
  - Supply chain efficiency improvements

### Operating Expenses
Model key categories separately:
| Category | Modeling Approach |
|----------|-----------------|
| Staff costs | Headcount × average compensation + annual increment |
| Rent & facilities | Per-site cost × locations (step function for expansion) |
| Marketing | % of revenue or fixed + variable components |
| Depreciation | Driven by PPE schedule |
| Amortization | Driven by intangible asset schedule |
| R&D | % of revenue or management plan |
| G&A | Semi-fixed, growing at inflation + scale |
| Professional fees | Step-function increases around listing events |

### Finance Costs
- Model separately by facility:
  - Bank borrowings × weighted average interest rate
  - Lease liabilities × implicit interest rate
  - Convertible instruments × effective interest rate
- Adjust for new borrowings and repayments

## Balance Sheet Modeling

### Working Capital
Drive from revenue/COGS using efficiency ratios:
```
Accounts Receivable = Revenue × (AR Days / 365)
Inventory = COGS × (Inventory Days / 365)
Accounts Payable = COGS × (AP Days / 365)
Other Receivables = % of revenue (historical trend)
Other Payables = % of COGS or revenue (historical trend)
```

### Fixed Assets (PPE Schedule)
```
Ending PPE = Beginning PPE + Additions - Disposals - Depreciation

Where:
Additions = Maintenance Capex + Growth Capex
Maintenance Capex = Depreciation × (1 + inflation)
Growth Capex = Revenue growth driven or management plan
Depreciation = Beginning PPE / Weighted Average Useful Life
```

### Debt Schedule
For each facility:
```
Ending Debt = Beginning Debt + Drawdowns - Repayments
Interest = Average Debt × Interest Rate
```

### Equity Schedule
```
Ending Equity = Beginning Equity + Net Income - Dividends + New Equity Issuance
```

## Cash Flow Derivation

### Free Cash Flow to Firm (FCFF)
```
FCFF = EBIT × (1 - Tax Rate)
     + Depreciation & Amortization
     - Changes in Working Capital
     - Capital Expenditures
```

### Free Cash Flow to Equity (FCFE)
```
FCFE = FCFF
     - Interest × (1 - Tax Rate)
     + Net Borrowings
```

## Scenario Analysis

Build three scenarios:

| Scenario | Revenue Growth | Margins | Capex | Description |
|----------|---------------|---------|-------|-------------|
| **Base** | Management guidance with analyst adjustment | Historical trend continuation | Management plan | Most likely outcome |
| **Upside** | Base + 20-30% | Margin expansion | Accelerated investment | Everything goes right |
| **Downside** | Base - 20-30% | Margin compression | Reduced/deferred capex | Conservative/adverse |

## Model Checks & Validation

### Internal Consistency
- Balance sheet balances (A = L + E)
- Cash flow statement reconciles to BS cash movement
- Depreciation links to PPE schedule
- Interest expense links to debt schedule

### Reasonableness Checks
- Revenue growth sustainable vs. market growth?
- Margin trajectory achievable vs. industry benchmarks?
- Capex sufficient to support projected growth?
- Working capital assumptions realistic vs. historical?
- Tax rate consistent with jurisdiction and incentives?
- Cash position adequate for operations (never negative without funding)?

### Sensitivity Outputs
Generate sensitivity tables showing impact on valuation:
1. Revenue growth rate ± 2-5%
2. EBITDA margin ± 2-5pp
3. WACC ± 1-2%
4. Terminal growth rate ± 0.5-1%
5. Exit multiple ± 1-2x

## Comparable Company Data Requirements

For comparable company analysis, gather for each peer:
- Market capitalization
- Enterprise value
- Revenue (LTM and NTM)
- EBITDA (LTM and NTM)
- Net income (LTM and NTM)
- Revenue growth rate
- EBITDA margin
- Net margin
- D/E ratio
- Unlevered beta

### Market Data Sources
- **Ideal:** Bloomberg Terminal (EV/EBITDA, P/E, beta, D/E ratios)
- **Alternative:** Capital IQ, Refinitiv, Yahoo Finance, company filings
- **Fallback:** Desktop research using public filings and press releases

### Comparable Benchmarks by Market

Orionmano clients target US listings; multiples below reflect US-exchange peer trading levels.

| Market | P/E Range | EV/EBITDA Range | Notes |
|--------|----------|----------------|-------|
| Nasdaq Global Select Market | 20-35x | 15-25x | Growth premium tier; institutional liquidity |
| Nasdaq Global Market | 15-25x | 10-18x | Mid-cap growth |
| Nasdaq Capital Market | 10-20x | 6-14x | Smaller-cap (most common Orionmano client tier) |
| NYSE | 15-25x | 10-18x | Established profitable issuers |
| NYSE American | 10-18x | 6-12x | Smaller-cap alternative to Nasdaq Capital Market |
