# Financial Analysis Framework

This framework guides the AI in performing analytical review of financial statements for the Due Diligence Report.

## Balance Sheet Analysis

For each line item, the analysis follows a consistent pattern:
1. **State the change** — absolute amount and percentage YoY
2. **Explain the driver** — what caused the change (business activity, accounting treatment, one-off event)
3. **Assess reasonableness** — is the change consistent with business operations and management's narrative?
4. **Flag risks** — any concerns about collectability, impairment, classification, or disclosure

### Current Assets
| Line Item | Key Analysis Points |
|-----------|-------------------|
| Accounts Receivable | Aging analysis, ECL adequacy, concentration by customer, collection history, related party balances |
| Other Receivables & Prepayments | Nature breakdown, related party amounts, prepayments to related parties, advance payments for IPO costs |
| Tax Recoverables | Overpayment position, refund timeline, certainty of recovery |
| Cash & Cash Equivalents | Bank reconciliation status, restricted cash, pledged deposits, currency breakdown |
| Inventory | Aging, obsolescence provision, NRV testing, slow-moving items, count procedures |

### Non-Current Assets
| Line Item | Key Analysis Points |
|-----------|-------------------|
| PPE | Addition/disposal schedule, depreciation policy, utilization rates, impairment indicators, capex vs revenue |
| Intangible Assets | Nature (software, IP, licenses), amortization policy, impairment testing, internally generated vs acquired |
| Right-of-Use Assets | Lease classification, discount rate, remaining lease terms, variable lease components |
| Investments | Classification (FVTPL/FVOCI/amortized cost), impairment, nature and purpose |
| Goodwill | Impairment testing, CGU allocation, key assumptions |

### Current Liabilities
| Line Item | Key Analysis Points |
|-----------|-------------------|
| Accounts Payable | Aging, payment terms, concentration, related party balances |
| Other Payables & Accruals | Nature breakdown, deferred revenue, customer deposits, IPO-related accruals |
| Tax Payables | Current year provision, prior year adjustments, assessment status |
| Bank Borrowings (Current) | Facility details, interest rates, covenants, repayment schedule, reclassification from non-current |
| Convertible Instruments | Terms, conversion triggers, classification (debt vs equity), accretion |

### Non-Current Liabilities
| Line Item | Key Analysis Points |
|-----------|-------------------|
| Bank Borrowings (Non-Current) | Maturity profile, secured/unsecured, fixed/floating rate mix |
| Lease Liabilities | Maturity analysis, discount rate, modifications |
| Other Non-Current Liabilities | Nature, contingent consideration, deferred tax liabilities |

## Income Statement Analysis

### Revenue Analysis
- **Decomposition** — break revenue into segments, channels, and revenue types
- **Growth drivers** — organic growth vs. acquisition vs. price increases vs. volume
- **Quality assessment** — recurring vs. one-off, concentration risk, sustainability
- **Revenue recognition** — timing of recognition (point-in-time vs. over time), deferred revenue adequacy
- **Cliff risk** — revenue streams that may not recur (e.g., one-off licensing fees)

### Cost Analysis
- **COGS/Cost of Revenue** — gross margin trend, cost composition, operational leverage
- **Operating Expenses** — fixed vs. variable, scalability, headcount-to-revenue ratio
- **Finance Costs** — interest by facility type, effective interest rate, lease interest separation
- **Depreciation & Amortization** — useful life assumptions, consistency, benchmark to capex

### Profitability Metrics
- Gross margin and trend
- EBITDA margin (adjusted for one-offs)
- Net profit margin
- Quality of earnings adjustments (non-recurring items, related party adjustments, accounting policy changes)

## Cash Flow Analysis

### Operating Activities
- Net income to operating cash flow reconciliation
- Working capital movement analysis
- Non-cash item addbacks (D&A, impairment, share-based compensation)
- Cash conversion ratio (Operating CF / EBITDA)

### Investing Activities
- Capital expenditure breakdown (maintenance vs. growth)
- Acquisition/disposal of subsidiaries or investments
- Intangible asset development spending

### Financing Activities
- Debt drawdown and repayment
- Equity issuance and buybacks
- Dividend payments
- Capital contributions

### Free Cash Flow
- FCF = Operating CF - Capital Expenditures
- FCF trend and adequacy for debt service
- FCF vs. net income comparison (earnings quality indicator)

## Key Financial Ratios

### Liquidity
| Ratio | Formula | Healthy Range |
|-------|---------|--------------|
| Current Ratio | Current Assets / Current Liabilities | > 1.0 |
| Quick Ratio | (Current Assets - Inventory) / Current Liabilities | > 0.8 |
| Cash Ratio | Cash / Current Liabilities | > 0.2 |

### Profitability
| Ratio | Formula |
|-------|---------|
| Gross Margin | Gross Profit / Revenue |
| EBITDA Margin | EBITDA / Revenue |
| Net Margin | Net Income / Revenue |
| ROA | Net Income / Total Assets |
| ROE | Net Income / Shareholders' Equity |

### Leverage
| Ratio | Formula | Warning Threshold |
|-------|---------|------------------|
| Debt-to-Equity | Total Debt / Total Equity | > 2.0 |
| Net Debt-to-EBITDA | (Total Debt - Cash) / EBITDA | > 3.5 |
| Interest Coverage | EBITDA / Finance Costs | < 3.0 |

### Efficiency
| Ratio | Formula |
|-------|---------|
| AR Days | (Accounts Receivable / Revenue) x 365 |
| AP Days | (Accounts Payable / COGS) x 365 |
| Inventory Days | (Inventory / COGS) x 365 |
| Cash Conversion Cycle | AR Days + Inventory Days - AP Days |
| Asset Turnover | Revenue / Total Assets |

## Focus Areas Table

For material line items, the DD report includes a Focus Areas table with columns:
| Column | Description |
|--------|------------|
| Focus Area | The balance sheet / P&L item or topic |
| Observations | Key data points and factual findings |
| DD Assessment | Professional judgment on risk, classification, or adequacy |
| Recommended Mitigations / Next Steps | Actionable suggestions for management |

## Analytical Writing Style

- Lead with the **quantified change** (e.g., "+103% from MYR 7,522k to MYR 15,291k")
- Follow with the **business driver** explaining the change
- Use professional, objective language appropriate for underwriter/investor audience
- Flag concerns clearly but avoid alarmist tone
- Use **underlined bold headers** for each line item analysis
- Reference specific amounts consistently in the reporting currency (e.g., "MYR 5,340k" not "approximately 5.3 million")
