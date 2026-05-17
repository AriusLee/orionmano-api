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


def _calibrate_to_target(payload: dict, target_actual: float) -> float | None:
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

    def apply(multiplier: float) -> None:
        proj["revenue_growth"] = [min(g * multiplier, GROWTH_CAP) for g in base_g]
        if base_m is not None:
            proj["gross_margin"] = [min(m * multiplier, GM_CAP) for m in base_m]
        # Mirror to segments (top-level array is the cascade base when no
        # segments; when segments are present, their arrays drive the totals).
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

# Task

Produce a JSON object that conforms to the schema document above. Use the company context to fill as many fields as possible. For fields you cannot determine from the context, use sensible defaults consistent with US/Nasdaq IPO advisory practice.{goal_seek_block}

# Market-aligned assumptions (Eric 2026-05-08 item 3)

Every growth rate, margin, WACC component, terminal-value parameter, and comp-set assumption MUST be defensible against current market conditions AND the target's business-development plan (BDP). Specifically:

- **Revenue growth & gross margin:** anchor to (a) the target's stated BDP / management projections if present in the documents, (b) recent comparable-company growth rates as a ceiling reality-check, and (c) industry-standard maturity curves (high-growth in early years, decaying toward terminal). If the BDP is absent, infer from historical FS trajectory + segment commentary. **When goal-seek mode is active, lean toward the upper end of the defensible range; when no target is set, lean toward the anchor.**
- **WACC inputs (risk_free, ERP, country risk, beta):** anchor risk_free_rate to a current sovereign-yield observation (cite the date), ERP to Damodaran's most recent implied ERP, country risk to Damodaran's country table, and unlevered_beta to the median of the comps marked `selected_for_wacc=true` (not a generic industry average).
- **Terminal growth:** must be ≤ long-run nominal GDP of the target's primary market AND consistent with industry-maturity expectations. Anything >3.5% for a developed-market company is hard to defend.
- **Margin progression:** if you project gross_margin or EBITDA-margin expansion, the trajectory must be justified by operating-leverage evidence in the documents (segment-mix shift, scale, automation). Do not assume universal margin expansion absent evidence.
- **Comp multiples:** the median comp multiple is only defensible if the comp set genuinely matches the target on size, growth, margin profile, and geography. If the target is sub-scale relative to the comps, apply a size discount in `size_premium`.

Every assumption above must have a `sources.<id>` entry whose `source` + `detail` cite the EXACT evidence (FS page, Damodaran retrieval date, BDP slide number, comp filing). Generic "Manual" sourcing is only acceptable when no document evidence exists AND the assumption is a regulator-standard convention.

# Required completeness

Every section listed below MUST be present in the output:

- `engagement` — all 13 fields (company_name, company_country, company_industry_us, company_industry_global, valuation_date, target_valuation, exchange_platform, report_purpose, accounting_standard, engagement_team{{partner,manager,department}}, client_name). `target_valuation` is the client's stated target valuation in **ACTUAL currency units** — NOT scaled by `currency.unit`. A $1B target is written as `1000000000`, NOT `1000000` (even when the workpaper unit is `'000`). Leave null if not provided by the user. `exchange_platform` is the exchange the comparable-company pool must be drawn from (e.g. "NASDAQ", "NYSE"); default to "NASDAQ" if not specified — comps not listed on this exchange must be excluded.
- `currency` — primary, unit, alt, fx_rate_alt
- `tax` — jurisdiction, type ("flat"/"two_tier"/"progressive"), rate_low, rate_high, threshold, effective_rate_override
- `projections` — years (typically 5), revenue_growth_method, **revenue_y0** (last reported full-year revenue, in the same currency × unit as the workpaper), **nwc_y0** (audited Y0 NWC = current assets ex-cash − current liabilities ex-debt), and Y1-Y5 arrays for revenue_growth, gross_margin, opex_pct_revenue, capex_pct_revenue, dep_pct_revenue, nwc_pct_sales (all 6 arrays, each length-5). **revenue_y0 is the cascade base — without it the workpaper math is dead.**
- `projections.segments` (OPTIONAL but RECOMMENDED when the target has distinct business lines) — array of segments, each `{{name, start_year, revenue_y0 (if start_year=0) or initial_revenue (if start_year>0), revenue_growth[], gross_margin[] OR cogs_pct[]}}`. When provided, total revenue & gross profit at each year are the SUM across all active segments; the top-level revenue_growth + gross_margin arrays are then IGNORED for the cascade (still emit them for back-compat, but make the segment numbers the authoritative breakdown). Segments with `start_year > 0` model new revenue streams launched mid-projection (Eric 2026-05-08 item 2: "user can add new revenue streams with corresponding COGS during the projection period"). The sum of all segment revenue_y0 (for start_year=0 segments) MUST equal the top-level revenue_y0 — otherwise the workpaper Y0 base mismatches the audited FS.
- `historical_fs` — 5-year arrays (FY-5..FY-1, oldest first; pad with null where data is missing) for: revenue, cogs, gross_profit, opex_total, sga, rnd, ebitda, da, ebit, interest_expense, other_income_expense, profit_before_tax, tax_expense, net_income, cash, accounts_receivable, inventory, prepaid_expenses, total_current_assets, ppe, intangibles, other_lt_assets, total_assets, accounts_payable, short_term_debt, other_current_liabilities, total_current_liabilities, long_term_debt, other_lt_liabilities, total_liabilities, total_equity. Pull from audited financial statements when available — fewer than 5 years OK; pad missing years with `null` (NOT 0).
- `terminal` — method ("gordon_growth"), growth_rate, exit_multiple_type, exit_multiple_value
- `wacc.shared` — risk_free_rate, risk_free_rate_source, equity_risk_premium, country_risk_premium
- `wacc.per_management` — unlevered_beta, target_debt_to_equity, size_premium, specific_risk_premium, pretax_cost_of_debt, target_debt_weight, target_equity_weight
- `wacc.independent` — same fields, slightly more conservative (higher beta, higher specific risk, higher D/E)
- `cocos` — array of 0-30 comparable companies with (tier, include, company, ticker, exchange, business_description, selected_for_wacc, country, accounting, market_cap_usd_mm, d_to_e, raw_beta, tax_rate). **Exchange filter rule:** every comp's `exchange` field MUST equal `engagement.exchange_platform` — comps listed on other exchanges are excluded by the pipeline. **Selection rule:** screen ~20 comps total; mark 5–6 with `selected_for_wacc=true` (the most directly comparable ones, used for the WACC beta build); the remainder are reference/peer comps with `selected_for_wacc=false`. **business_description** is a one-line description of what the comp does (e.g. "Document-oriented NoSQL database"). **Tier 3 size cap rule:** comparables (especially Tier 3) must be within ~10× the target's enterprise value. Do NOT include megacap reference comps that are 100×+ the target's size — they distort the median multiples. If the target's market cap is unclear, use revenue × industry-typical EV/Sales as a proxy.
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
                    payload, float(target_valuation_effective)
                )
                if calibration_applied is not None:
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
