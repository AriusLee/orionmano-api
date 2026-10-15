# Valuation model lifecycle — versions, locked history, Q&A, market data

Built 2026-10-15 for Eric's request: lock historical figures, tag uploads to a
period, answer counterparty questions against the model, and a "Market Data
Supported" report. The four pieces share one foundation: valuation versions.

## 0. Versions — `valuation_versions`

Every workpaper run (Generate, xlsx/JSON re-upload, Q&A change, restore) is a
row with its full `inputs`, computed `summary`, xlsx file and the report it
produced. One row per company is `active`; the rest are `superseded`.

- Written by `generate_valuation_workpaper` after the xlsx + `.summary.json`
  (those files are still written; downloads and old readers keep working).
- `/valuation/latest` returns the active version; `/valuation/versions`,
  `/versions/{id}`, `/versions/{id}/changes` (diff vs parent, incl. any moved
  historical figure), `/versions/{id}/restore` (appends a NEW version).
- Runs from before versions existed are imported lazily from the summary
  files on first access (`versions.import_legacy`).
- `reports.valuation_version_id` ties a valuation report to the version it
  explains; regenerating the report keeps that version.

## 1–2. Confirmed historical figures — `financial_periods` / `financial_figures`

One value per (period, line item), with source document and page.
`services/financials/catalogue.py` maps extraction keys onto line items and
says which feed `historical_fs` (sign: costs/liabilities negative).

- Extraction (`document_parser`) now marks PDF pages `[Page N]` and returns
  `financial_data.source_pages`.
- `store.sync_document` applies a document's figures:
  - tagged upload (`documents.target_period`) writes ONLY that period;
    other periods are comparatives → discrepancy if different, never written;
  - locked periods and hand-entered figures are never overwritten →
    discrepancy;
  - source rank: face statements (prospectus / audit / FS) > management
    accounts > other > schedules (leadsheet, breakdown… by filename). A
    lower-ranked document never overwrites a higher-ranked figure.
- Locking a period: the producer is told the slot mapping and the locked
  values, and `store.apply_plan` writes them into `historical_fs` (and the
  base-year `*_y0` values when FY-1 is locked) after the LLM, converting
  currency with the payload's own `fx_rate_alt` and unit. Pins still win.
- Amending a locked figure or unlocking needs a reason; everything is in
  `financial_figure_amendments`.
- Locked figures also lead the agent/report/KB contexts
  (`confirmed_context_block`).

## 3. Counterparty Q&A — `qa_batches` / `qa_items` / `qa_model_changes`

Questions pasted or uploaded (xlsx/docx/pdf/txt) → Claude drafts a simplified
and a detailed answer per question against the active version, and may
propose changes to PINNABLE_PARAMS keys. Each change shows its EV/equity
impact from `compute_summary` (deterministic, no LLM). Approve → apply:
changes are applied on top of the CURRENT active version through the
regenerate-from-inputs path → new version (`trigger=qa_change`,
`qa_item_id`) + its report, and the values are pinned on the company so a
later full Generate keeps them. Export to Excel / Word.

## 4. Market Data Supported report — `market_evidence`

For a version, each key assumption (growth, margins, terminal growth, Rf,
ERP, CRP, beta, size/specific premia, Kd, DLOM, DLOC) is checked with
Claude's `web_search_20250305` tool: assessment, market range, finding,
sources with URL + date. Then a `valuation_report` with
`variant = "market_supported"` is generated: it adds "Market Data Support
for Key Assumptions" (table + detail on anything not supported) and an
"Appendix — Market Data Sources" (S-numbered). The DuckDuckGo cached search
is unchanged and still used by the industry report.

## Startup

`main.py` reaps interrupted jobs like it does reports: `qa_items` stuck in
`applying`, `qa_batches` in `answering`, `market_evidence` rows `pending`.
