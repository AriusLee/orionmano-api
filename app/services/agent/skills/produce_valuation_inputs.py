"""Skill: produce a JSON object conforming to the valuation Inputs schema.

Reads company data + extracted document content from the AgentContext, calls
Claude with the schema spec as a cached system prompt, and parses the JSON
response. Output flows into GenerateValuationWorkpaperSkill which writes the
populated xlsx via export_workpaper.py.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import anthropic

from app.config import settings
from app.services.agent.context import AgentContext
from app.services.agent.skill import Skill, SkillResult
from app.services.agent.skills.valuation_inputs_schema import validate as validate_inputs


# Resolve from backend/ root (parents[4]) so the path holds in deploys that ship
# only the backend tree (e.g. Render). knowledge-base/ was moved into backend/
# for this reason — see also generate_valuation_workpaper.py and report/generator.py.
BACKEND_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = BACKEND_ROOT / "knowledge-base" / "04-valuation" / "inputs-sheet-schema.md"

# Make the standalone valuation module importable so we can compute the DCF EV
# in-loop for the goal-seek convergence check. Same trick used in
# generate_valuation_workpaper.py.
_VAL_DIR = BACKEND_ROOT / "valuation"
if str(_VAL_DIR) not in sys.path:
    sys.path.insert(0, str(_VAL_DIR))


_UNIT_MULTIPLIERS = {
    "": 1.0,
    "'000": 1_000.0,
    "000": 1_000.0,
    "'mm": 1_000_000.0,
    "mm": 1_000_000.0,
    "'000000": 1_000_000.0,
    "million": 1_000_000.0,
    "m": 1_000_000.0,
}


def _unit_multiplier(unit: str | None) -> float:
    """Convert a `currency.unit` string ('000 / 'mm / etc.) to its multiplier.
    Falls back to 1.0 on unknown units."""
    if not unit:
        return 1.0
    return _UNIT_MULTIPLIERS.get(unit.strip().lower(), 1.0)


def _implied_dcf_ev_actual(payload: dict) -> float | None:
    """Run compute_summary on the payload and return the per-management DCF EV
    scaled to ACTUAL currency units (multiplied by the workpaper's unit factor).
    target_valuation is in actual currency too, so this is the comparable value
    for the goal-seek convergence check. Returns None on any failure."""
    try:
        from compute import compute_summary  # type: ignore
        summary = compute_summary(payload)
        ev = summary.get("dcf", {}).get("per_management", {}).get("ev")
        if not isinstance(ev, (int, float)) or ev <= 0:
            return None
        unit = (payload.get("currency") or {}).get("unit")
        return float(ev) * _unit_multiplier(unit)
    except Exception:
        return None


# ─── Pinned overrides (Eric 2026-05-17) ──────────────────────────────────────
# Whitelist of analyst-pinnable parameters. Each entry maps a stable key to
# (dotted_path_in_payload, value_type). Type is informational — the frontend
# uses it to pick the right input widget; the backend coerces on apply.
PINNABLE_PARAMS: dict[str, tuple[str, str]] = {
    "revenue_y0":                 ("projections.revenue_y0",                    "currency"),
    "gross_profit_y0":            ("projections.gross_profit_y0",               "currency"),
    "opex_y0":                    ("projections.opex_y0",                       "currency"),
    "ebitda_y0":                  ("projections.ebitda_y0",                     "currency"),
    "ebit_y0":                    ("projections.ebit_y0",                       "currency"),
    "tax_y0":                     ("projections.tax_y0",                        "currency"),
    "net_income_y0":              ("projections.net_income_y0",                 "currency"),
    "revenue_growth_y1":          ("projections.revenue_growth.0",              "percent"),
    "revenue_growth_y2":          ("projections.revenue_growth.1",              "percent"),
    "revenue_growth_y3":          ("projections.revenue_growth.2",              "percent"),
    "revenue_growth_y4":          ("projections.revenue_growth.3",              "percent"),
    "revenue_growth_y5":          ("projections.revenue_growth.4",              "percent"),
    "revenue_growth_primary_y1":  ("projections.revenue_growth_primary.0",      "percent"),
    "revenue_growth_primary_y2":  ("projections.revenue_growth_primary.1",      "percent"),
    "revenue_growth_primary_y3":  ("projections.revenue_growth_primary.2",      "percent"),
    "revenue_growth_primary_y4":  ("projections.revenue_growth_primary.3",      "percent"),
    "revenue_growth_primary_y5":  ("projections.revenue_growth_primary.4",      "percent"),
    "gross_margin_y1":            ("projections.gross_margin.0",                "percent"),
    "gross_margin_y2":            ("projections.gross_margin.1",                "percent"),
    "gross_margin_y3":            ("projections.gross_margin.2",                "percent"),
    "gross_margin_y4":            ("projections.gross_margin.3",                "percent"),
    "gross_margin_y5":            ("projections.gross_margin.4",                "percent"),
    "terminal_growth_rate":       ("terminal.growth_rate",                      "percent"),
    "risk_free_rate":             ("wacc.shared.risk_free_rate",                "percent"),
    "equity_risk_premium":        ("wacc.shared.equity_risk_premium",           "percent"),
    "country_risk_premium":       ("wacc.shared.country_risk_premium",          "percent"),
    "unlevered_beta_pm":          ("wacc.per_management.unlevered_beta",        "number"),
    "size_premium_pm":            ("wacc.per_management.size_premium",          "percent"),
    "specific_risk_premium_pm":   ("wacc.per_management.specific_risk_premium", "percent"),
    "pretax_cost_of_debt_pm":     ("wacc.per_management.pretax_cost_of_debt",   "percent"),
    "dlom_pct":                   ("bridge.dlom_pct",                           "percent"),
    "dloc_pct":                   ("bridge.dloc_pct",                           "percent"),
    "shares_outstanding":         ("bridge.shares_outstanding",                 "number"),
    "shares_outstanding_diluted": ("bridge.shares_outstanding_diluted",         "number"),
}


def _apply_pinned_overrides(payload: dict, pinned: dict | None) -> list[str]:
    """Authoritatively write each pinned key into the payload, navigating the
    dotted path. Returns the list of applied keys (so calibration can skip
    them). Silently drops keys that aren't in PINNABLE_PARAMS."""
    if not pinned or not isinstance(pinned, dict):
        return []
    applied: list[str] = []
    for key, raw_value in pinned.items():
        spec = PINNABLE_PARAMS.get(key)
        if not spec:
            continue
        path, _type = spec
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            continue
        if value is None:
            continue
        parts = path.split(".")
        node: Any = payload
        # Walk to the parent of the leaf
        for i, p in enumerate(parts[:-1]):
            next_p = parts[i + 1]
            next_is_index = next_p.isdigit()
            if p.isdigit():
                idx = int(p)
                if not isinstance(node, list):
                    break  # type mismatch — skip
                while len(node) <= idx:
                    node.append([] if next_is_index else {})
                node = node[idx]
            else:
                if not isinstance(node, dict):
                    break
                node = node.setdefault(p, [] if next_is_index else {})
        else:
            # Set the leaf
            last = parts[-1]
            if last.isdigit():
                idx = int(last)
                if isinstance(node, list):
                    while len(node) <= idx:
                        node.append(None)
                    node[idx] = value
                    applied.append(key)
            else:
                if isinstance(node, dict):
                    node[last] = value
                    applied.append(key)
    return applied


def _pinned_array_indices(pinned_keys: list[str], array_key: str) -> set[int]:
    """Given a list of applied pinned keys and a target array name (e.g.
    'revenue_growth' or 'gross_margin'), return the set of indices that are
    pinned and must NOT be scaled by calibration."""
    indices: set[int] = set()
    for key in pinned_keys:
        spec = PINNABLE_PARAMS.get(key)
        if not spec:
            continue
        path = spec[0]
        # Match path like "projections.revenue_growth.K" or "projections.gross_margin.K"
        parts = path.split(".")
        if len(parts) == 3 and parts[1] == array_key and parts[2].isdigit():
            indices.add(int(parts[2]))
    return indices


def _find_previous_valuation_payload(company_id: Any, current_exchange: str | None) -> dict | None:
    """Eric 2026-05-18 — locate the most recent .summary.json for this company
    AND verify its engagement.exchange_platform matches the current target.
    Returns the previous run's inputs dict so callers can reuse its cocos
    section; None if no compatible prior run.

    Why: regenerates should NOT re-screen comps unless the analyst explicitly
    changes the target exchange. Reusing the comp set keeps the workpaper
    auditable and lets pinned_cocos toggles + manual edits survive."""
    if company_id is None:
        return None
    try:
        from app.config import settings as _settings  # type: ignore
    except Exception:
        return None
    val_dir = Path(_settings.UPLOAD_DIR).resolve() / "valuations"
    if not val_dir.exists():
        return None
    cid_str = str(company_id)
    candidates: list[tuple[float, dict]] = []
    for p in val_dir.glob("valuation-*.summary.json"):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("company_id") != cid_str:
            continue
        candidates.append((p.stat().st_mtime, data))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    latest = candidates[0][1]
    inputs = latest.get("inputs") or {}
    prev_exchange = (((inputs.get("engagement") or {}).get("exchange_platform")) or "").strip().upper()
    cur_exchange = (current_exchange or "").strip().upper()
    if not prev_exchange or not cur_exchange:
        return None
    if prev_exchange != cur_exchange:
        return None  # exchange changed — trigger fresh search
    cocos = inputs.get("cocos")
    if not isinstance(cocos, list) or not cocos:
        return None
    return inputs


_PRIMARY_GROWTH_CAP = 0.10  # 10% — anything above this needs BDP justification


def _ensure_revenue_growth_primary(payload: dict) -> None:
    """Ensure projections.revenue_growth_primary is a fully-populated length-n
    list (n = years count of revenue_growth). Defaulting rule, per Eric
    2026-05-19:

      1. If LLM supplied a full numeric list, clamp each entry to [0, 0.10]
         (the conservative-track cap) and keep them.
      2. Otherwise, derive a flat default from historical 3-yr revenue CAGR
         (`historical_fs.revenue[-3:]`), clamped to [0, 0.10].
      3. If historical revenue isn't available, copy revenue_growth and clamp
         to [0, 0.10] so primary is always defined.

    Mutates payload in place. Never raises — silently no-ops on malformed
    payloads (calibration / validation will catch shape issues downstream).
    """
    proj = payload.get("projections")
    if not isinstance(proj, dict):
        return
    growth = proj.get("revenue_growth")
    if not isinstance(growth, list) or not growth:
        return  # no total growth to anchor against; skeleton's IFERROR handles
    n = len(growth)

    def _clamp(x: Any) -> float | None:
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        if v < 0:
            return 0.0
        if v > _PRIMARY_GROWTH_CAP:
            return _PRIMARY_GROWTH_CAP
        return v

    supplied = proj.get("revenue_growth_primary")
    if isinstance(supplied, list) and len(supplied) == n and all(
        v is not None for v in supplied
    ):
        proj["revenue_growth_primary"] = [_clamp(v) for v in supplied]
        return

    historical = (payload.get("historical_fs") or {}).get("revenue")
    cagr: float | None = None
    if isinstance(historical, list):
        clean = [float(v) for v in historical if isinstance(v, (int, float)) and v > 0]
        if len(clean) >= 2:
            first, last = clean[-min(3, len(clean))], clean[-1]
            periods = min(3, len(clean)) - 1
            if first > 0 and periods > 0:
                try:
                    cagr = (last / first) ** (1.0 / periods) - 1.0
                except (ValueError, ZeroDivisionError):
                    cagr = None

    if cagr is not None:
        default = _clamp(cagr) or 0.0
        proj["revenue_growth_primary"] = [default] * n
        return

    # Last resort — copy revenue_growth (clamped) so primary still cascades
    # at a reasonable rate.
    proj["revenue_growth_primary"] = [_clamp(g) for g in growth]


def _calibrate_to_target(payload: dict, target_actual: float, pinned_keys: list[str] | None = None) -> float | None:
    """Deterministic safety net: when the LLM goal-seek loop fails to land DCF
    EV within tolerance of target, binary-search a uniform multiplier that
    scales BOTH revenue_growth AND gross_margin (capped at sane ceilings) so
    that DCF EV matches target.

    Mutates payload['projections']['revenue_growth'] + ['gross_margin']
    in place. Returns the multiplier actually applied (None if infeasible).

    Why two levers: revenue_growth alone hits a ceiling fast — at 6x the Top
    Leader -4 broken run only reached $41M of a $110M target because gross
    margin was the binding constraint (13.5%). Scaling both unlocks the upper
    range. Caps: per-period growth ≤ 1.50 (150%), per-period GM ≤ 0.85 (85%).
    Audited Y0 revenue + WACC + terminal stay untouched."""
    proj = payload.get("projections")
    if not isinstance(proj, dict):
        return None
    original_growth = proj.get("revenue_growth")
    original_gm = proj.get("gross_margin")
    if not isinstance(original_growth, list) or not original_growth:
        return None
    base_g = [float(g) if g is not None else 0.0 for g in original_growth]
    base_m = (
        [float(m) if m is not None else 0.0 for m in original_gm]
        if isinstance(original_gm, list) and original_gm
        else None
    )

    GROWTH_CAP = 1.50  # per-period growth cap (sanity)
    GM_CAP = 0.85       # per-period GM cap (sanity)

    # Indices that the analyst pinned — skip these when scaling so the pinned
    # value stays exactly as set, regardless of calibration multiplier.
    pinned_growth_idx = _pinned_array_indices(pinned_keys or [], "revenue_growth")
    pinned_gm_idx = _pinned_array_indices(pinned_keys or [], "gross_margin")

    def apply(multiplier: float) -> None:
        proj["revenue_growth"] = [
            base_g[i] if i in pinned_growth_idx else min(base_g[i] * multiplier, GROWTH_CAP)
            for i in range(len(base_g))
        ]
        if base_m is not None:
            proj["gross_margin"] = [
                base_m[i] if i in pinned_gm_idx else min(base_m[i] * multiplier, GM_CAP)
                for i in range(len(base_m))
            ]
        # Mirror to segments (top-level array is the cascade base when no
        # segments; when segments are present, their arrays drive the totals).
        # Segments inherit the same scaling but DON'T inherit pin protection —
        # pinned overrides are scoped to top-level arrays only for now.
        segs = proj.get("segments") or []
        for s in segs:
            if not isinstance(s, dict):
                continue
            if isinstance(s.get("revenue_growth"), list):
                s["revenue_growth"] = [
                    min(g * multiplier, GROWTH_CAP) if g is not None else None
                    for g in s["revenue_growth"]
                ]
            if isinstance(s.get("gross_margin"), list):
                s["gross_margin"] = [
                    min(m * multiplier, GM_CAP) if m is not None else None
                    for m in s["gross_margin"]
                ]

    def ev_at(multiplier: float) -> float | None:
        # Snapshot segment arrays before scaling so we can restore between probes
        segs = proj.get("segments") or []
        seg_snap = [
            (
                list(s["revenue_growth"]) if isinstance(s, dict) and isinstance(s.get("revenue_growth"), list) else None,
                list(s["gross_margin"]) if isinstance(s, dict) and isinstance(s.get("gross_margin"), list) else None,
            )
            for s in segs
        ]
        apply(multiplier)
        try:
            return _implied_dcf_ev_actual(payload)
        finally:
            for s, (g_snap, m_snap) in zip(segs, seg_snap):
                if isinstance(s, dict):
                    if g_snap is not None:
                        s["revenue_growth"] = g_snap
                    if m_snap is not None:
                        s["gross_margin"] = m_snap

    # Treat ev_at returning None (EV ≤ 0 / compute error) as "EV is effectively
    # zero" — that's what happens at the low end when GM × multiplier produces
    # negative gross profit. We never want to clamp to that bound; just treat
    # the multiplier as below-target so the bisection raises the floor.
    lo, hi = 0.3, 8.0
    ev_hi = ev_at(hi)
    if ev_hi is None:
        proj["revenue_growth"] = original_growth
        if base_m is not None:
            proj["gross_margin"] = original_gm
        return None
    # If even the max-effort multiplier can't reach target, clamp to hi.
    if target_actual >= ev_hi:
        apply(hi)
        return hi
    # Binary search — EV is non-decreasing in multiplier (with caps it
    # plateaus). Compute-failures at low multiplier are treated as "below
    # target" so the search keeps raising the floor.
    for _ in range(40):
        mid = (lo + hi) / 2
        ev_mid = ev_at(mid)
        if ev_mid is None or ev_mid < target_actual:
            lo = mid
        elif abs(ev_mid - target_actual) / target_actual < 0.005:  # ±0.5%
            apply(mid)
            return mid
        else:
            hi = mid
    apply((lo + hi) / 2)
    return (lo + hi) / 2


SYSTEM_INSTRUCTION = (
    "You are a valuation analyst at a US/Nasdaq IPO advisory firm. Your task "
    "is to produce a single JSON object conforming to the inputs-sheet schema. "
    "The output is consumed by an automated Excel export pipeline — any deviation "
    "from valid JSON breaks the build. Output JSON only, no prose, no markdown, "
    "no code fences. Default jurisdiction perspective: US/SEC (Nasdaq IPO targets); "
    "do NOT default to HKEX or HK regulatory framing."
)


def _build_user_prompt(context: str, target_valuation: float | None = None) -> str:
    goal_seek_block = (
        f"""

# Goal-seek mode (target valuation is the GOAL, not a reference)

The client has provided a target valuation of **{target_valuation}** in **ACTUAL currency units** (literally that many dollars/ringgit/etc. — NOT scaled by the workpaper unit). The pipeline scales the DCF Enterprise Value (per-management scenario) — which is stored in workpaper-unit thousands — up to actual currency before comparing to this target. Your job is to produce an assumption set whose actual-currency DCF EV lands within ±10% of the target.

This is NOT free-form reference — the client is paying for a workpaper that DEFENDS this valuation. Treat the target as a hard goal and back-solve the levers below within their defensible bands. The client has already done their own analysis and submitted a realistic figure; your job is to support it with rigorous numbers, not to second-guess it.

**Levers to flex (in order of preference):**

1. **Revenue growth (`projections.revenue_growth` / `projections.segments[].revenue_growth`)** — primary lever. Stretch the growth curve toward the upper end of what the BDP, comp set, and industry maturity support. Comp-set's top quartile growth is your defensible ceiling.
2. **Gross margin & EBITDA margin (`projections.gross_margin`, `projections.opex_pct_revenue`)** — model operating leverage / mix-shift / scale benefits that the documents can plausibly support. Stay at or below the comp set's top-quartile margins for the target's stage.
3. **Terminal growth (`terminal.growth_rate`)** — must remain ≤ long-run nominal GDP of the primary market (i.e. ≤ ~3.5% for developed markets, ≤ ~5% for high-growth emerging markets). Do NOT exceed this ceiling even to hit the target.
4. **WACC (`wacc.per_management.unlevered_beta`, `size_premium`, `specific_risk_premium`)** — lower WACC = higher EV. Beta should reflect the median of selected_for_wacc comps; size premium should reflect the target's actual size vs comps; specific risk premium can be tightened if the documents support lower idiosyncratic risk.
5. **Capex / D&A / NWC (`capex_pct_revenue`, `dep_pct_revenue`, `nwc_pct_sales`)** — tighter capital intensity = higher FCFF = higher EV. Use the comp set's median capital intensity as the floor; don't go below it without explicit evidence.

**Defensibility guardrails (non-negotiable — violating these makes the workpaper indefensible and the engagement is over):**

- Y1 revenue growth ≤ 100% (only if Y0 revenue is sub-$10M scale AND the BDP shows a credible product/GTM driver). For mature targets, ≤ 50%.
- Average Y1–Y5 revenue growth ≤ comp set's 75th-percentile growth.
- Gross margin ≤ comp set's 90th percentile.
- EBITDA margin Y5 ≤ comp set's 75th percentile (don't model the target out-margining the best public comps).
- Terminal growth ≤ 3.5% (developed markets) or ≤ 5% (high-growth emerging markets).
- Unlevered beta ≥ 0.7 (no asset-light fantasy).
- WACC ≥ risk_free_rate + 3% (no zero-risk discount rates).

If the target is so aggressive that hitting it would require breaking these guardrails, produce the closest-feasible assumption set (do not break the guardrails) and emit a brief explanation in `engagement.report_purpose` describing what additional evidence (e.g. signed pipeline contracts, regulatory approvals, new market launches) would be needed to defensibly close the remaining gap.

# Convergence loop

After you emit the JSON, the pipeline will compute the DCF per-management EV and compare it to the target. If divergence > 10%, you will be asked to retry with the specific delta — at that point, tighten the levers further (still within guardrails) to close the gap. Plan your initial assumptions to land close to target on the first attempt so the loop completes quickly."""
        if target_valuation is not None
        else ""
    )

    return f"""# Company context (from extracted documents and database)

{context if context else '(No extracted documents available — use sensible defaults consistent with US/Nasdaq IPO advisory practice for a generic Asia-Pacific tech target.)'}

# Document priority (Eric 2026-05-19 #2)

When extracting financial data from the company context above, weigh document categories in this order — earlier-listed sources override later ones if they disagree:

**Primary (must extract from when present):**
1. `audit_report` — most recent audited financial statements. Trumps everything for revenue_y0, historical_fs.*, gross_profit_y0, opex_y0, ebitda_y0, ebit_y0, tax_y0, net_income_y0, nwc_y0.
2. `management_accounts` — interim / LTM accounts that bridge the audit to today. Use ONLY for periods after the audit cutoff or when audit is missing.
3. `projections` / Business Development Plan — drives revenue_growth, gross_margin progression, opex_pct_revenue, capex/D&A intensity. Anchor every Y1-Y5 array entry to a specific driver cited in the BDP.

**Secondary (strengthens defensibility):**
4. `cap_table` — drives bridge.shares_outstanding, shares_outstanding_diluted, equity_interest_pct.
5. `shareholder_agreement` — affects bridge.dlom_pct (lockup / transfer restrictions) and dloc_pct (control / voting rights).
6. `tax_return` — sanity-checks tax.rate_high and the effective_rate_override.
7. `board_minutes` — context for terminal_growth_rate, specific_risk_premium (governance maturity).

If a primary doc is missing, populate from secondaries + market data, and flag the gap in the relevant `sources.<id>.notes` field so the analyst sees what was inferred vs audited.

# Task

Produce a JSON object that conforms to the schema document above. Use the company context to fill as many fields as possible. For fields you cannot determine from the context, use sensible defaults consistent with US/Nasdaq IPO advisory practice.{goal_seek_block}

# Market-aligned assumptions (Eric 2026-05-08 item 3)

Every growth rate, margin, WACC component, terminal-value parameter, and comp-set assumption MUST be defensible against current market conditions AND the target's business-development plan (BDP). Specifically:

- **Revenue growth & gross margin:** anchor to (a) the target's stated BDP / management projections if present in the documents, (b) recent comparable-company growth rates as a ceiling reality-check, and (c) industry-standard maturity curves (high-growth in early years, decaying toward terminal). If the BDP is absent, infer from historical FS trajectory + segment commentary. **When goal-seek mode is active, lean toward the upper end of the defensible range; when no target is set, lean toward the anchor.**
- **WACC inputs (risk_free, ERP, country risk, beta):** anchor risk_free_rate to a current sovereign-yield observation (cite the date), ERP to Damodaran's most recent implied ERP, country risk to Damodaran's country table, and unlevered_beta to the median of the comps marked `selected_for_wacc=true` (not a generic industry average).
- **WACC self-review (Eric 2026-05-19 #7) — REQUIRED:** after composing the WACC build, take an explicit second pass on `specific_risk_premium` (per-mgmt and independent). For BOTH scenarios, populate `sources.specific_risk_premium_per_mgmt.rationale` and `sources.specific_risk_premium_indep.rationale` with 2–3 sentences that EXPLICITLY assess: (i) **customer / supplier concentration** — single-customer revenue >30% or single-supplier sourcing >40% warrants +50–100bps; (ii) **governance maturity** — pre-IPO, recently-restated, or family-controlled targets carry +50–150bps; (iii) **jurisdictional risk above country premium** — operating-in-single-country, regulatory-license dependency, or sanctions-exposed targets warrant +25–100bps; (iv) **scale / data quality** — sub-$50M revenue or partial audit history warrants +25–75bps. Justify the final number you chose against this checklist. If you tightened the premium below your comp set's median, the rationale MUST identify which evidence (e.g. "long-dated supply contracts disclosed in note 14") supports the tightening. This is the analyst-facing review that defends the WACC; do not skip it.
- **Terminal growth:** must be ≤ long-run nominal GDP of the target's primary market AND consistent with industry-maturity expectations. Anything >3.5% for a developed-market company is hard to defend.
- **Margin progression:** if you project gross_margin or EBITDA-margin expansion, the trajectory must be justified by operating-leverage evidence in the documents (segment-mix shift, scale, automation). Do not assume universal margin expansion absent evidence.
- **Comp multiples:** the median comp multiple is only defensible if the comp set genuinely matches the target on size, growth, margin profile, and geography. If the target is sub-scale relative to the comps, apply a size discount in `size_premium`.

Every assumption above must have a `sources.<id>` entry whose `source` + `detail` cite the EXACT evidence (FS page, Damodaran retrieval date, BDP slide number, comp filing). Generic "Manual" sourcing is only acceptable when no document evidence exists AND the assumption is a regulator-standard convention.

# Market data freshness (Eric 2026-05-19 #8) — REQUIRED

Every **market-driven** parameter — `risk_free_rate`, `equity_risk_premium`, `country_risk_premium`, every `coco_multiples` entry, every `precedents.ev_*` figure, every comp `raw_beta` and `market_cap_usd_mm` — MUST carry an explicit retrieval date in its source's `detail` field. Acceptable formats: ISO date `"retrieved 2024-12-31"` or month-year `"as at Dec 2024"`. The date should be the most recent observation you can defensibly cite, ideally within 90 days of the engagement's `valuation_date`. For each entry:

- If retrieval date is **within 90 days of valuation_date** → no caveat needed; the data is fresh.
- If retrieval date is **90–180 days old** → append `"; consider refreshing before client delivery"` to the source's `notes`.
- If retrieval date is **>180 days stale** → append `"STALE: refresh required; current value may differ"` to `notes` and DO NOT use it as a goal-seek anchor.

This stays consistent with the dashboard/xlsx audit trail and gives the analyst a clear refresh trigger before they sign the report.

# Required completeness

Every section listed below MUST be present in the output:

- `engagement` — all 13 fields (company_name, company_country, company_industry_us, company_industry_global, valuation_date, target_valuation, exchange_platform, report_purpose, accounting_standard, engagement_team{{partner,manager,department}}, client_name). `target_valuation` is the client's stated target valuation in **ACTUAL currency units** — NOT scaled by `currency.unit`. A $1B target is written as `1000000000`, NOT `1000000` (even when the workpaper unit is `'000`). Leave null if not provided by the user. `exchange_platform` is the exchange the comparable-company pool must be drawn from (e.g. "NASDAQ", "NYSE"); default to "NASDAQ" if not specified — comps not listed on this exchange must be excluded.
- `currency` — primary, unit, alt, fx_rate_alt
- `tax` — jurisdiction, type ("flat"/"two_tier"/"progressive"), rate_low, rate_high, threshold, effective_rate_override
- `projections` — years (typically 5), revenue_growth_method, **revenue_y0** (last reported full-year revenue, in the same currency × unit as the workpaper), **nwc_y0** (audited Y0 NWC = current assets ex-cash − current liabilities ex-debt), and Y1-Y5 arrays for revenue_growth, **revenue_growth_primary**, gross_margin, opex_pct_revenue, capex_pct_revenue, dep_pct_revenue, nwc_pct_sales (all 7 arrays, each length-5). **revenue_y0 is the cascade base — without it the workpaper math is dead.** ALSO populate **gross_profit_y0**, **opex_y0** (negative), **ebitda_y0**, **ebit_y0**, **tax_y0** (negative), **net_income_y0** from the most recent full-year audited income statement (`historical_fs.gross_profit[-1]`, `historical_fs.opex_total[-1]`, `historical_fs.ebitda[-1]`, `historical_fs.ebit[-1]`, `historical_fs.tax_expense[-1]`, `historical_fs.net_income[-1]`) so the Projections sheet's Y0 column shows real audited values, not blanks. Eric 2026-05-18 / 2026-05-19 #1.

**Primary vs. Total revenue growth (Eric 2026-05-19)**: `revenue_growth` is the **TOTAL** growth the calibration tunes to hit `target_valuation`. `revenue_growth_primary` is the **CONSERVATIVE** baseline track — what the business does if it just continues its historical trend, with NO additional BDP-driven stretch. Anchor `revenue_growth_primary` to the 3-year historical revenue CAGR (compute from `historical_fs.revenue[-3:]`), allowing ±2pp tolerance for cyclical normalization. **Cap `revenue_growth_primary` at 10% absolute** even if historical CAGR is higher (anything above that needs BDP justification → goes into Additional). The Projections sheet displays Primary, Additional (= Total − Primary), and Total as three separate rows — Additional represents the BDP-justified stretch that the analyst must defend in the written report. Always populate `revenue_growth_primary` even when uncertain (fallback: copy `revenue_growth` clamped to [0, 0.10]).
- `projections.segments` (OPTIONAL but RECOMMENDED when the target has distinct business lines) — array of segments, each `{{name, start_year, revenue_y0 (if start_year=0) or initial_revenue (if start_year>0), revenue_growth[], gross_margin[] OR cogs_pct[]}}`. When provided, total revenue & gross profit at each year are the SUM across all active segments; the top-level revenue_growth + gross_margin arrays are then IGNORED for the cascade (still emit them for back-compat, but make the segment numbers the authoritative breakdown). Segments with `start_year > 0` model new revenue streams launched mid-projection (Eric 2026-05-08 item 2: "user can add new revenue streams with corresponding COGS during the projection period"). The sum of all segment revenue_y0 (for start_year=0 segments) MUST equal the top-level revenue_y0 — otherwise the workpaper Y0 base mismatches the audited FS.
- `historical_fs` — 5-year arrays (FY-5..FY-1, oldest first; pad with null where data is missing) for: revenue, cogs, gross_profit, opex_total, sga, rnd, ebitda, da, ebit, interest_expense, other_income_expense, profit_before_tax, tax_expense, net_income, cash, accounts_receivable, inventory, prepaid_expenses, total_current_assets, ppe, intangibles, other_lt_assets, total_assets, accounts_payable, short_term_debt, other_current_liabilities, total_current_liabilities, long_term_debt, other_lt_liabilities, total_liabilities, total_equity. Pull from audited financial statements when available — fewer than 5 years OK; pad missing years with `null` (NOT 0).
- `terminal` — method ("gordon_growth"), growth_rate, exit_multiple_type, exit_multiple_value
- `wacc.shared` — risk_free_rate, risk_free_rate_source, equity_risk_premium, country_risk_premium
- `wacc.per_management` — unlevered_beta, target_debt_to_equity, size_premium, specific_risk_premium, pretax_cost_of_debt, target_debt_weight, target_equity_weight
- `wacc.independent` — same fields, slightly more conservative (higher beta, higher specific risk, higher D/E)
- `cocos` — array of 0-30 comparable companies with (tier, include, company, ticker, exchange, business_description, selected_for_wacc, country, accounting, market_cap_usd_mm, d_to_e, raw_beta, tax_rate). **Exchange filter rule:** every comp's `exchange` field MUST equal `engagement.exchange_platform` — comps listed on other exchanges are excluded by the pipeline. **Selection rule (Eric 2026-05-19 #3 — TIGHTENED):** screen ~15–20 comps total; **mark EXACTLY 5–6 (no fewer, no more) with `selected_for_wacc=true`** — these are the "highly relevant" set that drives the WACC β. Every selected_for_wacc comp MUST satisfy ALL of: (a) **size match** — market cap within ~10× of the target's expected market cap (target estimated as Y1 revenue × industry-typical EV/Sales); (b) **sub-industry match** — same Damodaran industry classification or one tier away; (c) **geography proximity** — same region or close (HK/SG/MY/AU peers preferred over US for an APAC trader; US peers OK if no APAC equivalents exist on the target exchange); (d) **margin profile** — gross-margin and EBITDA-margin within ~50% relative of the target's own audited profile (a low-margin trading co. should NOT pick a high-margin SaaS comp). Reference/peer comps (`selected_for_wacc=false`) populate the broader 15–20-comp pool used in market-multiple ranges. **business_description** is a one-line description of what the comp does (e.g. "Document-oriented NoSQL database"). **Outlier check (Eric 2026-05-19 #6):** before finalising the multiples, sanity-check each comp's EV/Sales, EV/EBITDA, P/E against the cluster. If a comp's multiple is more than ~3× the visual median of the rest, mark its `include=false` and append " — multiple outlier, excluded" to its `business_description`. The Python summary additionally applies an IQR-based outlier filter (drops values outside [Q1 − 1.5·IQR, Q3 + 1.5·IQR]) so the dashboard medians are clean even if the analyst leaves include=true. **Tier 3 size cap rule:** comparables (especially Tier 3) must be within ~10× the target's enterprise value. Do NOT include megacap reference comps that are 100×+ the target's size — they distort the median multiples. If the target's market cap is unclear, use revenue × industry-typical EV/Sales as a proxy.
- `coco_multiples` — array same length and order as `cocos`, each entry `{{ev_sales_ltm, ev_sales_ntm, ev_ebitda_ltm, ev_ebitda_ntm, pe_ltm, pe_ntm}}`. Provide market-observed trading multiples for each comparable. Use null where data is unavailable (e.g. negative-EBITDA companies for EV/EBITDA). **Without these, the entire Comps + Football Field cascade is dead.**
- `coco_margins` — array same length as `cocos`, each `{{gross, ebit, net}}` (decimals; -0.10 = -10%)
- `coco_ratios` — array same length as `cocos`, each `{{roe, roa, d_to_e, current_ratio}}`
- `precedents` — array of 0-15 transactions with (include, date, acquirer, target, ev_usd_mm, ev_revenue, ev_ebitda, premium, rationale)
- `bridge` — surplus_assets, net_debt_override (null OK — defaults to short_term_debt + long_term_debt − cash from Historical FS), minority_interests, non_operating_assets, dlom_pct, dloc_pct, equity_interest_pct, shares_outstanding, shares_outstanding_diluted (null OK), pre_money_pct (null OK)
- `adjustments` — capitalize_rd, rd_amortization_years, convert_operating_leases, lease_discount_rate (null OK)
- `football_field` — weight_dcf, weight_comps, weight_precedent, weight_nav (sum must equal 1.0; weight_nav typically 0). Also produce an initial `selected_low`, `selected_mid`, `selected_high` band — set selected_mid to your best estimate of EV (using the company context + projections), and selected_low/high to ±15% around the mid as an initial range for the analyst to refine.
- `sensitivity` — wacc_step (0.005), wacc_count (5), terminal_g_step (0.005), terminal_g_count (5), revenue_g_step (0.02), ebitda_margin_step (0.02)
- `sources` — **MANDATORY**: every scalar parameter you assign a non-null value MUST have a corresponding `sources.<id>` entry of shape `{{source, detail, notes, rationale}}`. The `source` field must be one of: "Audited FS", "Management Projections", "Capital IQ", "Bloomberg", "Damodaran", "Kroll", "Mercer", "Prospectus", "Engagement Letter", "Calculated", "Manual". The `detail` field cites the specific document/page/figure (e.g. "FY2024 Audited FS, Note 3 — Revenue, p.42"). For Damodaran data: cite "Damodaran NYU Stern, [country/industry] page, retrieved <date>". This audit trail is non-negotiable; without sources the workpaper cannot be defended. At minimum, populate sources for: company_name, valuation_date, target_valuation (when provided), tax_rate_high, revenue_y0, nwc_y0, risk_free_rate, equity_risk_premium, country_risk_premium, unlevered_beta_per_mgmt, dlom_pct, dloc_pct, shares_outstanding, terminal_growth_rate.
- The `rationale` field (Eric 2026-05-08 item 7) is the "why" for the chosen number — 1–3 sentences explaining how this SPECIFIC value was derived for THIS company, citing the target's BDP / segment trajectory / comp set / industry context. This is what the report uses to defend the number to the client. **REQUIRED for**: target_valuation (when set — explain how the goal-seek levers were tuned), revenue_growth_y1 (top-level or per-segment), gross_margin_y1, terminal_growth_rate, unlevered_beta_per_mgmt, dlom_pct, dloc_pct, equity_risk_premium, risk_free_rate. **Strongly encouraged for**: every other scalar where the choice is non-obvious. **Skip rationale for** routine pass-through fields (e.g. company_name, valuation_date). Example: `"rationale": "30% Y1 revenue growth reflects management's 2025 BDP (slide 12), which assumes the Atlas migration concludes Q3 and unlocks the enterprise tier. This is below Datadog's 35% LTM growth at comparable scale and above the comp-set median of 24%, so the trajectory is defensible without breaking the size-vs-growth norm for Tier-1 SaaS."`

# Output

JSON object only. No prose, no markdown fences, no leading or trailing text."""


def _median(values: list[float]) -> float | None:
    """Plain median, returns None on empty input."""
    xs = sorted(values)
    n = len(xs)
    if n == 0:
        return None
    if n % 2 == 1:
        return xs[n // 2]
    return (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _derive_unlevered_beta(payload: dict) -> float | None:
    """Eric 2026-05-08 item 5: WACC β must be derived from the comps marked
    `selected_for_wacc=true`, not hand-entered. For each selected comp, unlever
    raw_beta via Hamada: unlevered = levered / (1 + (1 − tax) × D/E). Return the
    median across selected comps. Returns None if fewer than 3 comps qualify —
    in that case the LLM's value stays as the fallback."""
    cocos = payload.get("cocos") or []
    if not isinstance(cocos, list):
        return None
    unlevered: list[float] = []
    for c in cocos:
        if not isinstance(c, dict):
            continue
        if not c.get("selected_for_wacc"):
            continue
        if c.get("include") is False:
            continue
        try:
            levered = float(c.get("raw_beta") or 0)
            de = float(c.get("d_to_e") or 0)
            tax = float(c.get("tax_rate") or 0)
        except (TypeError, ValueError):
            continue
        if levered <= 0:
            continue
        denom = 1.0 + (1.0 - tax) * de
        if denom <= 0:
            continue
        unlevered.append(levered / denom)
    if len(unlevered) < 3:
        return None
    return _median(unlevered)


def _normalize_exchange(target_exchange: str | None) -> str | None:
    """Map a Company.target_exchange enum value (nasdaq / nasdaq_capital /
    nasdaq_global / nasdaq_global_select / nyse / nyse_american / other) to the
    coarse exchange_platform string the comp-filter step expects ('NASDAQ' /
    'NYSE'). Granular Nasdaq tiers collapse to NASDAQ because comps are filtered
    on exchange family, not listing tier."""
    if not target_exchange:
        return None
    key = target_exchange.strip().lower()
    if key.startswith("nasdaq"):
        return "NASDAQ"
    if key.startswith("nyse"):
        return "NYSE"
    return None


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from the model's response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back: extract from a markdown code block
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    # Fall back: extract the largest JSON-looking substring
    obj = re.search(r"\{.*\}", text, re.DOTALL)
    if obj:
        try:
            return json.loads(obj.group(0))
        except json.JSONDecodeError:
            pass
    return None


class ProduceValuationInputsSkill(Skill):
    name = "produce_valuation_inputs"
    description = (
        "Produce a JSON object conforming to the valuation Inputs schema by "
        "analyzing the company's extracted documents. Output is consumed by "
        "the valuation workpaper export pipeline."
    )
    parameters = []  # No params — reads ctx.documents

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        if not settings.ANTHROPIC_API_KEY:
            return SkillResult.failed(
                "ANTHROPIC_API_KEY is not configured. Set it in env or backend/.env"
            )

        if not SCHEMA_PATH.exists():
            return SkillResult.failed(f"Schema doc not found at {SCHEMA_PATH}")

        # Per-valuation run-config (Eric 2026-05-08 item 1). Precedence for the
        # final engagement.target_valuation written to the inputs JSON:
        #   1. kwarg from the Generate form (this-run override)
        #   2. Company.target_valuation (saved default on the company record)
        #   3. whatever the LLM infers from documents (lowest priority)
        # The kwarg / company value is also surfaced into the LLM prompt so the
        # model knows it and the assumptions can reference it.
        target_valuation_kw = kwargs.get("target_valuation")
        target_valuation_run: float | None = None
        if target_valuation_kw is not None:
            try:
                target_valuation_run = float(target_valuation_kw)
            except (TypeError, ValueError):
                target_valuation_run = None

        # Eric 2026-05-08 item 6: per-run valuation date. Forecasts, market data,
        # and comp metrics must be anchored to this date.
        valuation_date_kw = kwargs.get("valuation_date")
        valuation_date_run: str | None = None
        if isinstance(valuation_date_kw, str) and valuation_date_kw.strip():
            valuation_date_run = valuation_date_kw.strip()

        # Load company + extracted docs. get_best_context_str prefers the
        # pre-compiled kb pages (profile / historical-fs / cap-table) and falls
        # back to the raw extracted_data flatten on cold start.
        await ctx.load_company_data()
        company_context = await ctx.get_best_context_str()

        company_obj = getattr(ctx, "company", None)
        company_tv_raw = getattr(company_obj, "target_valuation", None)
        target_valuation_company: float | None = None
        if company_tv_raw is not None:
            try:
                target_valuation_company = float(company_tv_raw)
            except (TypeError, ValueError):
                target_valuation_company = None

        target_valuation_effective: float | None = (
            target_valuation_run if target_valuation_run is not None
            else target_valuation_company
        )

        # Eric 2026-05-17 — analyst-pinned overrides from Company record.
        # Filtered to known keys only; values coerced to float in _apply_pinned_overrides.
        pinned_overrides_raw = getattr(company_obj, "pinned_overrides", None) or {}
        pinned_overrides: dict[str, float] = {}
        if isinstance(pinned_overrides_raw, dict):
            for k, v in pinned_overrides_raw.items():
                if k in PINNABLE_PARAMS and v is not None:
                    try:
                        pinned_overrides[k] = float(v)
                    except (TypeError, ValueError):
                        pass

        if pinned_overrides:
            # Tell the LLM these are non-negotiable so it doesn't waste effort
            # trying to re-derive them from documents or convergence pressure.
            lines = []
            for k, v in pinned_overrides.items():
                path, type_ = PINNABLE_PARAMS[k]
                display = f"{v*100:.2f}%" if type_ == "percent" else f"{v:,.4f}"
                lines.append(f"  - {path} = {display}  (key: {k})")
            company_context = (
                "ANALYST-PINNED PARAMETERS (must preserve these exact values; "
                "DO NOT adjust based on documents, comps, or goal-seek pressure; "
                "tune all OTHER assumptions around these pivots):\n"
                + "\n".join(lines)
                + "\n\n"
                + company_context
            )

        # Eric 2026-05-19 #9 — analyst-supplied Business Development Plan.
        # Treated as authoritative narrative context for revenue/growth/margin
        # justification, anchoring the projection cascade against the BDP's
        # specific drivers (new product launches, geographic expansion, signed
        # contracts, capex programs). Injected ABOVE the document context so
        # the LLM weighs it as primary evidence, not commentary.
        bdp_raw = getattr(company_obj, "business_development_plan", None)
        if isinstance(bdp_raw, str) and bdp_raw.strip():
            company_context = (
                "ANALYST-SUPPLIED BUSINESS DEVELOPMENT PLAN (authoritative; "
                "use as primary evidence for revenue / growth / margin "
                "assumptions — every projection lever you choose MUST be "
                "traceable to a specific driver in this plan):\n"
                + bdp_raw.strip()
                + "\n\n"
                + company_context
            )

        # Eric 2026-05-18 — reuse the previous valuation's comp set when the
        # target exchange hasn't changed. The LLM still produces a payload but
        # we force its cocos arrays back to the previous run's identities
        # post-LLM (preserving any market-data refresh the LLM made per ticker).
        # Fresh comp search only fires when there's no prior run for this
        # company or when target_exchange changed.
        normalized_exchange = _normalize_exchange(
            getattr(company_obj, "target_exchange", None)
        )
        previous_inputs_for_cocos = _find_previous_valuation_payload(
            getattr(ctx, "company_id", None), normalized_exchange
        )
        if previous_inputs_for_cocos is not None:
            prev_cocos = previous_inputs_for_cocos.get("cocos") or []
            ticker_list = [str((c or {}).get("ticker") or "").strip() for c in prev_cocos if isinstance(c, dict)]
            ticker_list = [t for t in ticker_list if t]
            if ticker_list:
                company_context = (
                    "COMP SET LOCK (analyst-anchored; do NOT re-screen comps):\n"
                    "The previous valuation run for this company used the exact set of "
                    "comparable companies listed below. The analyst has not changed the "
                    "target exchange platform, so the comp set is LOCKED — emit EXACTLY "
                    "these tickers in your `cocos` array, in the same order, with the "
                    "same `company`, `ticker`, `exchange`, `country`, `accounting`, "
                    "`business_description`, and `tier` fields. You MAY refresh per-ticker "
                    "market data (`market_cap_usd_mm`, `d_to_e`, `raw_beta`, `tax_rate`, "
                    "and the `coco_multiples` / `coco_margins` / `coco_ratios` arrays) "
                    "with the latest values you know. DO NOT add, drop, reorder, or "
                    "replace any tickers. The post-LLM step enforces this lock.\n\n"
                    "Required tickers (in order): "
                    + ", ".join(ticker_list)
                    + "\n\n"
                    + company_context
                )

        # Eric 2026-05-18 — pinned CoCo selection injected into the prompt
        # as required tickers, exempt from the exchange filter. The post-LLM
        # overlay enforces the same flags + injects stubs if the LLM still
        # drops a pinned ticker.
        pinned_cocos_for_prompt = getattr(company_obj, "pinned_cocos", None) or {}
        pinned_cocos_for_prompt = pinned_cocos_for_prompt if isinstance(pinned_cocos_for_prompt, dict) else {}
        if pinned_cocos_for_prompt:
            required_lines = []
            for ticker, flags in pinned_cocos_for_prompt.items():
                if not isinstance(flags, dict):
                    continue
                include = bool(flags.get("include"))
                wacc = bool(flags.get("selected_for_wacc"))
                if not include and not wacc:
                    continue
                tag = []
                if include: tag.append("include=true")
                if wacc:    tag.append("selected_for_wacc=true")
                required_lines.append(f"  - {ticker} ({', '.join(tag)})")
            if required_lines:
                company_context = (
                    "ANALYST-PINNED COMPARABLE COMPANIES (MUST appear in your cocos array "
                    "with the exact ticker string shown below; DO NOT drop these even if "
                    "your exchange filter or comp-screen would normally exclude them — the "
                    "analyst has explicitly selected them. Populate all comp metadata "
                    "(company name, country, accounting standard, market cap, D/E, raw_beta, "
                    "tax rate, business_description) as best you can from your knowledge. "
                    "The include / selected_for_wacc flags shown will be enforced post-LLM):\n"
                    + "\n".join(required_lines)
                    + "\n\n"
                    + company_context
                )

        if target_valuation_run is not None:
            company_context = (
                f"User-supplied target valuation for this run: {target_valuation_run} "
                f"(in the same currency × unit you select for the workpaper). "
                f"Set engagement.target_valuation to this value; do NOT infer a different target "
                f"from documents — the user's input is authoritative.\n\n"
                f"{company_context}"
            )
        elif target_valuation_company is not None:
            company_context = (
                f"Saved target valuation on the company record: {target_valuation_company} "
                f"(in the same currency × unit you select for the workpaper). "
                f"Use this as engagement.target_valuation unless the documents contradict it.\n\n"
                f"{company_context}"
            )

        if valuation_date_run is not None:
            company_context = (
                f"User-supplied valuation date for this run: {valuation_date_run} (ISO YYYY-MM-DD). "
                f"All forecasts, market data, risk-free / ERP observations, comparable-company "
                f"multiples, and precedent transaction screens MUST be anchored to this date. "
                f"Set engagement.valuation_date to this value; do NOT infer a different date "
                f"from documents — the user's input is authoritative.\n\n"
                f"{company_context}"
            )

        schema_doc = SCHEMA_PATH.read_text()

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # System prompt: instruction + schema doc (cached — large + stable).
        # Both attempts (initial + retry) reuse the same system; cache_read on
        # attempt 2 is essentially free.
        system_prompt = [
            {"type": "text", "text": SYSTEM_INSTRUCTION},
            {
                "type": "text",
                "text": f"# Inputs Schema (canonical)\n\n{schema_doc}",
                "cache_control": {"type": "ephemeral"},
            },
        ]

        # Attempt loop covers two failure modes that retry differently:
        #  - schema validation (Pydantic errors) → retry with the error list
        #  - goal-seek convergence (DCF EV vs target_valuation > 10% off) →
        #    retry with the delta and instructions to tighten levers
        # 2 attempts is enough: the LLM gets one shot to converge, then the
        # deterministic post-process calibration (_calibrate_to_target) handles
        # any residual gap by scaling revenue_growth + gross_margin uniformly.
        # More LLM attempts mostly add latency (60-120s each) without improving
        # the final EV — calibration is exact, the LLM only needs to produce a
        # reasonable starting point.
        MAX_ATTEMPTS = 2
        EV_CONVERGENCE_TOLERANCE = 0.10  # ±10% of target is "close enough"
        last_payload: dict | None = None
        last_validation_error: str | None = None
        last_convergence_feedback: str | None = None
        last_implied_ev: float | None = None
        usage_totals = {"input_tokens": 0, "output_tokens": 0,
                        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        attempts_made = 0

        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempts_made = attempt
            user_prompt = _build_user_prompt(company_context, target_valuation_effective)
            if attempt > 1 and last_validation_error:
                user_prompt += (
                    f"\n\n# VALIDATION ERRORS FROM PREVIOUS ATTEMPT (FIX THESE)\n\n"
                    f"Your last response failed schema validation. Re-emit the full JSON, "
                    f"correcting these specific issues:\n\n{last_validation_error}\n\n"
                    f"Output the COMPLETE corrected JSON object, not a diff."
                )
            elif attempt > 1 and last_convergence_feedback:
                user_prompt += last_convergence_feedback

            try:
                async with client.messages.stream(
                    model="claude-opus-4-7",
                    max_tokens=32000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                ) as stream:
                    response = await stream.get_final_message()
            except anthropic.APIError as e:
                return SkillResult.failed(f"Anthropic API error (attempt {attempt}): {e}")

            usage = getattr(response, "usage", None)
            if usage is not None:
                for k in usage_totals:
                    usage_totals[k] += getattr(usage, k, 0) or 0

            text_blocks = [b.text for b in response.content if b.type == "text"]
            if not text_blocks:
                return SkillResult.failed(f"Model returned no text content (attempt {attempt})")
            text = text_blocks[0]

            payload = _parse_json_response(text)
            if payload is None:
                # JSON parse failure — retry with a hint
                last_validation_error = (
                    "Your response could not be parsed as JSON. Output ONLY a single "
                    "JSON object — no markdown fences, no prose, no leading/trailing text."
                )
                last_payload = None
                continue

            # Authoritatively set engagement.exchange_platform from the
            # Company record — Company.target_exchange is the user's explicit
            # choice and trumps whatever the LLM inferred from documents. If
            # Company has no exchange set ('other' or null), leave the LLM's
            # value alone.
            company_obj = getattr(ctx, "company", None)
            normalized_exchange = _normalize_exchange(
                getattr(company_obj, "target_exchange", None)
            )
            if normalized_exchange is not None:
                eng = payload.setdefault("engagement", {})
                eng["exchange_platform"] = normalized_exchange

            # Authoritatively set engagement.target_valuation using the precedence
            # computed above (kwarg > company > leave LLM value).
            if target_valuation_effective is not None:
                eng = payload.setdefault("engagement", {})
                eng["target_valuation"] = target_valuation_effective

            # Eric 2026-05-08 item 6: per-run valuation date override.
            if valuation_date_run is not None:
                eng = payload.setdefault("engagement", {})
                eng["valuation_date"] = valuation_date_run

            # Eric 2026-05-18 — comp-set lock enforcement. If the previous
            # valuation's comp set is still valid (same exchange), force the
            # cocos arrays back to that identity even if the LLM tried to
            # introduce different tickers. Per-ticker market data the LLM
            # refreshed is preserved when its ticker matches the previous set.
            if previous_inputs_for_cocos is not None:
                prev_cocos = previous_inputs_for_cocos.get("cocos") or []
                prev_mult  = previous_inputs_for_cocos.get("coco_multiples") or []
                prev_marg  = previous_inputs_for_cocos.get("coco_margins") or []
                prev_rat   = previous_inputs_for_cocos.get("coco_ratios") or []
                llm_cocos  = payload.get("cocos") or []
                llm_mult   = payload.get("coco_multiples") or []
                llm_marg   = payload.get("coco_margins") or []
                llm_rat    = payload.get("coco_ratios") or []
                llm_by_ticker = {
                    str((c or {}).get("ticker") or "").strip().lower(): i
                    for i, c in enumerate(llm_cocos) if isinstance(c, dict)
                }
                new_cocos: list[dict] = []
                new_mult: list[dict] = []
                new_marg: list[dict] = []
                new_rat: list[dict] = []
                for prev_idx, prev_c in enumerate(prev_cocos):
                    if not isinstance(prev_c, dict):
                        continue
                    t_lower = str(prev_c.get("ticker") or "").strip().lower()
                    if t_lower and t_lower in llm_by_ticker:
                        llm_idx = llm_by_ticker[t_lower]
                        llm_c = llm_cocos[llm_idx] if isinstance(llm_cocos[llm_idx], dict) else {}
                        # Merge: prev identity + LLM-refreshed market data.
                        merged = {**prev_c, **llm_c}
                        # Force-preserve identity fields from prev so the LLM
                        # can't rename / re-exchange the comp.
                        for k in ("ticker", "company", "exchange", "business_description"):
                            if prev_c.get(k) is not None:
                                merged[k] = prev_c[k]
                        new_cocos.append(merged)
                        new_mult.append(llm_mult[llm_idx] if llm_idx < len(llm_mult) else (prev_mult[prev_idx] if prev_idx < len(prev_mult) else {}))
                        new_marg.append(llm_marg[llm_idx] if llm_idx < len(llm_marg) else (prev_marg[prev_idx] if prev_idx < len(prev_marg) else {}))
                        new_rat.append(llm_rat[llm_idx] if llm_idx < len(llm_rat) else (prev_rat[prev_idx] if prev_idx < len(prev_rat) else {}))
                    else:
                        # LLM dropped this ticker — keep prev verbatim
                        new_cocos.append(prev_c)
                        new_mult.append(prev_mult[prev_idx] if prev_idx < len(prev_mult) else {})
                        new_marg.append(prev_marg[prev_idx] if prev_idx < len(prev_marg) else {})
                        new_rat.append(prev_rat[prev_idx] if prev_idx < len(prev_rat) else {})
                payload["cocos"] = new_cocos
                payload["coco_multiples"] = new_mult
                payload["coco_margins"] = new_marg
                payload["coco_ratios"] = new_rat

            # Eric 2026-05-18 — analyst-pinned CoCo selection. Overlay
            # include / selected_for_wacc flags onto matching cocos by ticker
            # BEFORE derived_beta runs, so the β build reflects the analyst's
            # comp choices (not the LLM's gut feel). If a pinned ticker is
            # MISSING from the LLM's cocos (LLM dropped it via exchange filter
            # or different comp-screen), INJECT a stub so the analyst's pin
            # survives across runs — the LLM may have given it metadata in
            # the prompt-driven path; if not, the analyst fills it via Re-upload.
            pinned_cocos_raw = getattr(company_obj, "pinned_cocos", None) or {}
            if isinstance(pinned_cocos_raw, dict) and pinned_cocos_raw:
                cocos = payload.setdefault("cocos", [])
                if not isinstance(cocos, list):
                    cocos = []
                    payload["cocos"] = cocos
                # Build a lookup of ticker -> coco entry (case-insensitive on ticker)
                by_ticker = {
                    str(c.get("ticker") or "").strip().lower(): c
                    for c in cocos if isinstance(c, dict)
                }
                # Coco_multiples / margins / ratios arrays must stay aligned
                # with cocos array length, so we pad them when appending stubs.
                cm = payload.setdefault("coco_multiples", [])
                cmg = payload.setdefault("coco_margins", [])
                cr = payload.setdefault("coco_ratios", [])
                if not isinstance(cm, list):  cm = []; payload["coco_multiples"] = cm
                if not isinstance(cmg, list): cmg = []; payload["coco_margins"] = cmg
                if not isinstance(cr, list):  cr = []; payload["coco_ratios"] = cr
                for ticker, flags in pinned_cocos_raw.items():
                    if not isinstance(flags, dict):
                        continue
                    target = by_ticker.get(str(ticker).strip().lower())
                    if target is None:
                        # Pinned ticker missing — inject a stub so the pin persists.
                        # exchange parsed from "NASDAQ:GLBE" / "NYSE:WCC" style.
                        ticker_str = str(ticker).strip()
                        exchange = (
                            ticker_str.split(":")[0].upper().strip()
                            if ":" in ticker_str else None
                        )
                        target = {
                            "tier": 3,
                            "include": bool(flags.get("include", False)),
                            "company": ticker_str,  # placeholder — analyst can rename
                            "ticker": ticker_str,
                            "exchange": exchange,
                            "selected_for_wacc": bool(flags.get("selected_for_wacc", False)),
                            "business_description": "(analyst-pinned; metadata pending)",
                        }
                        cocos.append(target)
                        cm.append({})
                        cmg.append({})
                        cr.append({})
                        continue
                    if "include" in flags:
                        target["include"] = bool(flags["include"])
                    if "selected_for_wacc" in flags:
                        target["selected_for_wacc"] = bool(flags["selected_for_wacc"])
                        # Selected for WACC implies included
                        if flags["selected_for_wacc"]:
                            target["include"] = True

            # Eric 2026-05-08 item 5: WACC β must come from the comps the LLM
            # marked selected_for_wacc, not from its own gut feel. Override only
            # when ≥3 selected comps yielded a valid unlevered beta (else
            # _derive_unlevered_beta returns None and we keep the LLM value as
            # a fallback so a sparse comp set doesn't break the run).
            derived_beta = _derive_unlevered_beta(payload)
            if derived_beta is not None:
                wacc = payload.setdefault("wacc", {})
                pm = wacc.setdefault("per_management", {})
                pm["unlevered_beta"] = derived_beta
                # Also annotate the source so the rationale lands in the workpaper.
                sources = payload.setdefault("sources", {})
                sources["unlevered_beta_per_mgmt"] = {
                    "source": "Calculated",
                    "detail": (
                        f"Median unlevered β = {derived_beta:.3f} across the "
                        f"comparable companies marked selected_for_wacc=true. "
                        f"Each comp unlevered via Hamada: β_u = β_L ÷ (1 + (1−t)·D/E)."
                    ),
                    "notes": "Auto-derived by the pipeline; re-levered to target capital structure inside the DCF.",
                }

            # Eric 2026-05-19 — guarantee revenue_growth_primary is populated
            # so the Projections sheet's Primary cascade has values to read.
            # If the LLM omitted or under-filled the field, fall back to
            # historical 3-yr revenue CAGR clamped to [0, 0.10]; if historical
            # revenue isn't available either, copy revenue_growth clamped to
            # the same cap. Done in a pure post-process so it runs on every
            # retry regardless of LLM output quality.
            _ensure_revenue_growth_primary(payload)

            # Eric 2026-05-17 — apply analyst-pinned overrides AFTER the
            # derived-beta step so a pinned unlevered_beta_pm wins over the
            # comp-derived value. This is the deterministic "preserve these
            # exact values run-to-run" guarantee.
            applied_pinned_keys: list[str] = _apply_pinned_overrides(payload, pinned_overrides)

            last_payload = payload

            model, error = validate_inputs(payload)
            if model is None:
                last_validation_error = error
                last_convergence_feedback = None
                continue  # retry with schema-error feedback

            # Schema validation passed. If a target is set, check DCF EV vs target.
            # Both sides are in actual currency units (the helper scales the
            # workpaper-unit EV up by currency.unit multiplier before returning).
            if target_valuation_effective is not None:
                implied_ev = _implied_dcf_ev_actual(payload)
                last_implied_ev = implied_ev
                if implied_ev is not None and implied_ev > 0:
                    target = float(target_valuation_effective)
                    divergence = abs(implied_ev - target) / target if target > 0 else 0.0
                    if divergence > EV_CONVERGENCE_TOLERANCE and attempt < MAX_ATTEMPTS:
                        direction = "INCREASE" if implied_ev < target else "DECREASE"
                        # Damped step hint: if we're within 2× of target, take a
                        # half-step in the relevant direction. If we're way off,
                        # take a full step. Prevents the oscillation pattern
                        # where over-by-32% becomes under-by-80% in one shot.
                        step_size_hint = (
                            "Take a MODERATE step — change each lever by roughly "
                            f"{divergence*50:.0f}% of its current value, not the full "
                            f"{divergence*100:.0f}% gap. The DCF responds non-linearly to "
                            "compound lever changes; aggressive multi-lever moves overshoot."
                            if divergence < 1.0
                            else "Take a full step — multiple levers may need to move "
                            "together since the gap is large."
                        )
                        last_convergence_feedback = (
                            f"\n\n# GOAL-SEEK CONVERGENCE FEEDBACK (attempt {attempt}/{MAX_ATTEMPTS})\n\n"
                            f"Your assumptions produced a DCF per-management EV of "
                            f"**{implied_ev:.0f}**, but the target is **{target:.0f}** "
                            f"(off by {divergence*100:.1f}%, need to {direction} EV by "
                            f"{abs(implied_ev - target):.0f}).\n\n"
                            f"{step_size_hint}\n\n"
                            f"Re-emit the FULL JSON with adjusted levers to close this gap. "
                            f"Recall the lever ordering: revenue_growth first, then margins, "
                            f"then capex/D&A/NWC intensity, then WACC components, then terminal "
                            f"growth (terminal is capped — do not exceed 3.5% developed / 5% "
                            f"emerging). Stay within the defensibility guardrails — if you "
                            f"cannot hit ±10% without breaking them, get as close as possible "
                            f"and document the residual gap in engagement.report_purpose. "
                            f"DO NOT pull every lever in the same direction at once — that's "
                            f"how the prior attempt overshot. Pick the 1-2 levers furthest from "
                            f"defensible best-case and adjust ONLY those."
                        )
                        last_validation_error = None
                        continue  # retry with goal-seek feedback
            # Deterministic post-process: if a target is set and the LLM loop
            # didn't converge within tolerance, scale revenue_growth uniformly
            # so the DCF EV lands exactly on target. This is the safety net
            # behind "always output to the target valuation" — the LLM is
            # stochastic, this isn't.
            calibration_applied: float | None = None
            if (
                target_valuation_effective is not None
                and last_implied_ev is not None
                and last_implied_ev > 0
                and abs(last_implied_ev - float(target_valuation_effective)) / float(target_valuation_effective) > EV_CONVERGENCE_TOLERANCE
            ):
                calibration_applied = _calibrate_to_target(
                    payload, float(target_valuation_effective),
                    pinned_keys=applied_pinned_keys,
                )
                if calibration_applied is not None:
                    # Defensive re-apply: calibration is supposed to skip
                    # pinned indices but a buggy edit shouldn't be able to
                    # clobber an analyst pin silently.
                    if pinned_overrides:
                        _apply_pinned_overrides(payload, pinned_overrides)
                    # Recompute implied EV with calibrated growth array
                    last_implied_ev = _implied_dcf_ev_actual(payload)
                    # Note the calibration in sources so the audit trail is honest
                    sources = payload.setdefault("sources", {})
                    src = sources.get("target_valuation") or {}
                    note = (
                        f"Growth array post-calibrated by {calibration_applied:.3f}x after "
                        f"{attempt} LLM goal-seek attempts to anchor DCF EV to client target."
                    )
                    src_notes = (src.get("notes") or "").strip()
                    src["notes"] = f"{src_notes} · {note}" if src_notes else note
                    sources["target_valuation"] = src

            # Success path: schema valid and (if target set) EV within tolerance,
            # OR we exhausted attempts (best effort).
            message_parts = [
                f"Produced valuation inputs JSON ({len(json.dumps(payload))} bytes; "
                f"validated on attempt {attempt}/{MAX_ATTEMPTS}; "
                f"cache_read={usage_totals['cache_read_input_tokens']} tokens)"
            ]
            if target_valuation_effective is not None and last_implied_ev is not None:
                target = float(target_valuation_effective)
                gap = abs(last_implied_ev - target) / target if target > 0 else 0.0
                message_parts.append(
                    f"DCF EV {last_implied_ev:.0f} vs target {target:.0f} "
                    f"(gap {gap*100:.1f}%"
                    + (f"; calibrated {calibration_applied:.3f}x" if calibration_applied else "")
                    + ")"
                )
            return SkillResult.success(
                data=payload,
                message=" · ".join(message_parts),
                artifacts={
                    "valuation_inputs": payload,
                    "usage": usage_totals,
                    "validation_attempts": attempt,
                    "implied_dcf_ev": last_implied_ev,
                    "target_valuation": target_valuation_effective,
                },
                token_usage=usage_totals["input_tokens"] + usage_totals["output_tokens"],
            )

        # Both attempts failed validation. Surface the errors plus the last
        # payload so the analyst can inspect / repair manually.
        return SkillResult.failed(
            f"Valuation inputs failed schema validation after {attempts_made} attempts. "
            f"Last errors:\n{last_validation_error}",
            artifacts={
                "last_payload": last_payload,
                "usage": usage_totals,
                "validation_attempts": attempts_made,
            },
        )
