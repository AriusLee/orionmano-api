"""Pure-Python computation of valuation headline values from the Inputs JSON.

Mirrors the Excel formula logic so the frontend can render a dashboard without
having to open or parse the xlsx. Used by the workpaper generation pipeline to
emit a summary alongside the xlsx file. All sign conventions match the Excel
skeleton (revenue/profit positive; expenses/capex/tax/d_nwc stored negative).
"""
from __future__ import annotations

from typing import Any


def _g(obj: Any, *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _safe_div(a: float, b: float) -> float:
    return a / b if b not in (0, None) else 0.0


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    idx = q * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    frac = idx - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _scenario_wacc(inputs: dict, scenario: str) -> dict[str, float]:
    """Compute Ke, after-tax Kd, WACC for one scenario (per_management or independent)."""
    shared = _g(inputs, "wacc", "shared", default={}) or {}
    s = _g(inputs, "wacc", scenario, default={}) or {}
    tax = _g(inputs, "tax", default={}) or {}

    rfr = float(shared.get("risk_free_rate") or 0)
    erp = float(shared.get("equity_risk_premium") or 0)
    crp = float(shared.get("country_risk_premium") or 0)

    unlevered_beta = float(s.get("unlevered_beta") or 0)
    de = float(s.get("target_debt_to_equity") or 0)
    size_prem = float(s.get("size_premium") or 0)
    spec_prem = float(s.get("specific_risk_premium") or 0)
    pretax_kd = float(s.get("pretax_cost_of_debt") or 0)
    debt_w = float(s.get("target_debt_weight") or 0)
    equity_w = float(s.get("target_equity_weight") or 0)

    eff_tax = tax.get("effective_rate_override")
    if eff_tax is None:
        eff_tax = float(tax.get("rate_high") or 0)
    eff_tax = float(eff_tax)

    levered_beta = unlevered_beta * (1 + (1 - eff_tax) * de)
    ke = rfr + levered_beta * erp + crp + size_prem + spec_prem
    kd_after = pretax_kd * (1 - eff_tax)
    wacc = ke * equity_w + kd_after * debt_w

    return {
        "effective_tax_rate": eff_tax,
        "levered_beta": levered_beta,
        "cost_of_equity": ke,
        "aftertax_cost_of_debt": kd_after,
        "wacc": wacc,
        "components": {
            "risk_free_rate": rfr,
            "equity_risk_premium": erp,
            "country_risk_premium": crp,
            "size_premium": size_prem,
            "specific_risk_premium": spec_prem,
            "pretax_cost_of_debt": pretax_kd,
            "debt_weight": debt_w,
            "equity_weight": equity_w,
            "unlevered_beta": unlevered_beta,
            "target_d_to_e": de,
        },
    }


def _at(arr: list | None, idx: int) -> float:
    """Segment-local array access: clamp to last value past the end, 0 before start."""
    if not arr:
        return 0.0
    if idx < 0:
        return 0.0
    v = arr[-1] if idx >= len(arr) else arr[idx]
    return float(v) if v is not None else 0.0


def _segment_series(seg: dict, n_years: int) -> tuple[list[float], list[float]]:
    """For one segment, return (revenue, gross_profit) arrays of length n_years+1
    indexed by y_index 0..n_years (0=Y0). Inactive years are zero. Eric
    2026-05-08 item 2: a segment may start mid-projection via start_year > 0."""
    start = int(seg.get("start_year") or 0)
    if start == 0:
        r0 = float(seg.get("revenue_y0") or 0)
    else:
        r0 = float(seg.get("initial_revenue") or 0)
    growth = seg.get("revenue_growth") or []
    gm_arr = seg.get("gross_margin")
    cogs_arr = seg.get("cogs_pct")

    revenue = [0.0] * (n_years + 1)
    gross_profit = [0.0] * (n_years + 1)
    for y in range(n_years + 1):
        if y < start:
            continue
        if y == start:
            revenue[y] = r0
        else:
            g = _at(growth, (y - start) - 1)
            revenue[y] = revenue[y - 1] * (1 + g)
        # Gross margin indexed from segment-local year 0 = start year
        if gm_arr:
            gm = _at(gm_arr, y - start)
        elif cogs_arr:
            gm = 1 - _at(cogs_arr, y - start)
        else:
            gm = 0.0
        gross_profit[y] = revenue[y] * gm
    return revenue, gross_profit


def _projections(inputs: dict) -> dict[str, list[float]]:
    """Build year-by-year revenue / EBITDA / FCFF lines from drivers.

    Revenue & gross-profit can come from one of two paths:
      (a) Flat: top-level revenue_y0 + revenue_growth[] + gross_margin[].
      (b) Segmented (Eric 2026-05-08 item 2): projections.segments[] each with
          its own revenue/COGS trajectory and start_year. Totals are summed
          across segments per year; the rest of the cascade (opex %, capex %,
          NWC %, depreciation %) is unchanged and applies to total revenue.
    Path (b) wins when segments is non-empty; otherwise (a) is used."""
    p = _g(inputs, "projections", default={}) or {}
    tax = _g(inputs, "tax", default={}) or {}

    rev_y0 = float(p.get("revenue_y0") or 0)
    nwc_y0 = float(p.get("nwc_y0") or 0)
    n_years = int(p.get("years") or 5)

    def vec(key: str) -> list[float]:
        arr = p.get(key) or []
        return [float(x) if x is not None else 0.0 for x in arr[:n_years]] + [0.0] * max(0, n_years - len(arr or []))

    opex = vec("opex_pct_revenue")
    capex = vec("capex_pct_revenue")
    dep = vec("dep_pct_revenue")
    nwc_pct = vec("nwc_pct_sales")

    eff_tax = tax.get("effective_rate_override")
    if eff_tax is None:
        eff_tax = float(tax.get("rate_high") or 0)
    eff_tax = float(eff_tax)

    segments = p.get("segments") or []
    seg_series: list[tuple[dict, list[float], list[float]]] = []
    if segments:
        # Path (b): aggregate per-segment revenue + gross_profit across all segments
        for s in segments:
            r, gp = _segment_series(s, n_years)
            seg_series.append((s, r, gp))
        revenue = [sum(r[y] for _, r, _ in seg_series) for y in range(n_years + 1)]
        gross_profit = [sum(gp[y] for _, _, gp in seg_series) for y in range(1, n_years + 1)]
    else:
        # Path (a): existing flat cascade
        growth = vec("revenue_growth")
        gm = vec("gross_margin")
        revenue = [rev_y0]
        for y in range(n_years):
            revenue.append(revenue[-1] * (1 + growth[y]))
        gross_profit = [revenue[y + 1] * gm[y] for y in range(n_years)]
    # revenue[0] = Y0, revenue[1..n] = Y1..Yn; gross_profit indexed 0..n-1 = Y1..Yn

    # Opex carve-out: segments carrying their own opex_pct_revenue (related
    # S&M/distribution costs of an additional revenue stream) are excluded from
    # the top-level opex base and charged their own ratio instead. Segments
    # without a ratio stay on the top-level ratio, so with no carve-outs this
    # reduces exactly to -revenue_total * opex_pct (the original formula).
    def _seg_opex_amt(s: dict, r: list[float]) -> list[float]:
        start = int(s.get("start_year") or 0)
        arr = s.get("opex_pct_revenue") or []
        return [-r[y + 1] * _at(arr, (y + 1) - start) for y in range(n_years)]

    carved = [(s, r) for s, r, _ in seg_series if s.get("opex_pct_revenue")]
    carved_opex = [_seg_opex_amt(s, r) for s, r in carved]
    opex_amt = []
    for y in range(n_years):
        carved_rev = sum(r[y + 1] for _, r in carved)
        base = -(revenue[y + 1] - carved_rev) * opex[y]
        opex_amt.append(base + sum(co[y] for co in carved_opex))
    ebitda = [gross_profit[y] + opex_amt[y] for y in range(n_years)]
    da = [-revenue[y + 1] * dep[y] for y in range(n_years)]
    ebit = [ebitda[y] + da[y] for y in range(n_years)]
    tax_amt = [-max(ebit[y], 0) * eff_tax for y in range(n_years)]
    capex_amt = [-revenue[y + 1] * capex[y] for y in range(n_years)]
    nwc = [revenue[y + 1] * nwc_pct[y] for y in range(n_years)]
    d_nwc = []
    prev_nwc = nwc_y0
    for y in range(n_years):
        d_nwc.append(-(nwc[y] - prev_nwc))
        prev_nwc = nwc[y]
    fcff = [ebit[y] + tax_amt[y] + (-da[y]) + capex_amt[y] + d_nwc[y] for y in range(n_years)]

    # Per-stream breakdown so incremental COGS / related opex from each revenue
    # stream is visible in outputs ("COGS – Stream A", "Related Opex – Stream A").
    by_segment: list[dict[str, Any]] = []
    for s, r, gp in seg_series:
        has_own_opex = bool(s.get("opex_pct_revenue"))
        if has_own_opex:
            seg_opex = _seg_opex_amt(s, r)
        else:
            # Allocation at the top-level ratio — display-only, does not change totals
            seg_opex = [-r[y + 1] * opex[y] for y in range(n_years)]
        by_segment.append({
            "name": s.get("name"),
            "source": s.get("source") or ("additional_stream" if int(s.get("start_year") or 0) > 0 else "core"),
            "start_year": int(s.get("start_year") or 0),
            "revenue": r,
            "gross_profit": gp[1:],
            "cogs": [-(r[y + 1] - gp[y + 1]) for y in range(n_years)],
            "opex": seg_opex,
            "opex_is_allocation": not has_own_opex,
            "growth_basis": s.get("growth_basis"),
            "contractual_support": s.get("contractual_support"),
        })

    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "ebitda": ebitda,
        "da": da,
        "ebit": ebit,
        "tax": tax_amt,
        "capex": capex_amt,
        "nwc": nwc,
        "d_nwc": d_nwc,
        "fcff": fcff,
        "by_segment": by_segment,
    }


def _dcf_ev(fcff: list[float], wacc: float, terminal_method: str,
            terminal_g: float, exit_multiple_value: float | None,
            terminal_metric_y5: float) -> dict[str, float]:
    """Discount explicit FCFF + terminal value to enterprise value."""
    if wacc <= 0:
        return {"sum_pv_explicit": 0.0, "terminal_value": 0.0,
                "pv_terminal": 0.0, "ev": 0.0}
    pv = 0.0
    discounted = []
    for y, cf in enumerate(fcff, start=1):
        df = 1 / ((1 + wacc) ** y)
        pv += cf * df
        discounted.append(cf * df)
    if terminal_method == "exit_multiple" and exit_multiple_value:
        tv = float(terminal_metric_y5) * float(exit_multiple_value)
    else:
        tv = (fcff[-1] * (1 + terminal_g)) / (wacc - terminal_g) if wacc > terminal_g else 0.0
    pv_tv = tv / ((1 + wacc) ** len(fcff)) if fcff else 0.0
    return {
        "sum_pv_explicit": pv,
        "pv_explicit_by_year": discounted,
        "terminal_value": tv,
        "pv_terminal": pv_tv,
        "ev": pv + pv_tv,
    }


def _equity_bridge(ev: float, inputs: dict, hist_net_debt: float) -> dict[str, float]:
    b = _g(inputs, "bridge", default={}) or {}
    surplus = float(b.get("surplus_assets") or 0)
    non_op = float(b.get("non_operating_assets") or 0)
    nd_override = b.get("net_debt_override")
    net_debt = float(nd_override) if nd_override is not None else hist_net_debt
    minority = float(b.get("minority_interests") or 0)

    equity_pre = ev + surplus + non_op - net_debt - minority

    dlom = float(b.get("dlom_pct") or 0)
    dloc = float(b.get("dloc_pct") or 0)
    after_dlom = equity_pre * (1 - dlom)
    after_dloc = after_dlom * (1 - dloc)

    interest_pct = float(b.get("equity_interest_pct") or 1)
    client_value = after_dloc * interest_pct

    return {
        "ev": ev,
        "surplus_assets": surplus,
        "non_operating_assets": non_op,
        "net_debt": net_debt,
        "minority_interests": minority,
        "equity_pre_discount": equity_pre,
        "dlom_pct": dlom,
        "after_dlom": after_dlom,
        "dloc_pct": dloc,
        "after_dloc": after_dloc,
        "equity_interest_pct": interest_pct,
        "client_value": client_value,
    }


def _per_share(equity_value: float, inputs: dict) -> dict[str, float | None]:
    b = _g(inputs, "bridge", default={}) or {}
    cu = _g(inputs, "currency", default={}) or {}
    unit = (cu.get("unit") or "actual").strip().strip("'")
    multiplier = {"000": 1_000, "million": 1_000_000, "actual": 1}.get(unit, 1)

    basic = b.get("shares_outstanding")
    diluted = b.get("shares_outstanding_diluted") or basic
    pps_basic = (equity_value * multiplier / float(basic)) if basic else None
    pps_diluted = (equity_value * multiplier / float(diluted)) if diluted else None
    return {"basic": pps_basic, "diluted": pps_diluted}


def _historical_net_debt(inputs: dict) -> float:
    """Most-recent FY (FY-1) net debt = ST debt + LT debt − cash. Returns 0 if missing."""
    h = _g(inputs, "historical_fs", default={}) or {}

    def latest(arr_key: str) -> float:
        arr = h.get(arr_key) or []
        for v in reversed(arr):
            if v is not None:
                return float(v)
        return 0.0

    st_debt = abs(latest("short_term_debt"))
    lt_debt = abs(latest("long_term_debt"))
    cash = abs(latest("cash"))
    return st_debt + lt_debt - cash


def _coco_stats(inputs: dict) -> dict[str, dict[str, float]]:
    """For each multiple metric, compute Q1/Median/Q3 across included CoCos.

    Filters: (1) include flag, (2) exchange match against
    engagement.exchange_platform when both are populated (Eric 2026-05-08 item 5
    — comps listed on a different exchange must not pollute the multiples),
    (3) Eric 2026-05-19 #6 — IQR outlier removal: values outside
    [Q1 − 1.5·IQR, Q3 + 1.5·IQR] are dropped from the included population
    before recomputing the final stats so a single distortive comp doesn't
    pull the median.
    Comps with no exchange field are kept (backward-compat for older data;
    new LLM-produced data always carries the exchange field)."""
    cocos = _g(inputs, "cocos", default=[]) or []
    multiples = _g(inputs, "coco_multiples", default=[]) or []
    exchange_platform = _g(inputs, "engagement", "exchange_platform", default=None)
    n = min(len(cocos), len(multiples))
    metrics = ["ev_sales_ltm", "ev_sales_ntm", "ev_ebitda_ltm",
               "ev_ebitda_ntm", "pe_ltm", "pe_ntm"]
    out: dict[str, dict[str, float]] = {}
    for m in metrics:
        raw_vals: list[float] = []
        for i in range(n):
            if not cocos[i].get("include", True):
                continue
            if exchange_platform:
                comp_exchange = cocos[i].get("exchange")
                if comp_exchange and comp_exchange != exchange_platform:
                    continue
            v = (multiples[i] or {}).get(m)
            if v is None:
                continue
            try:
                raw_vals.append(float(v))
            except (TypeError, ValueError):
                continue
        # IQR outlier removal — need at least 4 values to compute meaningful
        # Q1/Q3. With fewer, skip the filter (otherwise we'd over-trim a
        # sparse population).
        outlier_count = 0
        if len(raw_vals) >= 4:
            q1 = _percentile(raw_vals, 0.25)
            q3 = _percentile(raw_vals, 0.75)
            iqr = q3 - q1
            lo_bound = q1 - 1.5 * iqr
            hi_bound = q3 + 1.5 * iqr
            cleaned = [v for v in raw_vals if lo_bound <= v <= hi_bound]
            outlier_count = len(raw_vals) - len(cleaned)
            vals = cleaned
        else:
            vals = raw_vals
        out[m] = {
            "q1": _percentile(vals, 0.25),
            "median": _percentile(vals, 0.50),
            "q3": _percentile(vals, 0.75),
            "n": float(len(vals)),
            "outliers_removed": float(outlier_count),
        }
    return out


def _football_field(dcf_ev_pm: float, dcf_ev_indep: float,
                    coco_stats: dict, proj: dict, inputs: dict,
                    bridge_pm: dict) -> dict[str, Any]:
    """Build football-field bands for each methodology."""
    rev_y1 = proj["revenue"][1] if len(proj["revenue"]) > 1 else 0
    ebitda_y1 = proj["ebitda"][0] if proj["ebitda"] else 0
    ni_proxy_y1 = (proj["ebit"][0] if proj["ebit"] else 0) * (1 - bridge_pm.get("effective_tax_rate", 0.21))
    surplus = bridge_pm["surplus_assets"]
    non_op = bridge_pm["non_operating_assets"]
    net_debt = bridge_pm["net_debt"]
    minority = bridge_pm["minority_interests"]

    # Comps implied EV
    s_low = (coco_stats.get("ev_sales_ntm") or {}).get("q1", 0) * rev_y1
    s_mid = (coco_stats.get("ev_sales_ntm") or {}).get("median", 0) * rev_y1
    s_high = (coco_stats.get("ev_sales_ntm") or {}).get("q3", 0) * rev_y1

    e_low = (coco_stats.get("ev_ebitda_ntm") or {}).get("q1", 0) * ebitda_y1
    e_mid = (coco_stats.get("ev_ebitda_ntm") or {}).get("median", 0) * ebitda_y1
    e_high = (coco_stats.get("ev_ebitda_ntm") or {}).get("q3", 0) * ebitda_y1

    # P/E gives equity → bridge back to EV
    p_low_eq = (coco_stats.get("pe_ntm") or {}).get("q1", 0) * ni_proxy_y1
    p_mid_eq = (coco_stats.get("pe_ntm") or {}).get("median", 0) * ni_proxy_y1
    p_high_eq = (coco_stats.get("pe_ntm") or {}).get("q3", 0) * ni_proxy_y1
    bridge_back = -surplus - non_op + net_debt + minority
    p_low = p_low_eq + bridge_back
    p_mid = p_mid_eq + bridge_back
    p_high = p_high_eq + bridge_back

    comps_lows = [v for v in (s_low, e_low, p_low) if v != 0]
    comps_highs = [v for v in (s_high, e_high, p_high) if v != 0]
    comps_mids = [v for v in (s_mid, e_mid, p_mid) if v != 0]
    comps_low = min(comps_lows) if comps_lows else 0
    comps_high = max(comps_highs) if comps_highs else 0
    comps_mid = sum(comps_mids) / len(comps_mids) if comps_mids else 0

    # Precedents — mean EV/EBITDA × EBITDA Y1 (or use given ev_usd_mm)
    precedents = _g(inputs, "precedents", default=[]) or []
    prec_evs = []
    for p in precedents:
        if not p.get("include", True):
            continue
        if p.get("ev_ebitda") and ebitda_y1:
            prec_evs.append(float(p["ev_ebitda"]) * ebitda_y1)
    prec_low = min(prec_evs) if prec_evs else 0
    prec_high = max(prec_evs) if prec_evs else 0
    prec_mid = sum(prec_evs) / len(prec_evs) if prec_evs else 0

    ff = _g(inputs, "football_field", default={}) or {}
    w_dcf = float(ff.get("weight_dcf") or 0)
    w_comps = float(ff.get("weight_comps") or 0)
    w_prec = float(ff.get("weight_precedent") or 0)

    dcf_low = min(dcf_ev_pm, dcf_ev_indep)
    dcf_high = max(dcf_ev_pm, dcf_ev_indep)
    dcf_mid = (dcf_ev_pm + dcf_ev_indep) / 2

    weighted_mid = dcf_mid * w_dcf + comps_mid * w_comps + prec_mid * w_prec

    return {
        "dcf": {"low": dcf_low, "mid": dcf_mid, "high": dcf_high, "weight": w_dcf},
        "comps": {"low": comps_low, "mid": comps_mid, "high": comps_high, "weight": w_comps},
        "comps_breakdown": {
            "ev_sales_ntm": {"low": s_low, "mid": s_mid, "high": s_high},
            "ev_ebitda_ntm": {"low": e_low, "mid": e_mid, "high": e_high},
            "pe_ntm": {"low": p_low, "mid": p_mid, "high": p_high},
        },
        "precedent": {"low": prec_low, "mid": prec_mid, "high": prec_high, "weight": w_prec},
        "weighted_mid": weighted_mid,
        "selected_low": ff.get("selected_low"),
        "selected_mid": ff.get("selected_mid"),
        "selected_high": ff.get("selected_high"),
    }


CROSS_CHECK_TOLERANCE = 0.10


def _cross_checks(dcf_ev_pm: float, ff: dict, coco_stats: dict, inputs: dict) -> dict[str, Any]:
    """DCF is the sole primary methodology; Market Approach and Recent
    Transactions are cross-checks. Each implied EV is compared against the DCF
    EV: both within ±10% ⇒ 'within_reasonable_range', either outside ⇒
    'outside_cross_check_range' (report must flag and explain)."""
    comps_n = max(
        (int((coco_stats.get(m) or {}).get("n") or 0)
         for m in ("ev_sales_ntm", "ev_ebitda_ntm", "pe_ntm")),
        default=0,
    )
    precedents = _g(inputs, "precedents", default=[]) or []
    prec_n = sum(1 for p in precedents if p.get("include", True) and p.get("ev_ebitda"))

    checks = []
    for method, block, n in (
        ("market_approach_comps", ff.get("comps") or {}, comps_n),
        ("precedent_transactions", ff.get("precedent") or {}, prec_n),
    ):
        implied = float(block.get("mid") or 0)
        if not implied or not dcf_ev_pm:
            checks.append({
                "method": method, "implied_ev": implied or None,
                "low": block.get("low"), "high": block.get("high"),
                "variance_pct": None, "within_range": None,
                "available": False, "n": n,
            })
            continue
        variance = (implied - dcf_ev_pm) / dcf_ev_pm
        checks.append({
            "method": method, "implied_ev": implied,
            "low": block.get("low"), "high": block.get("high"),
            "variance_pct": variance,
            "within_range": abs(variance) <= CROSS_CHECK_TOLERANCE,
            "available": True, "n": n,
        })

    available = [c for c in checks if c["available"]]
    if not available:
        verdict = "not_available"
    elif all(c["within_range"] for c in available):
        verdict = "within_reasonable_range"
    else:
        verdict = "outside_cross_check_range"
    return {
        "primary_ev": dcf_ev_pm,
        "tolerance_pct": CROSS_CHECK_TOLERANCE,
        "checks": checks,
        "verdict": verdict,
    }


DEFAULT_NOMINAL_GDP_GROWTH = 0.04  # long-run US nominal GDP proxy when inputs omit it


def _validation_flags(inputs: dict, proj: dict, cross_checks: dict) -> list[dict[str, Any]]:
    """Deterministic checks the report must disclose (client requirement, item 9):
    (a) terminal g at/above nominal GDP − 50bps; (b) EV heavily driven by
    unproven new segments without contractual support; (c) cross-check outside
    the ±10% range."""
    flags: list[dict[str, Any]] = []

    terminal = _g(inputs, "terminal", default={}) or {}
    t_growth = float(terminal.get("growth_rate") or 0)
    gdp_raw = terminal.get("nominal_gdp_growth")
    gdp = float(gdp_raw) if gdp_raw is not None else DEFAULT_NOMINAL_GDP_GROWTH
    if t_growth >= gdp - 0.005:
        flags.append({
            "code": "terminal_g_vs_gdp",
            "severity": "warning",
            "message": (
                f"Terminal growth rate {t_growth:.2%} is at or above nominal GDP "
                f"{gdp:.2%} − 50bps and must be explicitly justified in the report."
            ),
            "data": {"terminal_g": t_growth, "nominal_gdp": gdp,
                     "gdp_is_default": gdp_raw is None, "threshold": gdp - 0.005},
        })

    new_segs = [s for s in (proj.get("by_segment") or [])
                if s.get("source") == "additional_stream" or (s.get("start_year") or 0) > 0]
    total_y_final = proj["revenue"][-1] if proj.get("revenue") else 0
    if new_segs and total_y_final:
        new_rev = sum(s["revenue"][-1] for s in new_segs)
        share = new_rev / total_y_final
        unsupported = [s.get("name") or "?" for s in new_segs
                       if not (s.get("contractual_support") or "").strip()]
        if share > 0.30 and unsupported:
            flags.append({
                "code": "unproven_segment_concentration",
                "severity": "warning",
                "message": (
                    f"New/unproven revenue streams contribute {share:.0%} of final-year "
                    f"revenue without contractual support ({', '.join(unsupported)}). "
                    f"This must be clearly disclosed in the risk and assumption sections."
                ),
                "data": {"y_final_revenue_share_new_segments": share,
                         "segments_without_support": unsupported},
            })

    if cross_checks.get("verdict") == "outside_cross_check_range":
        outside = [c["method"] for c in cross_checks.get("checks", [])
                   if c.get("available") and not c.get("within_range")]
        flags.append({
            "code": "cross_check_variance",
            "severity": "info",
            "message": (
                f"Cross-check implied EV outside ±10% of the DCF enterprise value: "
                f"{', '.join(outside)}. The report must flag this and briefly comment "
                f"on likely reasons (limited comparables, outlier transactions, sector conditions)."
            ),
            "data": {"methods_outside": outside},
        })

    return flags


def _sensitivity_grid(fcff: list[float], wacc_base: float, terminal_g_base: float,
                      inputs: dict) -> dict[str, Any]:
    """7×7 grid (WACC × terminal g) of EV under Gordon-growth terminal."""
    sens = _g(inputs, "sensitivity", default={}) or {}
    w_step = float(sens.get("wacc_step") or 0.005)
    w_count = int(sens.get("wacc_count") or 3)
    g_step = float(sens.get("terminal_g_step") or 0.005)
    g_count = int(sens.get("terminal_g_count") or 3)

    wacc_axis = [wacc_base + (i - w_count) * w_step for i in range(2 * w_count + 1)]
    g_axis = [terminal_g_base + (j - g_count) * g_step for j in range(2 * g_count + 1)]

    grid: list[list[float | None]] = []
    for w in wacc_axis:
        row: list[float | None] = []
        for g in g_axis:
            if w <= g:
                row.append(None)
                continue
            pv = sum(cf / ((1 + w) ** y) for y, cf in enumerate(fcff, start=1))
            tv = (fcff[-1] * (1 + g)) / (w - g)
            pv_tv = tv / ((1 + w) ** len(fcff))
            row.append(pv + pv_tv)
        grid.append(row)
    return {
        "wacc_axis": wacc_axis,
        "terminal_g_axis": g_axis,
        "grid": grid,
        "base_row": w_count,
        "base_col": g_count,
    }


def compute_summary(inputs: dict) -> dict[str, Any]:
    """Top-level entry: take Inputs JSON, return a dashboard-ready summary."""
    proj = _projections(inputs)
    wacc_pm = _scenario_wacc(inputs, "per_management")
    wacc_indep = _scenario_wacc(inputs, "independent")
    terminal = _g(inputs, "terminal", default={}) or {}
    t_method = terminal.get("method", "gordon_growth")
    t_growth = float(terminal.get("growth_rate") or 0)
    t_exit = terminal.get("exit_multiple_value")
    ebitda_y5 = proj["ebitda"][-1] if proj["ebitda"] else 0

    dcf_pm = _dcf_ev(proj["fcff"], wacc_pm["wacc"], t_method, t_growth, t_exit, ebitda_y5)
    dcf_indep = _dcf_ev(proj["fcff"], wacc_indep["wacc"], t_method, t_growth, t_exit, ebitda_y5)

    hist_net_debt = _historical_net_debt(inputs)
    bridge_pm = _equity_bridge(dcf_pm["ev"], inputs, hist_net_debt)
    bridge_pm["effective_tax_rate"] = wacc_pm["effective_tax_rate"]
    bridge_indep = _equity_bridge(dcf_indep["ev"], inputs, hist_net_debt)
    bridge_indep["effective_tax_rate"] = wacc_indep["effective_tax_rate"]

    pps_pm = _per_share(bridge_pm["after_dloc"], inputs)
    pps_indep = _per_share(bridge_indep["after_dloc"], inputs)

    coco_stats = _coco_stats(inputs)
    ff = _football_field(dcf_pm["ev"], dcf_indep["ev"], coco_stats, proj,
                         inputs, bridge_pm)
    sens = _sensitivity_grid(proj["fcff"], wacc_pm["wacc"], t_growth, inputs)

    cross = _cross_checks(dcf_pm["ev"], ff, coco_stats, inputs)
    flags = _validation_flags(inputs, proj, cross)

    # Concluded range: DCF is the sole primary methodology. Band from the
    # analyst-selected range when set, else DCF EV at WACC ± one sensitivity step.
    low = ff.get("selected_low")
    high = ff.get("selected_high")
    if low is None or high is None:
        grid, br, bc = sens["grid"], sens["base_row"], sens["base_col"]
        lo_cell = grid[br + 1][bc] if br + 1 < len(grid) else None  # higher WACC ⇒ lower EV
        hi_cell = grid[br - 1][bc] if br - 1 >= 0 else None
        low = low if low is not None else lo_cell
        high = high if high is not None else hi_cell
    concluded = {"basis": "dcf_per_management", "ev": dcf_pm["ev"],
                 "low": low, "high": high}

    eng = _g(inputs, "engagement", default={}) or {}
    cu = _g(inputs, "currency", default={}) or {}

    return {
        "engagement": {
            "company_name": eng.get("company_name"),
            "valuation_date": eng.get("valuation_date"),
            "country": eng.get("company_country"),
            "industry": eng.get("company_industry_us"),
            "report_purpose": eng.get("report_purpose"),
            "target_valuation": eng.get("target_valuation"),
            "exchange_platform": eng.get("exchange_platform"),
        },
        "currency": {
            "primary": cu.get("primary"),
            "unit": cu.get("unit"),
        },
        "projections": proj,
        "wacc": {
            "per_management": wacc_pm,
            "independent": wacc_indep,
        },
        "dcf": {
            "per_management": dcf_pm,
            "independent": dcf_indep,
        },
        "bridge": {
            "per_management": bridge_pm,
            "independent": bridge_indep,
        },
        "per_share": {
            "per_management": pps_pm,
            "independent": pps_indep,
        },
        "coco_stats": coco_stats,
        "football_field": ff,
        "sensitivity": sens,
        "concluded": concluded,
        "cross_checks": cross,
        "validation_flags": flags,
        "terminal": {"method": t_method, "growth_rate": t_growth,
                     "nominal_gdp_growth": terminal.get("nominal_gdp_growth")},
    }
