# Valuation Module — v1 Implementation Status

Live tracking of the v1 build for the Orionmano valuation report module. **Deliverable format: Excel workpaper** (per client requirement — they export the workpaper as the deliverable, not a PDF/Word report). The narrative report template at `../05-report-templates/05-valuation-report.md` becomes a secondary output derived from the workpaper.

## 1. Architecture

```
+-----------------------+        +---------------------------+        +---------------------+
|  Customer data        |  --->  |  Backend agentic skill    |  --->  |  JSON inputs        |
|  (audited FS, mgmt    |        |  system (TODO)            |        |  conforming to      |
|  projections, etc.)   |        |                           |        |  schema contract    |
+-----------------------+        +---------------------------+        +---------------------+
                                                                                |
                                                                                v
                                                              +-----------------------------+
                                                              |  export_workpaper.py        |
                                                              |  (JSON -> populated xlsx)   |
                                                              +-----------------------------+
                                                                                |
                                                                                v
                                                              +-----------------------------+
                                                              |  Skeleton xlsx              |
                                                              |  (24 sheets, 112 named      |
                                                              |   ranges, no formulas yet)  |
                                                              +-----------------------------+
                                                                                |
                                                                                v
                                                              +-----------------------------+
                                                              |  Populated xlsx             |
                                                              |  (Inputs filled, audit      |
                                                              |   trail wired)              |
                                                              +-----------------------------+
                                                                                |
                                                                                v
                                                              +-----------------------------+
                                                              |  Formulas pass (TODO)       |
                                                              |  -> Working workpaper       |
                                                              +-----------------------------+
```

## 2. File inventory

### Specification documents (`knowledge-base/04-valuation/`)

| File | Purpose |
|---|---|
| `valuation-framework.md` | Methodology guide — DCF / CoCo / Precedent / NAV, WACC build, multiples |
| `valuation-model-reference.md` | Sheet-by-sheet structure of the reference TP workpaper |
| `financial-modeling.md` | Modeling conventions |
| **`project-tp-calc-graph.md`** | Reverse-engineered formula spec from the real client TP workpaper — every computed value, dependency, and broken `#REF!` link |
| **`inputs-sheet-schema.md`** | Schema for the v1 Inputs sheet — every parameter, type, JSON contract, source-citation pattern |
| **`broken-refs-audit.md`** | Audit of all 985 `#REF!` errors in TP vs the v1 schema; coverage 99% |
| **`v1-implementation.md`** | This file — implementation status & file inventory |

### Build artifacts (`backend/valuation/`)

| File | Purpose | Status |
|---|---|---|
| `build_skeleton.py` | Generates the v1 skeleton xlsx from the schema (data-driven) | ✓ done |
| `export_workpaper.py` | JSON → populated xlsx pipeline; runs validation + audit trail | ✓ done |
| `sample_inputs.json` | Worked example fixture (Singapore tech IPO scenario) | ✓ done |

### Output artifacts (`materials/templates/`)

| File | Purpose | Status |
|---|---|---|
| `orionmano-valuation-template-v1.xlsx` | The skeleton — 24 sheets, 112 named ranges, no formulas | ✓ built (~30 KB) |
| `out/sample-valuation.xlsx` | Test export from sample_inputs.json | ✓ verified |

### Reference materials (`materials/`)

| File | Purpose |
|---|---|
| `260318 Project TP - Valuation Model.xlsx` | The actual Orionmano client workpaper — structural source of truth |
| `references/damodaran-amazon-sept2018.xlsx` | Damodaran Amazon DCF — driver-input pattern + R&D / lease adjusters |
| `references/damodaran-aramco-ipo.xlsx` | Damodaran Aramco IPO — source-of-data audit trail pattern |

External reference exemplar list (SEC fairness opinions, Damodaran, Delaware Chancery): `~/AI-OS/wiki/concepts/us-valuation-report-exemplars.md`

## 3. Skeleton xlsx — sheet inventory

| # | Sheet | Status |
|---:|---|---|
| 1 | README | placeholder |
| 2 | Dashboard | placeholder |
| 3 | **Inputs** | **populated; calculated cells (levered_beta / Ke / Kd_at / WACC) cycle from WACC sheet** |
| 4 | **Historical FS** | **wired — IS + BS table with FY-5..FY-1 columns; auto-populated from `historical_fs` JSON block (31 line items)** |
| 5 | **Projections** | **wired — Y0 base (`revenue_y0` / `nwc_y0`) + Y1-Y5 cascade driven by Inputs named ranges** |
| 6 | **DCF** | **wired — discount mechanics + Gordon Growth/Exit Multiple terminal + EV** |
| 7 | **DCF (Independent)** | **wired — same formulas with `wacc_indep`** |
| 8 | **Comps** | **wired — apply CoCo Q1/Median/Q3 to Y1 metrics; cross-check vs DCF** |
| 9 | Precedent | placeholder (precedents pulled into Football Field row instead) |
| 10 | **Football Field** | **wired — DCF range across scenarios + Comps combined + Precedent + weighted-avg EV + selected band** |
| 11 | **WACC** | **wired — Ke build, levered beta, after-tax Kd, capital-weighted WACC for both scenarios** |
| 12 | Beta Analysis | placeholder |
| 13 | **CoCo Selection** | **wired — full mirror of Inputs cocos_table with calculated unlevered beta** |
| 14 | **CoCo Multiples** | **wired — auto-populated from `coco_multiples[]` JSON; Min/Q1/Median/Mean/Q3/Max stats + tier-filtered means** |
| 15 | **CoCo Margins** | **wired — auto-populated from `coco_margins[]` JSON; same stats pattern** |
| 16 | **CoCo Ratios** | **wired — auto-populated from `coco_ratios[]` JSON; same stats pattern** |
| 17 | CIQ Data Timeline | placeholder |
| 18 | **Country ERP** | **wired — 31-jurisdiction Damodaran ref table (mid-2025 ERP/CRP/tax) — refresh annually** |
| 19 | **Industry Averages** | **wired — 79-industry Damodaran US reference table (mid-2025 unlevered β / margins / capex / EV/EBITDA NTM) — refresh annually** |
| 20 | **Adjustments** | **wired — EV → Equity bridge, DLOM, DLOC, client interest** |
| 21 | **Sensitivity** | **wired — 7×7 grid (WACC × terminal g) recomputing EV from Projections FCFF** |
| 22 | R&D + Lease Adj | placeholder |
| 23 | **Valuation Summary** | **wired — headline values across scenarios + per-share (basic & diluted) with unit-aware conversion** |
| — | _dropdowns | hidden, holds data validation lists |

## 4. Inputs sheet — current state

- **70 scalar parameters** across 12 sections (A-L, no G/H since those are tables)
- **23 scenario-suffixed parameters** (`*_per_mgmt` + `*_indep`) for WACC build
- **30 year-vector parameters** for projections (6 stems × 5 years)
- **2 tabular blocks:** `cocos_table` (30 rows × 11 columns), `precedents_table` (15 rows × 9 columns)
- **8-column band per parameter:** id / Parameter / Type / Value (Per Mgmt) / Value (Independent) / Source / Source detail / Notes
- **Dropdowns wired** on: Source (11 options: Audited FS / Management Projections / Capital IQ / Bloomberg / Damodaran / Kroll / Mercer / Prospectus / Engagement Letter / Calculated / Manual), boolean params

## 5. How to run

### Build the skeleton
```bash
cd /Users/ariuslee/Projects/orionmano
python3 backend/valuation/build_skeleton.py
# -> materials/templates/orionmano-valuation-template-v1.xlsx
```

### Export populated workpaper from JSON
```bash
python3 backend/valuation/export_workpaper.py \
  --json backend/valuation/sample_inputs.json \
  --output materials/templates/out/sample-valuation.xlsx
```

The exporter rebuilds the skeleton automatically if missing. Validation errors block the export; warnings are logged but allow the export to proceed.

## 6. JSON contract

See `inputs-sheet-schema.md` §5 for the full contract. Top-level keys:

```
engagement, currency, tax, projections, terminal, wacc,
cocos[], precedents[], bridge, adjustments,
football_field, sensitivity, sources
```

Every parameter has a paired `sources.<id>` entry: `{ source, detail, notes }` for the audit trail. The exporter writes that metadata into columns F/G/H of the Inputs sheet alongside the value.

## 7. Implementation roadmap

| Phase | Status | Description |
|---|---|---|
| Schema design | ✓ done | Inputs schema + JSON contract specified |
| Broken-ref audit | ✓ done | 985 `#REF!` cells classified vs schema |
| Skeleton build | ✓ done | 23 sheets + named ranges + Inputs band + dropdowns |
| Export pipeline | ✓ done | JSON → populated xlsx with audit trail |
| Formulas — Projections sheet | ✓ done | Revenue / margins / opex / capex / NWC / FCFF driven by Inputs named ranges |
| Formulas — WACC sheet | ✓ done | Per-Mgmt + Independent scenarios; levered β, Ke, Kd_after_tax, WACC; cycle-back to Inputs |
| Formulas — DCF + DCF (Independent) | ✓ done | FCFF schedule, discount, Gordon Growth + Exit Multiple terminal, EV |
| Formulas — Adjustments + Valuation Summary | ✓ done | EV→Equity bridge, DLOM, DLOC, client interest, per-share (basic + diluted) |
| Formulas — CoCo sheets | ✓ done | CoCo Selection mirror + Multiples / Margins / Ratios with summary stats + tier-filtered means |
| Formulas — Comps cross-check | ✓ done | Apply CoCo NTM medians (Q1/Median/Q3) to target Y1 metrics; compare implied EV vs DCF |
| Formulas — Football Field | ✓ done | DCF range across scenarios + Comps combined + Precedent + weighted-average EV + selected band |
| Formulas — Sensitivity grid | ✓ done | 7×7 grid recomputing EV from Projections FCFF for each (WACC, terminal g) combination |
| Historical FS sheet | ✓ done | IS + BS manual-entry rows with derived NWC / net-debt; FY-5..FY-1 columns |
| Bundled Country ERP reference data | ✓ done | 31-jurisdiction Damodaran mid-2025 ERP/CRP/tax-rate table baked into skeleton |
| Backend integration — FastAPI endpoint | ✓ done | `POST /api/v1/companies/{id}/valuation/{generate-workpaper, produce-inputs}` |
| Agentic skill — Inputs producer | ✓ done | `produce_valuation_inputs` skill — Anthropic Claude Opus 4.7 + cached schema doc |
| Agentic skill — workpaper chain | ✓ done | `generate_valuation_workpaper` — chains producer → exporter, returns `/uploads/...` URL |
| Industry Averages reference data | ✓ done | 79-industry Damodaran US bundle (mid-2025 approximation; refresh annually) |
| Y0 base values (`revenue_y0` / `nwc_y0`) | ✓ done | Schema + producer + exporter; Projections!C8/C27 wire via named ranges |
| Historical FS auto-population | ✓ done | 31-field 5-year JSON block writes into Historical FS!C7:G44 |
| CoCo metric auto-population | ✓ done | `coco_multiples[]` / `coco_margins[]` / `coco_ratios[]` arrays write into the three CoCo sheets cols E+ |
| Source-completeness validation | ✓ done | Exporter warns on any high-priority parameter that has a value but no `sources.<id>` entry |
| Tier-3 size-cap rule for CoCos | ✓ done | Producer prompt enforces ≤10× target EV; schema documents methodology |
| Dashboard rollup | TODO | Cosmetic top-level summary view consolidating Valuation Summary highlights |
| R&D + Lease adjustment formulas | TODO | Off by default; toggle via `capitalize_rd` and `convert_operating_leases` |
| Independent projection drivers | TODO (v2) | Per-Mgmt vs Independent currently differ only on WACC; full independent FCFF needs `Projections (Independent)` sheet |

## 8. Hand-verified expected outputs (sample_inputs.json)

When the user opens `materials/templates/out/sample-valuation.xlsx` in Excel and fills the two manual Y0 base cells on the Projections sheet (`C8` revenue Y0, `C27` NWC Y0), the formulas should compute these values for the Per-Management scenario:

| Metric | Expected | Source |
|---|---:|---|
| Levered beta | 1.2243 | WACC sheet |
| Cost of equity (Ke) | 15.73% | WACC sheet |
| After-tax Kd | 4.98% | WACC sheet |
| **WACC** | **13.91%** | WACC sheet |
| FCFF Y1 (with Y0 rev=100,000, NWC=8,000) | -2,890 | Projections!D36 |
| FCFF Y5 | 51,448 | Projections!H36 |
| Sum of PV of explicit FCFF | 73,881 | DCF!I25 |
| Terminal value (Gordon, g=3%) | 485,917 | DCF!I19 |
| PV of terminal | 253,418 | DCF!I22 |
| **Enterprise Value** | **327,299** USD'000 | DCF!I27 |
| Equity value (pre-discounts) | 352,299 | Adjustments!C12 |
| After DLOM (20%) | 281,839 | Adjustments!C17 |
| After DLOM and DLOC (15%) | 239,563 | Adjustments!C20 |
| **Per share (basic, $/sh)** | **$0.96** | Valuation Summary!C16 |

Hand-verification script: `python3 -c "..."` block that reproduced these is in the agent transcript; reproduce by re-running with the inputs above.

## 9. Open questions parked for client confirmation

From `inputs-sheet-schema.md` §8:
1. Scenario columns vs sheet clones — TP uses clones; v1 uses side-by-side columns. Acceptable to client?
2. Tax rule shape — is HK two-tier intentional or accidental?
3. CoCo data source — Capital IQ feed, manual, or SEC EDGAR XBRL?
4. Default equity interest = 100% or partial stakes the norm?
5. R&D / lease adjustment defaults given typical client target profile?
