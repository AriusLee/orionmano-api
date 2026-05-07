# Valuation Model Reference — Orionmano Workpaper Template

This document describes the actual valuation model workpaper structure used by Orionmano Assurance, based on the "Project TP" valuation model. This serves as the reference for AI-generated valuation outputs.

## Model Overview

- **Purpose:** Fair value analysis (Business Enterprise Value / BEV review)
- **Standards:** IFRS 9 and IFRS 13
- **Primary Method:** Discounted Cash Flow (DCF) with comparable company (CoCo) cross-check
- **Currency:** Typically HKD'000 or USD'000
- **Projection Period:** 5 years explicit forecast + terminal value

## Workpaper Sheet Structure

### 1. Dashboard & User Guide
- Company name, valuation date, currency & unit
- Manual input items checklist (historical figures, terminal growth rate, low-range values, CoCo charts)
- High-level summary of DCF value, net debt, surplus assets, equity value after DLOM
- Key parameters: discount rate, terminal growth rate
- Implied multiples: P/AUM, P/E, EV/EBITDA with CoCo ranges
- Back-testing section: revenue, EBIT, WC, capex projections vs actuals
- Revenue growth rate and EBIT margin comparison charts (prior vs current forecast)
- CoCo benchmarking charts for P/E and EV/EBITDA

### 2. Chart Data
- Back-testing data: Revenue, Gross Profit, EBIT, Net Income, Working Capital, Capex
- Projection comparison: Dec-21 forecast vs Dec-24 forecast with changes
- CAGR calculations (e.g., 2020-2022, 2023-2028)
- CoCo benchmarking data: P/E and EV/EBITDA for each comparable company with mean/median
- Show/Hide toggles for each CoCo in charts

### 3. Value Summary (Primary — Per Management Projections)
- **Financial Projection Highlights:**
  - Revenue, Direct cost, Gross Profit
  - Other Income
  - Administrative and Operating Expenses
  - Profit from Operations (EBIT)
  - Finance Costs
  - Profit Before Tax
  - Tax (calculated based on EBIT × effective rate)
  - Net Income
- **FCFF Calculation:**
  - EBIT
  - Less: Tax on EBIT
  - Add: Depreciation
  - Less: Capex
  - Less: Change in Working Capital
  - = Free Cash Flow to Firm (FCFF)
- **DCF Mechanics:**
  - Partial year adjustment
  - Discount period (1, 2, 3, ... n)
  - Discount factor = 1 / (1 + WACC)^period
  - PV of FCFF for each year
  - Terminal growth rate (typically 3%)
  - Terminal value = FCFF_terminal × (1 + g) / (WACC - g)
- **Key Metrics Tracked:**
  - Sales growth rate
  - Gross profit margin
  - EBITDA margin
  - EBIT margin
  - Net income margin
  - Net income growth
  - Effective tax rate
  - Operating expenses as % of revenue
  - Capex as % of revenue
  - Working capital as % of sales
  - AR/Inventory/AP turnover days

### 4. Value Summary (Parallel Analysis — Independent/Appraiser View)
- Same structure as primary but with independent discount rate range
- Low-end and high-end scenarios
- Different DLOM/DLOC assumptions

### 5. DCF Value Summary Output
```
Sum of PV of projected cash flows
+ Terminal value (PV)
+ Surplus assets
= Enterprise Value (EV)
+ Net cash (or - Net debt)
= 100% Equity value before DLOM and DLOC
- DLOM (Discount for Lack of Marketability)
- DLOC (Discount for Lack of Control)
= 100% Equity value after adjustments
× Equity interest held by Client
= Fair value of X% equity interest
```

### 6. Income Statement (PBC — Provided by Client)
- Detailed revenue breakdown by line item
- Detailed COGS breakdown by line item
- Gross Profit
- Detailed operating expense breakdown (30+ line items typical)
- Chinese/bilingual item names common for HK/China companies

### 7. Balance Sheet (Nature Analysis)
- Split each BS line item into:
  - Operating assets/liabilities
  - Non-operating (surplus) assets/liabilities
  - Net debt components
- Nature classification (e.g., "Unsecured, non-interest bearing interco loan")
- Net assets check

### 8. Historical Financial Statements
- 3-5 years historical BS and P&L
- Audited vs unaudited labels
- Period alignment (some companies have non-Dec year-ends with stub periods)

### 9. Discount Rate / WACC
- **CoCo Selection:** 10-17 comparable listed companies with tickers
- **WACC Components:**
  - **Cost of Equity (Ke):**
    - Risk-free rate (government bond yield)
    - Unlevered beta (from CoCo median)
    - Levered beta = Unlevered × [1 + (1-T) × D/E]
    - Equity Risk Premium (ERP, typically 6-7%)
    - Size premium (typically 2-3%)
    - Specific risk premium (2-4%, judgment-based)
    - Ke = Rf + β × ERP + Size premium + Specific risk
    - Rounded to nearest 0.5% or 1%
  - **Cost of Debt (Kd):**
    - Pre-tax cost of debt
    - Tax rate
    - After-tax Kd = Kd × (1 - T)
  - **Capital Structure:**
    - Proportion of debt (from CoCo median)
    - Proportion of equity
  - **WACC = Ke × (E/V) + Kd_aftertax × (D/V)**
- **Parallel Analysis:** Two scenarios (low-end 15.5%, high-end 17.5% typical range)

### 10. Implied Multiples
- From DCF-derived EV/Equity Value, calculate:
  - EV/Sales (historical and projected years)
  - EV/EBITDA (historical and projected years)
  - P/E (historical and projected years)
- Compare implied multiples against CoCo range to validate DCF reasonableness

### 11. CoCo Data Sheets
- **Multiples:** P/E, EV/EBITDA, EV/Revenue for each CoCo
- **Margins:** Gross margin, EBIT margin, Net margin for each CoCo
- **Ratios:** ROE, ROA, D/E, current ratio for each CoCo
- **Financial data timeline:** Revenue, EBITDA, Net Income time series
- Source: Capital IQ (CIQ) or Bloomberg

### 12. WACC Analysis (Detailed)
- Unlevered beta calculation from each CoCo
- D/E ratio for each CoCo
- Tax rate for each CoCo
- Relevered beta at target capital structure
- Sensitivity table: WACC vs terminal growth rate → EV

## Key Valuation Adjustments

### DLOM (Discount for Lack of Marketability)
- Applied to equity value of non-listed companies
- Typical range: 10-30%
- Based on restricted stock studies, IPO studies, or option pricing models
- Lower end: company has near-term IPO plans
- Higher end: small company, no near-term exit plans

### DLOC (Discount for Lack of Control)
- Applied when valuing minority interests
- Typical range: 10-30%
- Based on control premium studies
- May be combined with DLOM (e.g., combined 20-40%)

### Surplus Assets / Net Debt Bridge
- **Net debt** = Total borrowings - Cash and cash equivalents
- **Surplus assets** = Non-operating assets not captured in DCF cash flows
  - Investments (FVTPL, FVOCI)
  - Excess cash above operating needs
  - Non-core real estate
  - Amounts due from related parties (non-operating)

## CoCo Selection Criteria (Orionmano Practice)
1. Same industry / business model
2. Listed on recognized exchange (ASX, NYSE, Nasdaq, LSE, SEHK)
3. Similar revenue scale (within 0.3x-5x)
4. Similar geographic focus
5. Investment as % of total assets < 20% (to avoid investment-heavy companies distorting multiples)
6. 10-17 companies typically selected
7. Selection may change between valuations (with documented reasons)
8. Both mean and median multiples reported; median typically preferred

## Sensitivity Analysis Format
Two-dimensional table:
- **Rows:** Discount rate / WACC (e.g., 11%, 12%, 13%, 14%, 15%)
- **Columns:** Terminal growth rate (e.g., 1%, 2%, 3%, 4%, 5%)
- **Values:** Enterprise Value at each combination
- Highlight the base case intersection
