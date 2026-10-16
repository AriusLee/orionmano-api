"""Shared helpers for working on a valuation version's inputs: read and patch a
parameter, recompute headline values, describe the model to an LLM, call Claude."""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

import anthropic

from app.config import settings
from app.services.agent.skills.produce_valuation_inputs import (
    PINNABLE_PARAMS,
    _apply_pinned_overrides,
    _parse_json_response,
)
from app.services.valuation_model.versions import headline

logger = logging.getLogger(__name__)

# Same model the valuation producer uses, so answers reason at the same level
# as the model they explain.
CLAUDE_MODEL = "claude-opus-4-7"

PARAM_LABELS: dict[str, str] = {
    "revenue_y0": "Base-year revenue",
    "gross_profit_y0": "Base-year gross profit",
    "opex_y0": "Base-year operating expenses",
    "ebitda_y0": "Base-year EBITDA",
    "ebit_y0": "Base-year EBIT",
    "tax_y0": "Base-year tax",
    "net_income_y0": "Base-year net income",
    **{f"revenue_growth_y{i}": f"Revenue growth Y{i} (total)" for i in range(1, 6)},
    **{f"revenue_growth_primary_y{i}": f"Revenue growth Y{i} (primary / conservative)" for i in range(1, 6)},
    **{f"gross_margin_y{i}": f"Gross margin Y{i}" for i in range(1, 6)},
    "terminal_growth_rate": "Terminal growth rate",
    "nominal_gdp_growth": "Long-run nominal GDP growth",
    "risk_free_rate": "Risk-free rate",
    "equity_risk_premium": "Equity risk premium",
    "country_risk_premium": "Country risk premium",
    "unlevered_beta_pm": "Unlevered beta",
    "size_premium_pm": "Size premium",
    "specific_risk_premium_pm": "Company-specific risk premium",
    "pretax_cost_of_debt_pm": "Pre-tax cost of debt",
    "effective_tax_rate": "Effective tax rate",
    "dlom_pct": "Discount for lack of marketability (DLOM)",
    "dloc_pct": "Discount for lack of control (DLOC)",
    "shares_outstanding": "Shares outstanding (basic)",
    "shares_outstanding_diluted": "Shares outstanding (diluted)",
    "net_debt_override": "Net debt",
}


def get_path(inputs: dict, path: str) -> Any:
    node: Any = inputs
    for part in path.split("."):
        if part.isdigit():
            if not isinstance(node, list) or int(part) >= len(node):
                return None
            node = node[int(part)]
        else:
            if not isinstance(node, dict):
                return None
            node = node.get(part)
    return node


def param_value(inputs: dict, key: str) -> float | None:
    spec = PINNABLE_PARAMS.get(key)
    if not spec:
        return None
    v = get_path(inputs, spec[0])
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def format_param(key: str, value: float | None, currency: str | None = None, unit: str | None = None) -> str:
    if value is None:
        return "—"
    spec = PINNABLE_PARAMS.get(key)
    kind = spec[1] if spec else "number"
    if kind == "percent":
        return f"{value * 100:.2f}%"
    if kind == "currency":
        return f"{currency or ''} {value:,.0f}{(' ' + unit) if unit else ''}".strip()
    return f"{value:,.4g}"


def patched(inputs: dict, changes: dict[str, float]) -> dict:
    """A deep copy of inputs with each PINNABLE_PARAMS key set to its value."""
    out = copy.deepcopy(inputs)
    _apply_pinned_overrides(out, changes)
    return out


def compute_values(inputs: dict) -> dict[str, float | None]:
    """EV, equity (after DLOM/DLOC) and the concluded EV range from the
    deterministic model — cheap, so every proposed change can show its impact
    before anything is applied."""
    try:
        from compute import compute_summary  # type: ignore  (backend/valuation on sys.path)
        summary = compute_summary(inputs)
    except Exception as e:
        logger.warning("compute_summary failed: %s: %s", type(e).__name__, e)
        return {"ev": None, "equity": None, "low": None, "high": None, "dcf_low": None, "dcf_high": None}
    ev, equity = headline(summary)
    concluded = summary.get("concluded") or {}
    dcf_ff = (summary.get("football_field") or {}).get("dcf") or {}

    def num(v: Any) -> float | None:
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    # The concluded range keeps the analyst-selected band while it still
    # brackets the EV, so it often does not move; the DCF range (per
    # management vs independent) always does, so both are reported.
    return {"ev": ev, "equity": equity, "low": num(concluded.get("low")), "high": num(concluded.get("high")),
            "dcf_low": num(dcf_ff.get("low")), "dcf_high": num(dcf_ff.get("high"))}


def compute_headline(inputs: dict) -> tuple[float | None, float | None]:
    v = compute_values(inputs)
    return v["ev"], v["equity"]


def impact_between(inputs: dict, new_inputs: dict) -> dict[str, Any]:
    """Effect on EV, equity and the valuation range of replacing `inputs` with `new_inputs`."""
    a, b = compute_values(inputs), compute_values(new_inputs)
    cu = inputs.get("currency") or {}

    def pct(x: float | None, y: float | None) -> float | None:
        return (y - x) / x if x not in (None, 0) and y is not None else None

    return {
        "ev_before": a["ev"],
        "ev_after": b["ev"],
        "equity_before": a["equity"],
        "equity_after": b["equity"],
        "ev_change_pct": pct(a["ev"], b["ev"]),
        "equity_change_pct": pct(a["equity"], b["equity"]),
        "range_before": [a["low"], a["high"]],
        "range_after": [b["low"], b["high"]],
        "dcf_range_before": [a["dcf_low"], a["dcf_high"]],
        "dcf_range_after": [b["dcf_low"], b["dcf_high"]],
        "currency": cu.get("primary"),
        "unit": cu.get("unit"),
    }


def impact(inputs: dict, changes: dict[str, float]) -> dict[str, Any]:
    return impact_between(inputs, patched(inputs, changes))


def describe_model(inputs: dict, summary: dict | None) -> str:
    """Compact, LLM-readable description of a valuation version: headline
    results, the changeable parameters with current values, and the stated
    basis for each assumption."""
    cu = inputs.get("currency") or {}
    currency, unit = cu.get("primary"), cu.get("unit")
    ev, equity = headline(summary)
    eng = inputs.get("engagement") or {}
    lines = [
        f"Company: {eng.get('company_name')} · valuation date {eng.get('valuation_date')} · "
        f"currency {currency} {unit or ''} · exchange {eng.get('exchange_platform')}",
    ]
    if ev is not None:
        lines.append(f"Concluded DCF enterprise value: {currency} {ev:,.0f} {unit or ''}")
    if equity is not None:
        lines.append(f"Equity value after DLOM/DLOC: {currency} {equity:,.0f} {unit or ''}")
    wacc = ((summary or {}).get("wacc") or {}).get("per_management") or {}
    if isinstance(wacc.get("wacc"), (int, float)):
        lines.append(f"WACC: {wacc['wacc'] * 100:.2f}%")
    lines.append("\nParameters that may be changed (key = current value):")
    for key in PINNABLE_PARAMS:
        v = param_value(inputs, key)
        if v is None:
            continue
        lines.append(f"- {key} ({PARAM_LABELS.get(key, key)}) = {format_param(key, v, currency, unit)} [raw {v:.6g}]")
    proj = inputs.get("projections") or {}
    for arr in ("revenue_growth", "gross_margin", "opex_pct_revenue", "capex_pct_revenue", "nwc_pct_sales"):
        if isinstance(proj.get(arr), list):
            vals = ", ".join("—" if x is None else f"{x * 100:.1f}%" for x in proj[arr])
            lines.append(f"projections.{arr} (Y1–Y5): {vals}")
    hist = inputs.get("historical_fs") or {}
    if isinstance(hist.get("revenue"), list):
        lines.append("historical revenue (FY-5..FY-1): " + ", ".join("—" if x is None else f"{x:,.0f}" for x in hist["revenue"]))
    sources = inputs.get("sources") or {}
    if sources:
        lines.append("\nStated basis for assumptions (sources):")
        for k, v in list(sources.items())[:40]:
            if isinstance(v, dict):
                text = " · ".join(str(v.get(x)) for x in ("source", "detail", "notes") if v.get(x))
            else:
                text = str(v)
            lines.append(f"- {k}: {text[:400]}")
    return "\n".join(lines)


async def ask_claude_json(system: str, user: str, *, max_tokens: int = 4000, tools: list | None = None) -> tuple[dict | None, Any]:
    """One Claude call that must answer with a JSON object. Returns (parsed,
    raw response). With `tools` (e.g. web search) the JSON is read from the
    final text block."""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    kwargs: dict[str, Any] = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if tools:
        kwargs["tools"] = tools
    async with client.messages.stream(**kwargs) as stream:
        response = await stream.get_final_message()
    texts = [b.text for b in response.content if getattr(b, "type", None) == "text" and getattr(b, "text", None)]
    parsed = None
    # The JSON answer is normally the last text block (after any search turns).
    for t in reversed(texts):
        parsed = _parse_json_response(t)
        if parsed is not None:
            break
    if parsed is None and texts:
        parsed = _parse_json_response("\n".join(texts))
    return parsed, response


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)
