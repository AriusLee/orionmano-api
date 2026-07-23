# Inputs Sheet — Schema Specification

The Inputs sheet is the contract between the backend (agentic skill system) and the Excel valuation workpaper. Every driver assumption lives here. Every other sheet reads from here via Excel named ranges. Backend produces a JSON object keyed by these parameter IDs; the export pipeline writes values to the named ranges.

**Status:** v1 spec — to be implemented.

## 1. Design principles

1. **Single source of truth** — no parameter exists in two places. If `wacc_per_mgmt` is on Inputs, no other sheet has its own copy.
2. **Scalars on Inputs, vectors on Projections** — single values + assumption rates live on Inputs. Year-by-year forecast lines (revenue array, FCFF array) live on `Projections`.
3. **Two-scenario discipline** — every scenario-sensitive parameter has Per-Management and Independent columns. No clone sheet (replaces TP `Value summary alt`).
4. **Audit trail mandatory** — every parameter has a Source dropdown + Source detail + Notes. (Damodaran Aramco pattern.)
5. **Named ranges, not cell refs** — every parameter has a stable Excel named range matching its `id`. Formulas downstream use `=country_erp` not `=Inputs!E47`.
6. **Tiered scope** — Core parameters are mandatory for v1. Extended parameters (precedent, R&D/lease toggles, sensitivity ranges) are optional for v1 but the schema reserves their slots.

## 2. Sheet layout

```
Col:    A         B                          C            D                E              F           G                H
Row 1   [Section header band]
Row 2   id        Parameter                  Type         Value (Per Mgmt) Value (Indep)  Source      Source detail    Notes
Row 3   ...       ...                        ...          ...              ...            ...        ...              ...
```

Most parameters use only column D (single value). Scenario-sensitive parameters use columns D + E. Tables (CoCos, Precedent) live in their own banded blocks below the scalars.

Columns:
- **A** `id` — snake_case identifier; matches the named range in Excel and the JSON key
- **B** `Parameter` — human-readable label
- **C** `Type` — number / percentage / currency / date / text / enum / boolean
- **D** `Value (Per Mgmt)` — primary value; for non-scenario params this is the only value
- **E** `Value (Independent)` — second value when scenario-sensitive; blank otherwise
- **F** `Source` — dropdown: `Audited FS`, `Management Projections`, `Capital IQ`, `Damodaran`, `Kroll`, `Prospectus`, `Engagement Letter`, `Calculated`, `Manual`
- **G** `Source detail` — free text, e.g. "FY2024 audited income statement, p.42"
- **H** `Notes` — free text

## 3. Parameter inventory

### Section A — Engagement metadata (Core)

| id | Parameter | Type | Default | Notes |
|---|---|---|---|---|
| `company_name` | Company name | text | — | Cover page anchor |
| `company_country` | Country of incorporation | enum (ISO) | — | Drives `country_erp` lookup |
| `company_industry_us` | Industry (US classification) | enum | — | Damodaran industry code |
| `company_industry_global` | Industry (Global classification) | enum | — | Damodaran industry code |
| `valuation_date` | Valuation date | date | — | Drives partial-year discount |
| `target_valuation` | Client target valuation | currency | — | ACTUAL currency units (not scaled by `unit`); null when no target set |
| `target_valuation_basis` | What the target represents | enum | `enterprise_value` | `enterprise_value` / `equity_value` — equity means after the EV-to-equity bridge (net debt, surplus assets, minority interests) AND DLOM/DLOC; the goal-seek pipeline compares the corresponding computed per-management metric to the target |
| `report_purpose` | Purpose | enum | — | `BEV review` / `IPO pricing` / `Fairness opinion` / `M&A` / `Fundraising` |
| `accounting_standard` | Accounting standard | enum | `IFRS` | `IFRS` / `US GAAP` / `IFRS 9 + IFRS 13` |
| `engagement_team_partner` | Audit/engagement partner | text | — | |
| `engagement_team_manager` | Audit/engagement manager | text | — | |
| `engagement_department` | Department | text | — | |
| `client_name` | Client (engaging party) | text | — | May differ from `company_name` |

**Replaces TP cells:** `Value summary` A1-A4, B7-B11; cover-page anchors mirrored across all sheets via `=Value summary!A1` chains.

### Section B — Currency & units (Core)

| id | Parameter | Type | Default | Notes |
|---|---|---|---|---|
| `currency` | Reporting currency | enum (ISO 4217) | `USD` | Primary display currency |
| `unit` | Unit of presentation | enum | `'000` | `'000` / `million` / `actual` |
| `currency_alt` | Secondary display currency | enum (optional) | — | TP carries USD'000 + HKD'000 |
| `fx_rate_alt` | FX rate to alt currency | number | — | Required if `currency_alt` set |

### Section C — Tax rule (Core)

| id | Parameter | Type | Default | Notes |
|---|---|---|---|---|
| `tax_jurisdiction` | Tax jurisdiction | enum (ISO) | — | |
| `tax_type` | Tax structure | enum | `flat` | `flat` / `two_tier` / `progressive` |
| `tax_rate_low` | Low-tier rate | percentage | — | For `two_tier` / `progressive` |
| `tax_rate_high` | High-tier (or flat) rate | percentage | — | Single rate if `flat` |
| `tax_threshold` | Threshold between tiers | currency | — | In reporting currency + unit |
| `tax_effective_rate` | Effective rate (override) | percentage | — | If management discloses an effective rate that differs from statutory |

**Replaces TP hardcode:** `Value summary` E24, F24 (HK two-tier rates), J24 threshold of `2000`.

### Section D — Projection drivers (Core, scalars; year-vectors on Projections sheet)

| id | Parameter | Type | Notes |
|---|---|---|---|
| `projection_years` | Explicit forecast years | integer | Default 5 |
| `revenue_growth_method` | Revenue growth method | enum | `flat` / `declining` / `staged` / `per_year` |
| `revenue_y0` | Revenue base (Y0 / LTM) | currency | **Required** — last reported full-year revenue. Cascades into Projections!C8 (Y0 base). Without this, every Y1–Y5 figure resolves to 0. |
| `nwc_y0` | Net working capital (Y0) | currency | **Required** — audited Y0 net working capital. Used as base for Y1 ΔNWC. |
| `revenue_growth_y1`..`_y10` | Annual revenue growth | percentage | Per-year overrides; nullable |
| `gross_margin_y1`..`_y10` | Gross margin | percentage | |
| `opex_pct_revenue_y1`..`_y10` | Operating expenses % of revenue | percentage | |
| `capex_pct_revenue_y1`..`_y10` | Capex % of revenue | percentage | |
| `dep_pct_revenue_y1`..`_y10` | Depreciation % of revenue | percentage | |
| `nwc_pct_sales_y1`..`_y10` | Working capital % of sales | percentage | OR use turnover days below |
| `ar_days_y1`..`_y10` | AR turnover days | number | Optional alt to `nwc_pct_sales` |
| `inv_days_y1`..`_y10` | Inventory turnover days | number | Optional |
| `ap_days_y1`..`_y10` | AP turnover days | number | Optional |

**Pragmatic v1:** carry `_y1` through `_y5` only. Schema reserves `_y6`-`_y10` for longer projections.

#### Section D.1 — Revenue segments (`projections.segments[]`, optional)

If non-empty, per-segment series aggregate into total revenue & gross profit; top-level `revenue_growth` + `gross_margin` are ignored. Each segment:

| id | Parameter | Type | Notes |
|---|---|---|---|
| `name` | Segment / revenue-stream name | string | Required |
| `start_year` | First projection year the stream exists | integer | `0` = already running; `k` = launches at Yk |
| `revenue_y0` | Y0 revenue | currency | Required when `start_year == 0` |
| `initial_revenue` | Revenue at `start_year` | currency | Required when `start_year > 0` |
| `revenue_growth` | Growth from `start_year` onward | percentage[] | |
| `gross_margin` / `cogs_pct` | Per-year margin (either form) | percentage[] | `cogs_pct = 1 − gross_margin` |
| `source` | Origin of the segment | enum | `core` / `additional_stream` (user-defined via settings panel) |
| `opex_pct_revenue` | Related opex (S&M / distribution) % of stream revenue | percentage[] | When set, the stream carries its own related-opex line and is carved out of the top-level opex base |
| `growth_basis` | One-line defence of the growth vector | string | e.g. `"Analyst override"` or `"Web research: EV charging CAGR ~24% (BNEF, retrieved 2026-07)"` |
| `contractual_support` | Contracts / backlog / MOUs supporting the stream | string | Leave empty only if genuinely none — empty triggers the unproven-segment validation flag |

### Section E — Terminal value (Core)

| id | Parameter | Type | Default | Notes |
|---|---|---|---|---|
| `terminal_method` | Terminal value method | enum | `gordon_growth` | `gordon_growth` / `exit_multiple` |
| `terminal_growth_rate` | Terminal growth rate | percentage | `0.03` | Used if `gordon_growth` |
| `terminal_exit_multiple_type` | Exit multiple metric | enum | — | `EV/EBITDA` / `EV/Sales` / `P/E` |
| `terminal_exit_multiple_value` | Exit multiple value | number | — | Used if `exit_multiple` |
| `nominal_gdp_growth` | Long-run nominal GDP growth of the operating jurisdiction | percentage | `0.04` | Reference ceiling: `terminal_growth_rate` at or above `nominal_gdp_growth − 0.005` is flagged and must be explicitly justified. Cite IMF WEO / World Bank with retrieval date in `sources` |

### Section F — WACC inputs (Core, scenario-sensitive)

Two-column block (Per Mgmt / Independent). Most parameters appear in both columns; some (Rf, ERP, country premium) typically share across scenarios.

| id | Parameter | Type | Scenarios | Notes |
|---|---|---|---|---|
| `risk_free_rate` | Risk-free rate | percentage | shared | 10y govt bond in `currency` |
| `risk_free_rate_source` | Rf source descriptor | text | shared | e.g. "10y MGS as at 2026-04-29" |
| `equity_risk_premium` | ERP | percentage | shared | Damodaran or Kroll |
| `country_risk_premium` | Country risk premium | percentage | shared | From Country ERP sheet, by `company_country` |
| `unlevered_beta` | Unlevered beta | number | per-scenario | From CoCo median (calculated) or override |
| `target_debt_to_equity` | Target D/E ratio | percentage | per-scenario | From CoCo median or management target |
| `levered_beta` | Levered beta (calculated) | number | per-scenario | `=unlevered_beta * (1 + (1-tax)*D/E)` |
| `size_premium` | Size premium | percentage | per-scenario | Kroll size deciles |
| `specific_risk_premium` | Company-specific risk | percentage | per-scenario | Judgment-based, 2-4% typical |
| `cost_of_equity` | Cost of equity (Ke, calculated) | percentage | per-scenario | `=Rf + β*ERP + size + country + specific` |
| `pretax_cost_of_debt` | Pre-tax Kd | percentage | per-scenario | |
| `aftertax_cost_of_debt` | After-tax Kd (calculated) | percentage | per-scenario | `=Kd * (1 - tax_effective_rate)` |
| `target_debt_weight` | D/V | percentage | per-scenario | |
| `target_equity_weight` | E/V | percentage | per-scenario | `=1 - D/V` |
| `wacc` | WACC (calculated) | percentage | per-scenario | `=Ke*E/V + Kd_at*D/V` |

**Replaces TP cells:** `Discount rate` D52-E62 (low/high WACC build) and `WACC (final)` rows 13-30 (component aggregates).

### Section G — Comparable companies table (Core)

Tabular block: one row per CoCo, up to 30 rows reserved.

| Column | Field | Type | Notes |
|---|---|---|---|
| `coco_tier` | Tier | enum | `1` / `2` / `3` / `Excluded` — drives `AVERAGEIFS` |
| `coco_include` | Include in analysis | boolean | Master toggle |
| `coco_company` | Company name | text | |
| `coco_ticker` | Ticker | text | e.g. `NASDAQ:AMZN` |
| `coco_country` | Country | enum (ISO) | |
| `coco_accounting` | Accounting standard | enum | `IFRS` / `US GAAP` / `Local` |
| `coco_market_cap` | Market cap | currency | In USD millions |
| `coco_d_to_e` | D/E ratio | percentage | For unlevering beta |
| `coco_raw_beta` | Raw levered beta | number | From Capital IQ / Bloomberg |
| `coco_tax_rate` | Effective tax rate | percentage | For unlevering beta |
| `coco_unlevered_beta` | Unlevered β (calculated) | number | `=raw_beta / (1 + (1-T)*D/E)` |

Multiples + margins + ratios per CoCo are produced by the agent as parallel arrays (`coco_multiples`, `coco_margins`, `coco_ratios`) and written into the dedicated sheets (`CoCo Multiples`, `CoCo Margins`, `CoCo Ratios`) by the export pipeline. Indexed row-by-row with this selection table.

**Tier 3 size-cap rule:** comparables (especially Tier 3 reference comps) MUST be within ~10× the target's enterprise value. Including megacap reference comps that are 100×+ the target's size silently distorts the median multiples and inflates the implied EV ceiling. If the target's market cap is not yet known, use revenue × industry-typical EV/Sales as a proxy.

**Replaces TP cells:** `WACC (final)` rows 15-44 (CoCo selection), `Multiples (final)` cols 2-10, `Margins (final)`, `Ratios (final)` per-CoCo rows.

### Section H — Precedent transactions (Extended)

Tabular block: one row per transaction, up to 15 rows reserved.

| Column | Field | Type | Notes |
|---|---|---|---|
| `precedent_include` | Include | boolean | |
| `precedent_date` | Transaction date | date | |
| `precedent_acquirer` | Acquirer | text | |
| `precedent_target` | Target | text | |
| `precedent_ev` | Transaction EV | currency | USD millions |
| `precedent_ev_revenue` | EV/Revenue multiple | number | |
| `precedent_ev_ebitda` | EV/EBITDA multiple | number | |
| `precedent_premium` | Premium paid | percentage | vs pre-announcement price |
| `precedent_rationale` | Strategic rationale | text | |

**New in v1.** TP has no precedent transactions sheet. SEC fairness opinions consistently include this.

### Section I — EV → Equity bridge (Core)

| id | Parameter | Type | Notes |
|---|---|---|---|
| `surplus_assets` | Surplus / non-operating assets | currency | Pulled from BS nature, optionally overridden |
| `net_debt_override` | Net debt (override) | currency | Optional; otherwise `=BS nature` net debt |
| `minority_interests` | Minority interests | currency | Subtracted from EV |
| `non_operating_assets` | Non-operating assets (separate) | currency | Added to EV |
| `dlom_pct` | DLOM rate | percentage | Default 20%; range 10-30% |
| `dloc_pct` | DLOC rate | percentage | Default 20%; range 10-30% |
| `equity_interest_pct` | Client's % equity interest | percentage | e.g. 10% for partial-stake valuation |
| `shares_outstanding` | Shares outstanding (basic) | number | Pre-IPO basic; required for per-share output |
| `shares_outstanding_diluted` | Shares outstanding (diluted) | number | Optional; post-IPO fully diluted |
| `pre_money_pct` | Pre-money equity % | percentage | IPO-only; existing shareholders' share before IPO dilution |

**Replaces broken TP `#REF!` cells:** `Value summary` D66 (DLOC rate), D68 (DLOM rate), F69 (post-bridge calculation reference). Both currently point to deleted parameter cells — these become explicit Inputs entries.

### Section J — Adjustment toggles (Extended — Damodaran pattern)

| id | Parameter | Type | Default | Notes |
|---|---|---|---|---|
| `capitalize_rd` | Capitalize R&D? | boolean | `false` | If `true`, `R&D Adj` sheet activates |
| `rd_amortization_years` | R&D amortization period | integer | `5` | If `capitalize_rd` |
| `convert_operating_leases` | Convert operating leases to debt? | boolean | `false` | If `true`, `Lease Adj` sheet activates |
| `lease_discount_rate` | Lease discount rate | percentage | — | If `convert_operating_leases`; defaults to `pretax_cost_of_debt` |

**New in v1.** TP target was a PE fund so didn't need these. Critical for tech / SaaS Asia-Pac IPO targets.

### Section K — Football field weights (Extended)

| id | Parameter | Type | Notes |
|---|---|---|---|
| `weight_dcf` | DCF weight | percentage | Sum to 100% |
| `weight_comps` | Comparable companies weight | percentage | |
| `weight_precedent` | Precedent transactions weight | percentage | 0% if no precedents |
| `weight_nav` | NAV / asset-based weight | percentage | 0% if not asset-heavy |
| `selected_low` | Selected valuation low | currency | Manual judgment override |
| `selected_mid` | Selected valuation mid | currency | |
| `selected_high` | Selected valuation high | currency | |

**New in v1.** Required for Football Field reconciliation sheet.

### Section L — Sensitivity ranges (Extended)

| id | Parameter | Type | Notes |
|---|---|---|---|
| `sens_wacc_step` | WACC sensitivity step | percentage | e.g. `0.005` for 0.5% steps |
| `sens_wacc_count` | Steps each side of base | integer | e.g. 5 → ±2.5% |
| `sens_terminal_g_step` | Terminal g sensitivity step | percentage | |
| `sens_terminal_g_count` | Steps each side of base | integer | |
| `sens_revenue_g_step` | Revenue growth sens step | percentage | |
| `sens_ebitda_margin_step` | EBITDA margin sens step | percentage | |

## 4. Validation rules & dropdowns

| Field | Rule |
|---|---|
| `valuation_date` | Must be in past or current month |
| `terminal_growth_rate` | 0% ≤ x ≤ 5%; warn if > GDP growth proxy for `currency` |
| `dlom_pct`, `dloc_pct` | 0% ≤ x ≤ 50%; warn if > 30% |
| `risk_free_rate` | 0% ≤ x ≤ 15%; cross-check vs current 10y govt bond for `currency` |
| `equity_risk_premium` | 4% ≤ x ≤ 10%; cross-check vs Damodaran ERP page |
| `target_debt_to_equity` | ≥ 0; warn if > 200% |
| `wacc` | calculated; warn if < `risk_free_rate` (sanity floor) |
| `tax_*` rates | 0% ≤ x ≤ 50% |
| `weight_*` (football field) | sum must equal 100% |
| `coco_tier` | must be 1, 2, 3, or Excluded |

Source dropdown enum:
```
Audited FS | Management Projections | Capital IQ | Bloomberg | Damodaran | Kroll | Mercer | Prospectus | Engagement Letter | Calculated | Manual
```

## 5. JSON contract

Backend produces this object; export pipeline maps it onto Inputs sheet named ranges.

```jsonc
{
  "engagement": {
    "company_name": "string",
    "company_country": "ISO 3166-1 alpha-2",
    "company_industry_us": "string",
    "company_industry_global": "string",
    "valuation_date": "YYYY-MM-DD",
    "report_purpose": "BEV review | IPO pricing | Fairness opinion | M&A | Fundraising",
    "accounting_standard": "IFRS | US GAAP | IFRS 9 + IFRS 13",
    "engagement_team": {
      "partner": "string",
      "manager": "string",
      "department": "string"
    },
    "client_name": "string"
  },
  "currency": {
    "primary": "USD",
    "unit": "'000 | million | actual",
    "alt": "HKD | null",
    "fx_rate_alt": 7.8
  },
  "tax": {
    "jurisdiction": "ISO 3166-1 alpha-2",
    "type": "flat | two_tier | progressive",
    "rate_low": 0.0825,
    "rate_high": 0.165,
    "threshold": 2000,
    "effective_rate_override": null
  },
  "projections": {
    "years": 5,
    "revenue_growth_method": "per_year",
    "revenue_y0": 100000,
    "nwc_y0": 8000,
    "revenue_growth": [0.15, 0.12, 0.10, 0.08, 0.06],
    "gross_margin": [0.45, 0.45, 0.46, 0.46, 0.46],
    "opex_pct_revenue": [0.30, 0.28, 0.27, 0.27, 0.27],
    "capex_pct_revenue": [0.05, 0.05, 0.04, 0.04, 0.04],
    "dep_pct_revenue": [0.03, 0.03, 0.03, 0.03, 0.03],
    "nwc_pct_sales": [0.10, 0.10, 0.10, 0.10, 0.10]
  },
  "historical_fs": {
    // 5-element arrays (FY-5..FY-1, oldest first). Pad missing years with null (NOT 0).
    // Income statement
    "revenue": [80, 88, 95, 100, null],
    "cogs": [-50, -55, -58, -62, null],
    "gross_profit": [30, 33, 37, 38, null],
    "opex_total": [-22, -23, -25, -27, null],
    "sga": [-15, -16, -17, -18, null],
    "rnd": [-7, -7, -8, -9, null],
    "ebitda": [8, 10, 12, 11, null],
    "da": [-2, -2, -3, -3, null],
    "ebit": [6, 8, 9, 8, null],
    "interest_expense": [-1, -1, -1, -1, null],
    "other_income_expense": [0, 0, 0, 0, null],
    "profit_before_tax": [5, 7, 8, 7, null],
    "tax_expense": [-1, -1.5, -2, -1.7, null],
    "net_income": [4, 5.5, 6, 5.3, null],
    // Balance sheet
    "cash": [3, 4, 5, 6, null],
    "accounts_receivable": [12, 13, 14, 15, null],
    "inventory": [5, 6, 6, 6, null],
    "prepaid_expenses": [1, 1, 1, 1, null],
    "total_current_assets": [21, 24, 26, 28, null],
    "ppe": [25, 28, 32, 36, null],
    "intangibles": [3, 3, 3, 3, null],
    "other_lt_assets": [2, 2, 2, 2, null],
    "total_assets": [51, 57, 63, 69, null],
    "accounts_payable": [-7, -8, -9, -10, null],
    "short_term_debt": [-3, -3, -2, -2, null],
    "other_current_liabilities": [-2, -2, -2, -3, null],
    "total_current_liabilities": [-12, -13, -13, -15, null],
    "long_term_debt": [-12, -12, -10, -10, null],
    "other_lt_liabilities": [-1, -1, -1, -1, null],
    "total_liabilities": [-25, -26, -24, -26, null],
    "total_equity": [26, 31, 39, 43, null]
  },
  "terminal": {
    "method": "gordon_growth",
    "growth_rate": 0.03,
    "exit_multiple_type": null,
    "exit_multiple_value": null,
    "nominal_gdp_growth": 0.04
  },
  "wacc": {
    "shared": {
      "risk_free_rate": 0.045,
      "risk_free_rate_source": "10y UST as at 2026-04-29",
      "equity_risk_premium": 0.055,
      "country_risk_premium": 0.012
    },
    "per_management": {
      "unlevered_beta": 1.05,
      "target_debt_to_equity": 0.25,
      "size_premium": 0.025,
      "specific_risk_premium": 0.02,
      "pretax_cost_of_debt": 0.06,
      "target_debt_weight": 0.20,
      "target_equity_weight": 0.80
    },
    "independent": {
      "unlevered_beta": 1.10,
      "target_debt_to_equity": 0.30,
      "size_premium": 0.03,
      "specific_risk_premium": 0.03,
      "pretax_cost_of_debt": 0.065,
      "target_debt_weight": 0.23,
      "target_equity_weight": 0.77
    }
  },
  "cocos": [
    {
      "tier": 1,
      "include": true,
      "company": "string",
      "ticker": "NASDAQ:XXXX",
      "country": "US",
      "accounting": "US GAAP",
      "market_cap_usd_mm": 1234.5,
      "d_to_e": 0.20,
      "raw_beta": 1.20,
      "tax_rate": 0.21
    }
  ],
  "coco_multiples": [
    // Same length and order as `cocos`. Use null where a metric isn't applicable
    // (e.g. negative-EBITDA companies → null for EV/EBITDA).
    {
      "ev_sales_ltm": 3.2,
      "ev_sales_ntm": 2.8,
      "ev_ebitda_ltm": 16.5,
      "ev_ebitda_ntm": 14.0,
      "pe_ltm": 22.0,
      "pe_ntm": 18.5
    }
  ],
  "coco_margins": [
    // Same length as `cocos`. Decimals (e.g. -0.10 = -10%).
    { "gross": 0.55, "ebit": 0.18, "net": 0.12 }
  ],
  "coco_ratios": [
    // Same length as `cocos`.
    { "roe": 0.18, "roa": 0.08, "d_to_e": 0.20, "current_ratio": 2.1 }
  ],
  "precedents": [
    {
      "include": true,
      "date": "2024-06-15",
      "acquirer": "string",
      "target": "string",
      "ev_usd_mm": 5000,
      "ev_revenue": 3.5,
      "ev_ebitda": 18.0,
      "premium": 0.32,
      "rationale": "string"
    }
  ],
  "bridge": {
    "surplus_assets": 50,
    "net_debt_override": null,
    "minority_interests": 0,
    "non_operating_assets": 0,
    "dlom_pct": 0.20,
    "dloc_pct": 0.20,
    "equity_interest_pct": 1.00,
    "shares_outstanding": 123456789,
    "shares_outstanding_diluted": 145000000,
    "pre_money_pct": 0.85
  },
  "adjustments": {
    "capitalize_rd": false,
    "rd_amortization_years": 5,
    "convert_operating_leases": false,
    "lease_discount_rate": null
  },
  "football_field": {
    "weight_dcf": 0.50,
    "weight_comps": 0.30,
    "weight_precedent": 0.20,
    "weight_nav": 0.00,
    "selected_low": null,
    "selected_mid": null,
    "selected_high": null
  },
  "sensitivity": {
    "wacc_step": 0.005,
    "wacc_count": 5,
    "terminal_g_step": 0.005,
    "terminal_g_count": 5,
    "revenue_g_step": 0.02,
    "ebitda_margin_step": 0.02
  },
  "sources": {
    "company_name": { "source": "Engagement Letter", "detail": "...", "notes": "" },
    "revenue_growth_y1": { "source": "Management Projections", "detail": "FY2025 budget, p.12", "notes": "..." }
    // ... one entry per parameter
  }
}
```

Every parameter has a matching `sources.<id>` entry for the audit trail.

## 6. Mapping — what each parameter replaces

| Parameter | Replaces in TP | New / from Damodaran |
|---|---|---|
| Engagement metadata block | `Value summary` A1-A4, B7-B11 (cover page) | — |
| `tax_*` | `Value summary` E24, F24, J24 hardcode (HK 8.25%/16.5%/2000) | — |
| `revenue_growth_y1..y5` | `Value summary` row 11 (per-year growth rates) | — |
| `gross_margin_*`, `opex_pct_*`, `capex_pct_*` | `Value summary` rows 17-19, 30, etc. + ratio outputs rows 48-49 | — |
| `terminal_growth_rate` | `Chart data` F103 (manual input per User Guide item 2) | — |
| WACC build (Section F) | `Discount rate` D52-E62, `WACC (final)` rows 13-30 | — |
| `country_risk_premium` | — (not in TP) | **Damodaran `Country equity risk premiums` sheet** |
| CoCo selection table | `WACC (final)` rows 15-44 | — |
| `dlom_pct`, `dloc_pct` | **TP `Value summary` D66, D68 — both `#REF!`** | — |
| `surplus_assets`, `net_debt_override` | TP `Value summary` rows 62-64 (linked to BS nature) | — |
| Precedent transactions block | — (not in TP) | **New — SEC fairness opinion pattern** |
| `capitalize_rd`, `rd_amortization_years` | — (not in TP) | **Damodaran `R&D converter`** |
| `convert_operating_leases`, `lease_discount_rate` | — (not in TP) | **Damodaran `Operating lease converter`** |
| Football field weights | — (not in TP) | **New — SEC fairness opinion pattern** |
| Sensitivity ranges | — (TP has fixed sensitivity grid) | — |

## 7. Implementation notes

**Excel named-range strategy:**
- One named range per scalar parameter, scoped to workbook (not sheet)
- Named range name = parameter `id` exactly
- Tabular blocks (CoCos, Precedents) use named ranges over the table area: `cocos_table`, `precedents_table`
- Year-vector parameters: prefer storing `revenue_growth_y1` ... `revenue_growth_y5` as five separate named cells over a single array, for cleaner formula references on `Projections`

**Source dropdowns:**
- Use Excel data validation with a hidden `_dropdowns` sheet holding the lists
- Dropdowns for: `Source` enum, `report_purpose`, `accounting_standard`, `tax_type`, `terminal_method`, `currency`, ISO country list, etc.

**Two-scenario columns:**
- Where a parameter is per-scenario, both columns D and E hold values and have named ranges: `unlevered_beta_per_mgmt` and `unlevered_beta_indep`
- Single-scenario parameters live in column D with named range matching `id` (no suffix)

**Validation banner on Dashboard:**
- Compute green / amber / red status per validation rule
- Surface as a panel at the top of `Dashboard`

**Source sheet for backend export:**
- Backend writes JSON to a single file passed to the export script
- Export script (Python + openpyxl) reads JSON, walks `sources`, writes value into named range, writes source metadata into adjacent F:H columns
- Validation runs after write; failures returned to backend for surfacing

## 8. Open questions for client confirmation

1. **Two-scenario columns:** TP uses two full sheet clones. Is collapsing to side-by-side columns acceptable to the client, or do they require the sheet-clone format?
2. **Tax rule shape:** is the two-tier HK pattern in TP carried forward by accident, or is it a deliberate convention? For Asia-Pac Nasdaq IPO targets (PRC, SG, MY, KR), most jurisdictions are flat-rate.
3. **CoCo data source:** TP uses Capital IQ with a manual import timeline sheet. Will v1 have a Capital IQ feed, or will CoCo data be entered manually / pulled from an alternative source (e.g. SEC EDGAR XBRL for US-listed CoCos)?
4. **Equity interest %:** TP sometimes values a partial stake (10% interest). Is this the default workflow, or is 100% equity interest the default with partial-stake as an option?
5. **R&D / lease toggles:** these are off by default but critical for tech / SaaS targets. Confirm typical client target profile so we can set sensible defaults.

## 9. References

- Project TP calc graph: `project-tp-calc-graph.md`
- Valuation framework: `valuation-framework.md`
- Workpaper structure reference: `valuation-model-reference.md`
- Damodaran reference models: `../../materials/references/damodaran-amazon-sept2018.xlsx`, `damodaran-aramco-ipo.xlsx`
- External exemplar list: `~/AI-OS/wiki/concepts/us-valuation-report-exemplars.md`
