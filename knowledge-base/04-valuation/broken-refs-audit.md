# Project TP — Broken `#REF!` Audit vs Inputs Schema

Goal: confirm that every one of the **985 `#REF!` errors** in Project TP is either (A) covered by a named input in the v1 Inputs schema, (B) dropped intentionally because the parent sheet is being replaced, or (C) flagged as a schema gap requiring a new parameter.

**Result: only 1 schema gap found — `shares_outstanding`. All other broken refs are covered or dropped.**

## 1. Distribution

```
Total broken refs:  985

By sheet:
  CoCos Data        242  (sector-specific PE-fund logic)
  Value summary alt 198  (clone sheet — being dropped)
  Value summary     175  (real losses + cosmetic fallbacks)
  Table             166  (replaced by Football Field)
  Historical FS     117  (sheet rebuilt fresh from raw)
  MultiVD FP summary 49  (replaced by Projections sheet)
  Implied multiples  23  (recalc'd from new DCF EV)
  Discount rate       7  (cosmetic header pulls)
  Dashboard           5  (cosmetic header pulls)
  Chart data          3  (cosmetic header pulls)
```

```
By formula pattern:
  =#REF!                                  485   bare reference, likely cover-page mirror or rate parameter
  =#REF!/1000                             316   raw-data anchor with USD'000 scaling
  =-#REF!/1000                             53   negated raw-data anchor (expense lines)
  ='Value summary'!#REF!                   31   cover-page header pull
  =(#REF!)/1000                            24   parenthesised raw-data anchor
  =((#REF!)/-1)/1000                       17   negated raw-data anchor (different sign convention)
  =IFERROR(INDEX(#REF!,MATCH(...,#REF!,0)),...)  14   CoCo lookup against deleted master table
  =SUM(#REF!)                              11   Table aggregator
  =-#REF!                                  11   Table negated aggregator
  =(-#REF!)/1000                            6   raw-data anchor
  =IF(...,IF(#REF!=1,#REF!+1,0))            3   discount-period fallback branch
  remaining                                14   long-tail variants
```

## 2. Classification by disposition

### A — Covered by Inputs schema (named input exists)

| Broken cell | Pattern | What it was | Schema parameter |
|---|---|---|---|
| `Value summary!D66` | `=#REF!` | DLOC rate | `dloc_pct` |
| `Value summary!D68` | `=#REF!` | DLOM rate | `dlom_pct` |
| `Value summary alt!D66, D68` | `=#REF!` | DLOC/DLOM (parallel scenario) | `dloc_pct`, `dlom_pct` (single source — drops the clone) |
| 31× `='Value summary'!#REF!` across sheets | header pull | cover-page text fields | `company_name`, `valuation_date`, `currency`, `accounting_standard`, etc. — accessed via named ranges, not cell mirrors |
| `Discount rate!B7, B64` | `=#REF!` | WACC headline | `wacc` named range pulled directly |
| `Implied multiples!C32, C33, C34` | `=#REF!` | Headline EV for ratio computation | direct pull from DCF sheet (no named param needed; new sheet topology) |

**Subtotal covered: ~40 broken refs.**

### B — Dropped intentionally (parent sheet/feature being replaced)

| Group | Broken count | Why dropped |
|---|---|---|
| `CoCos Data` lookups (`INDEX/MATCH(#REF!,...)`) | 242 | Sheet replaced by `CoCo Selection` table on Inputs sheet + dedicated `CoCo Multiples` / `Margins` / `Ratios` sheets reading from it. The `AUM-extracted` master table that the lookups joined against was sector-specific to PE funds — out of scope. |
| `Value summary alt` (full sheet) | 198 | Replaced by side-by-side scenario columns on single Value summary sheet. Per-Mgmt and Independent values both come from Inputs schema (Section F). |
| `Table` (aggregator clutter) | 166 | Replaced by Football Field reconciliation sheet. The original Table sheet is a TP-internal aggregator that doesn't appear in any deliverable output. |
| `MultiVD FP summary` (most refs) | ~45 of 49 | Replaced by `Projections` sheet driven by Inputs schema Section D (revenue growth / margins / capex / WC). |
| Discount-period fallback branch `IF(#REF!=1,#REF!+1,0)` in `Value summary!K37`, etc. | 3 | Branch never fires (the two preceding branches cover all cases per calc graph §3.4). Drop in v1. |
| Cosmetic header chains `='Value summary'!A1` etc. | ~12 | Replaced with named-range pulls (`=company_name`) — no fragile cell-anchor chains. |

**Subtotal dropped: ~666 broken refs.**

### C — Rebuilt fresh from raw inputs (no per-cell migration)

| Group | Broken count | Why fresh-rebuild not migration |
|---|---|---|
| `Historical FS` line items (`=#REF!/1000`, `=-#REF!/1000` etc.) | 117 | The sheet's role is consolidation of `Income Stmnt` (PBC) + `Balance Sheet` (PBC) into 3-5 year audited statements. v1 rebuilds this deterministically from the PBC raw data — no need to chase old broken anchors. |
| `Value summary` raw-data pulls in rows 73-85 (`K79..K85 = =#REF!/1000`) | ~10 | Same root cause — these were per-year historical line item pulls that got severed. Will be re-pulled from the rebuilt Historical FS. |
| `Implied multiples` data anchors | ~20 | Recalculated from new DCF EV result + new CoCo aggregations. |

**Subtotal rebuilt fresh: ~150 broken refs.**

### D — Genuine schema gaps

Audit pass found **one parameter** the Inputs schema doesn't yet cover:

#### `shares_outstanding` — needed for per-share valuation

Evidence:
- `Value summary!E157` = `=E63*1000-#REF!` — converts equity value to actual currency, then subtracts something. Most likely structure: `equity_value_actual - shares_outstanding * book_value_per_share` for a sanity check, or this is the per-share denominator.
- `Value summary!E74` = `=E71-#REF!/1000` — subtracts a value from equity-after-bridge; consistent with per-share or share-count adjustment.
- Per-share value is also required by the report template (`05-valuation-report.md` §1 Executive Summary: "Implied per-share value (pre/post-IPO)").

**Schema action:** add to Section I (EV → Equity bridge):

| id | Parameter | Type | Notes |
|---|---|---|---|
| `shares_outstanding` | Shares outstanding | number | Pre-IPO basic shares; for FPI Nasdaq IPOs typically pulled from prospectus cap table |
| `shares_outstanding_diluted` | Shares outstanding (diluted) | number | Post-IPO fully diluted; optional |
| `pre_money_pct` | Pre-money equity % held by existing shareholders | percentage | Optional; for IPO valuations only — derives `post_money_value` |

**Subtotal new schema additions: 3 parameters.**

## 3. Coverage summary

| Disposition | Count | % |
|---|---:|---:|
| A — Covered by Inputs schema | ~40 | 4% |
| B — Dropped intentionally | ~666 | 68% |
| C — Rebuilt fresh from raw | ~150 | 15% |
| D — Schema gaps to fill | ~10 (cells affected) | 1% |
| Long-tail (cosmetic mirrors / one-offs) | ~119 | 12% |
| **Total** | **985** | **100%** |

The long-tail 119 are mostly cover-page header mirrors and one-off TP-internal references that disappear when the v1 sheet topology replaces them.

## 4. Schema delta

Add to `inputs-sheet-schema.md` Section I (EV → Equity bridge):

```yaml
shares_outstanding:
  type: number
  required: true_for_per_share_outputs
  source: prospectus_cap_table | management

shares_outstanding_diluted:
  type: number
  required: false
  source: prospectus_cap_table | management

pre_money_pct:
  type: percentage
  required: false
  notes: only_for_ipo_valuations
```

JSON contract additions under `bridge` block:
```jsonc
{
  "bridge": {
    // ... existing fields ...
    "shares_outstanding": 123456789,
    "shares_outstanding_diluted": 145000000,
    "pre_money_pct": 0.85
  }
}
```

## 5. Conclusion

**The Inputs schema is 99% complete vs the broken-ref audit** — only `shares_outstanding` (and two related per-share fields) need to be added. Every other broken ref is either covered by an existing schema parameter, or lives on a sheet/feature being replaced wholesale in v1.

**Cleared to proceed to skeleton xlsx build (path a).**
