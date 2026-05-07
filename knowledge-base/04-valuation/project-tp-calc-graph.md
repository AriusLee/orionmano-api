# Project TP — Calculation Graph

Reverse-engineered specification of the formulas inside `materials/260318 Project TP - Valuation Model.xlsx` (the actual Orionmano client workpaper). Documents what each computed value is, what it depends on, and which links are broken — so the v1 AI-generated template can reproduce every computation TP performs without losing any logic.

**Scope:** Data-only. Cosmetics, named ranges, conditional formatting, and chart wiring are out of scope.

## 1. Headline metrics

| Metric | Sheet | Cell | Status |
|---|---|---|---|
| Total cells with content | — | — | 22,273 |
| Formulas | — | — | 11,296 |
| Hardcoded numbers | — | — | 5,410 |
| `#REF!` errors | — | — | **985** |

Broken refs concentrate in the value-summary / CoCos-data / Table sheets — exactly the layers the v1 rebuild must replace.

## 2. Sheet dependency layers

```
L0 (raw input):        Income Stmnt   Balance Sheet   Revenue breakdown comparison
                              ↓               ↓
L1 (consolidation):    Historical FS   BS nature
                              ↓
L2 (core compute):     Value summary  Value summary alt   ← read FS, write DCF
                              ↑                    ↑
L2 (parallel):         WACC (final)  WACC.Analysis (final)   Discount rate
                              ↑
L2 (CoCo data):        CIQ.DataTimeline   →   Multiples   Margins   Ratios   CoCos Data   AUM-extracted
                                                  ↓
L3 (cross-check):      Implied multiples   ←   Value summary
                              ↓
L3 (aggregator):       Table   Chart data   MultiVD FP summary
                              ↓
L4 (output):           Dashboard   Dashboard_UserGide
```

Top dependency edges (formula reference counts):
- `Chart data` ← `MultiVD FP summary` (147), `Margins (final)` (54), `Multiples (final)` (51)
- `Table` ← `Value summary` (88), `Multiples (final)` (85), `CoCos Data` (44)
- `Value summary` ← `Historical FS` (55)
- `Value summary alt` ← `Historical FS` (72)
- `CoCos Data` ← `AUM-extracted` (225) — sector-specific, drop in v1
- `Discount rate` ← `WACC (final)` (33)

## 3. Canonical formulas — DCF mechanics (`Value summary`)

The DCF block lives at rows 14-39 of `Value summary`. Years run across columns G-N (or wider), with hardcoded historicals in G:I and projected in J:N+.

### 3.1 Revenue projection
```
H16 = =25535282/1000              ← hardcoded prior year (USD'000 from raw)
J16 = =SUM('Income Stmnt'!D3:D5)/1000   ← consolidated from Income Stmnt
K16 = =J16 * (1 + K$11)           ← projected: prior × (1 + growth assumption row 11)
```
**Driver:** row 11 holds revenue growth rate per year.

### 3.2 Tax — two-tier HK profits tax (jurisdiction-specific)
```
J24 = =IF(J23>2000, -2000*$E$24 - (J23-2000)*$F$24, -J23*$E$24)
```
- `$E$24` = first-tier rate (~8.25% in HK)
- `$F$24` = standard-tier rate (~16.5% in HK)
- Threshold = 2000 (HKD'000) hardcoded
- **v1 rebuild note:** parameterize tax rule on Inputs sheet — flat vs tiered, threshold, two rates. Asia-Pac jurisdictions vary (PRC 25% flat with HNTE at 15%, SG 17% flat, MY 24% flat with SME tiers, KR tiered).

### 3.3 FCFF construction (rows 27-33)
```
EBIT (row 27)        K27 = =K23
Less: Tax (row 28)   K28 = =K24
Add: Dep (row 29)    [— row exists, formulas blank in extracted sample —]
Less: Capex (row 30) [— row exists, formulas blank in extracted sample —]
Less: ΔWC (row 31)   [— row exists, formulas blank in extracted sample —]
FCFF (row 33)        K33 = =SUM(K27:K31)
```

### 3.4 Partial-year discount mechanics (rows 36-38)
```
Partial year     K36 = =IF(K14<YEAR($F$9), 0,
                           IF(K14=YEAR($F$9), YEARFRAC($F$9, DATE(K14,12,31)),
                              1))
Discount period  K37 = =IF(AND(K36, NOT(J37)), K36,
                           IF(AND(K36, NOT(I37)), J36+K36,
                              IF(K36=1, K37+1, 0)))
                 M37 = =L37 + M36                (accumulator after stub year)
Discount factor  K38 = =1 / (1 + $E$38)^K37
PV of FCFF       K39 = =K33 * K38
```
- `$F$9` = valuation date (e.g. 2024-12-31)
- `K14` = year header
- `$E$38` = WACC (the discount rate input — sourced from `Discount rate` sheet)
- **v1 rebuild note:** the partial-year logic is correct and worth keeping. Drop the `#REF!` fallback branch in `K37`.

### 3.5 Operational ratio outputs (rows 48-49)
```
Opex % rev   K48 = =-K19/K18
Capex % rev  K49 = =K30/K$18
```
Used as sanity checks in Dashboard charts.

## 4. EV → Equity bridge (`Value summary` rows 62-69)

```
B62  Add: Surplus assets/liab.       (row 62 — typically 0 or hardcoded from BS nature)
B64  Add: Net cash                   E64 = =SUM('Balance Sheet'!B15)/1000
B65  Equity value before DLOC/DLOM   E65 = =E63 + E64
B66  Less: DLOC                      D66 = #REF!  ← BROKEN (rate parameter lost)
                                     E66 = =-E65 * $D$66
B67  100% equity value after DLOC    E67 = =SUM(E65:E66)
B68  Less: DLOM                      D68 = #REF!  ← BROKEN (rate parameter lost)
                                     E68 = =-E67 * $D$68
B69  100% equity value after both    E69 = =SUM(E67:E68)
                                     F69 = =E69 - #REF!/1000   ← BROKEN
```

**Critical finding:** the DLOC and DLOM **rates** themselves are broken `#REF!`. The application logic (`-base × rate`) works, but the rate input is gone. In v1, DLOM and DLOC must be explicit named inputs on the Inputs sheet (typical ranges: DLOM 10-30%, DLOC 10-30%, sometimes combined 20-40%).

## 5. WACC — `WACC (final)` sheet

The WACC sheet uses a tier-flag pattern for comparable selection:
```
U15 = =IFERROR(IF(D15, (A15*1 + B15*2 + C15*3), "Excluded"), "")
```
Columns A/B/C are tier flags (Tier 1 / 2 / 3), D is a global include flag. The encoded tier number drives downstream `AVERAGEIFS` calls in `Multiples (final)` etc.

The actual Ke build-up is in the same sheet but extracted via grid layout — formulas in WACC build are clean (zero `#REF!` in sheet 15). Formula heads dominated by `IFERROR` (333), letter-prefixed cell anchors (`F` 145, `G` 120, `H` 120) — column-anchored summary stats over the comp table.

The selected-WACC consolidation lives on `Discount rate`:
```
D62 = =D52*D61 + D58*D60        ← WACC = Ke × (E/V) + Kd_aftertax × (D/V)  [low scenario]
E62 = =E52*E61 + E58*E60        ← same formula, high scenario
C62 = =AVERAGE(D62:E62)         ← base case = mid of range
```
- D52, E52 = Ke (low / high)
- D61, E61 = E/V (low / high)
- D58, E58 = Kd × (1−T) (low / high)
- D60, E60 = D/V (low / high)

**v1 rebuild note:** standard WACC formula, parameterize Rf, ERP, beta range, size premium, specific risk premium, Kd, tax rate, capital structure on Inputs sheet. The two-scenario range pattern (low/high) is worth keeping — it's what produces the Per-Mgmt vs Independent split.

## 6. CoCo multiples aggregation — `Multiples (final)`

Grid is `J12:CR41` (~30 rows of comparable companies × multiple metric columns). Per-metric summary stats:
```
Maximum     J42 = =IFERROR(MAX(J$12:J$41), "n/a")
Minimum     J43 = =IFERROR(MIN(J$12:J$41), "n/a")
Median      J45 = =IFERROR(MEDIAN(J$12:J$41), "n/a")
```
Tier-filtered means:
```
Tier-1 mean   J49 = =AVERAGEIFS(J$12:J$41, $CR$12:$CR$41, 1)
Tier-2 mean   J50 = =AVERAGEIFS(J$12:J$41, $CR$12:$CR$41, 2)
Tier-3 mean   J51 = =AVERAGEIFS(J$12:J$41, $CR$12:$CR$41, 3)
```
where `$CR` holds the encoded tier number from `WACC (final)!U15` formula (replicated per CoCo).

Same pattern repeats in `Margins (final)` and `Ratios (final)` (444 / 360 formulas, both `AVERAGEIFS`-dominated).

**v1 rebuild note:** this pattern is reproducible cleanly. Keep the Min/Max/Median as the headline range, plus tier-filtered means as the "high quality CoCo subset" view.

## 7. Implied multiples cross-check — `Implied multiples`

```
B24  Equity value before DLOC               C24 = ='Value summary'!E65
B25  Equity value after DLOC, before DLOM   C25 = ='Value summary'!E67
B26  Equity value after DLOC and DLOM       C26 = ='Value summary'!E69

B32  EV/Sales                               C32 = #REF!     ← BROKEN (headline EV missing)
                                            D32 = =$C$23 / 'Value summary'!J18
                                            E32 = =$C$23 / 'Value summary'!K18
B33  EV/EBITDA                              D33 = =$C$23 / 'Value summary'!J21
B34  P/E                                    D34 = =$C$26 / 'Value summary'!J25
```

**Critical finding:** column C of rows 32-34 holds the headline EV/Equity numbers for ratio computation, but they're `#REF!`. The year-by-year ratios (cols D:F) work because they reference `$C$23` (a separate EV constant) — likely the post-tax EV from DCF that was supposed to be linked but got broken in an edit.

**v1 rebuild note:** make the EV pull explicit — `=DCF!{ev_cell}` — and run implied EV/Sales, EV/EBITDA, P/E for each historical and projected year. Compare against `Multiples (final)` summary stats (Min/Median/Max) for sanity check.

## 8. Broken-link rebuild list

The 985 `#REF!` errors fall into these recoverable patterns:

| Pattern | Sheets affected | Likely original target | v1 fix |
|---|---|---|---|
| DLOM / DLOC rates | `Value summary`, `Value summary alt`, `Implied multiples`, `Table` | Named cell on Inputs sheet | Define `DLOM_pct`, `DLOC_pct` as Inputs parameters |
| Discount-period stub year fallback (`K37` branch) | `Value summary`, `Value summary alt` | Prior column's discount period | Drop fallback branch — the main two branches cover all cases |
| Headline EV pull on Implied multiples | `Implied multiples` C32:C34 | DCF EV result on Value summary | Direct `=Value summary!E61` (or wherever DCF EV lands) |
| AUM-extracted comparison links | `CoCos Data` (225 refs) | Sector-specific comp data — DROP | Don't carry AUM-extracted into v1; it was for PE-fund target |
| Historical FS row anchors | `Historical FS` (117 refs) | Cell anchors that moved during edits | Rebuild from `Income Stmnt` / `Balance Sheet` deterministically |
| Table aggregator pulls | `Table` (166 refs) | Fragile cell anchors across sheets | Rebuild Table to reference current Value summary cells only |

## 9. v1 build implications

**Keep and reproduce:**
1. Two-scenario WACC range (Per Mgmt + Independent) → produces Per Mgmt + Parallel value summaries
2. Partial-year discount mechanics (YEARFRAC stub + accumulator)
3. Tier-flagged CoCo selection driving AVERAGEIFS aggregations
4. EV → Equity bridge with surplus / net debt / DLOM / DLOC layered application
5. Implied multiples cross-check against CoCo Min/Median/Max
6. Multi-currency support (USD'000 primary, HKD'000 alternate)

**Reparameterize (move to Inputs sheet):**
- DLOM rate
- DLOC rate
- Tax rule (jurisdiction + flat-vs-tiered + thresholds)
- WACC components (Rf, ERP, beta range, size premium, specific risk, Kd, tax rate, D/E)
- Terminal growth rate
- Revenue growth assumptions per year
- Capex % of revenue, Working capital % of sales
- Currency + unit

**Drop:**
- `AUM-extracted` (sector-specific to PE funds)
- All `#REF!` chains that reference deleted sheets
- The hardcoded 2000-HKD'000 tax threshold (parameterize)
- The `Value summary alt` clone — instead, make scenario a column on a single Value summary sheet

**Add (gap vs Damodaran + SEC fairness opinions):**
- Football Field reconciliation sheet (DCF range vs CoCo range vs Precedent range, weighted)
- Precedent transactions sheet
- R&D capitalization toggle (for tech/SaaS Asia-Pac targets — Damodaran pattern)
- Operating lease conversion toggle (Damodaran pattern)
- Country ERP reference data sheet (for FPI valuations — Damodaran pattern)
- "Source of data" column on Inputs sheet (Damodaran Aramco pattern — every input cited to audited FS / management / prospectus / Capital IQ)

## 10. References

- Source workpaper: `/Users/ariuslee/Projects/orionmano/materials/260318 Project TP - Valuation Model.xlsx`
- Structural map (sheet inventory): see Section 2 above
- Reference benchmarks: `materials/references/damodaran-amazon-sept2018.xlsx`, `damodaran-aramco-ipo.xlsx`
- Adjacent docs: `valuation-framework.md`, `valuation-model-reference.md`, `../05-report-templates/05-valuation-report.md`
- External exemplar list: `~/AI-OS/wiki/concepts/us-valuation-report-exemplars.md`
