"""Pydantic schema for validating ProduceValuationInputsSkill output.

Goal: catch the failure modes that silently break the xlsx export — missing
top-level sections, wrong array lengths, length mismatches between cocos and
their multiples/margins/ratios, malformed wacc tri-section. NOT a strict
property-by-property contract — the LLM is allowed to emit additional fields
(extra='allow') and most leaves are typed as Optional so a missing data point
becomes a None rather than a hard failure.

Used by produce_valuation_inputs.py to:
  1. Validate the parsed JSON
  2. On failure, retry once with the formatted Pydantic error appended to the
     user prompt — gives the model a chance to self-correct (Karpathy's
     "lint loop" idea, applied at point of generation)
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Permissive base — the LLM may emit extra fields we haven't formalized yet.
class _Permissive(BaseModel):
    model_config = ConfigDict(extra="allow")


# ─── Section A: Engagement metadata ──────────────────────────────────────────

class Engagement(_Permissive):
    company_name: str
    company_country: str | None = None
    company_industry_us: str | None = None
    company_industry_global: str | None = None
    valuation_date: str  # ISO date string; not parsed strictly
    target_valuation: float | None = None  # client's target valuation; same currency × unit as workpaper
    exchange_platform: str | None = None  # exchange comparable-company pool is drawn from (e.g. NASDAQ, NYSE)
    report_purpose: str | None = None
    accounting_standard: str | None = None
    engagement_team_partner: str | None = None
    engagement_team_manager: str | None = None
    engagement_department: str | None = None
    client_name: str | None = None


# ─── Section B: Currency & units ─────────────────────────────────────────────

class Currency(_Permissive):
    primary: str | None = Field(default=None, alias="currency")  # accept either key
    unit: str | None = None
    alt: str | None = Field(default=None, alias="currency_alt")
    fx_rate_alt: float | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ─── Section C: Tax rule ─────────────────────────────────────────────────────

class Tax(_Permissive):
    jurisdiction: str | None = None
    type: str | None = None  # flat | two_tier | progressive
    rate_low: float | None = None
    rate_high: float | None = None
    threshold: float | None = None
    effective_rate_override: float | None = None


# ─── Section D: Projections (Y1-Y5 arrays + Y0 base) ─────────────────────────

class Segment(_Permissive):
    """One business segment of the target's revenue. Eric 2026-05-08 item 2:
    revenue & COGS broken out by segment, with the option to introduce new
    revenue streams mid-projection (start_year > 0)."""
    name: str
    start_year: int | None = 0  # 0 = Y0 (already running); k = first appears at projection year k
    revenue_y0: float | None = None  # initial revenue if start_year == 0
    initial_revenue: float | None = None  # revenue at start_year (required when start_year > 0)
    revenue_growth: list[float | None] | None = None  # growth rates from start_year onward
    gross_margin: list[float | None] | None = None  # per-year GM; either this OR cogs_pct
    cogs_pct: list[float | None] | None = None  # alternative to gross_margin (cogs_pct = 1 − gross_margin)


class Projections(_Permissive):
    years: int | None = None
    revenue_growth_method: str | None = None
    revenue_y0: float
    nwc_y0: float
    # Eric 2026-05-18 — audited Y0 absolutes so the Projections sheet's Y0
    # column shows real numbers instead of blanks. Optional because legacy
    # inputs JSONs may not include them; producer prompts the LLM to fill
    # them from historical_fs. opex_y0 is stored NEGATIVE for sign consistency
    # with the rest of the cascade.
    gross_profit_y0: float | None = None
    opex_y0: float | None = None  # negative
    ebitda_y0: float | None = None
    ebit_y0: float | None = None
    # Eric 2026-05-19 #1 — tax + net income Y0 absolutes (negative for tax)
    tax_y0: float | None = None  # negative
    net_income_y0: float | None = None
    revenue_growth: list[float | None]
    # Eric 2026-05-19 — primary/additional split. revenue_growth_primary is the
    # conservative track (~historical CAGR ±2pp) that doesn't require BDP
    # justification; the residual to hit revenue_growth (the TOTAL growth that
    # calibration tunes to target_valuation) shows up as the "Additional"
    # revenue line on Projections and must be explained by the BDP narrative.
    revenue_growth_primary: list[float | None] | None = None
    gross_margin: list[float | None]
    opex_pct_revenue: list[float | None]
    capex_pct_revenue: list[float | None]
    dep_pct_revenue: list[float | None]
    nwc_pct_sales: list[float | None]
    segments: list[Segment] | None = None  # if non-empty, segment series aggregate into total revenue & gross_profit; top-level revenue_growth + gross_margin are ignored

    @model_validator(mode="after")
    def _check_array_lengths(self) -> "Projections":
        n = self.years or 5
        for name in (
            "revenue_growth", "gross_margin", "opex_pct_revenue",
            "capex_pct_revenue", "dep_pct_revenue", "nwc_pct_sales",
        ):
            arr = getattr(self, name)
            if len(arr) != n:
                raise ValueError(
                    f"projections.{name} has length {len(arr)}, expected {n} "
                    f"(matches projections.years={n}). Pad with null where data is unknown."
                )
        return self


# ─── Section: Historical FS (5-year arrays, padded with null) ───────────────

_HISTORICAL_FS_REQUIRED_KEYS = (
    "revenue", "cogs", "gross_profit", "opex_total", "ebitda", "da", "ebit",
    "interest_expense", "profit_before_tax", "tax_expense", "net_income",
    "cash", "accounts_receivable", "inventory", "total_current_assets",
    "ppe", "total_assets", "accounts_payable", "short_term_debt",
    "total_current_liabilities", "long_term_debt", "total_liabilities",
    "total_equity",
)


class HistoricalFS(_Permissive):
    @model_validator(mode="after")
    def _check_keys_and_lengths(self) -> "HistoricalFS":
        # All known fields are stored as model_extra under _Permissive; check there
        data = self.model_dump()
        missing = [k for k in _HISTORICAL_FS_REQUIRED_KEYS if k not in data]
        if missing:
            raise ValueError(
                f"historical_fs missing required series: {missing}. "
                f"Provide a length-5 array for each (oldest first); pad with null."
            )
        bad_len = []
        for k in _HISTORICAL_FS_REQUIRED_KEYS:
            v = data.get(k)
            if not isinstance(v, list):
                bad_len.append(f"{k} (not a list)")
            elif len(v) != 5:
                bad_len.append(f"{k} (len={len(v)}, expected 5)")
        if bad_len:
            raise ValueError(
                f"historical_fs series must be length-5 arrays (FY-5..FY-1, "
                f"oldest first; pad missing years with null). Issues: {bad_len[:5]}"
            )
        return self


# ─── Section E: Terminal value ───────────────────────────────────────────────

class Terminal(_Permissive):
    method: str  # gordon_growth | exit_multiple
    growth_rate: float | None = None
    exit_multiple_type: str | None = None
    exit_multiple_value: float | None = None


# ─── Section F: WACC tri-scenario ────────────────────────────────────────────

class WaccShared(_Permissive):
    risk_free_rate: float
    risk_free_rate_source: str | None = None
    equity_risk_premium: float
    country_risk_premium: float | None = None


class WaccScenario(_Permissive):
    unlevered_beta: float
    target_debt_to_equity: float
    size_premium: float | None = None
    specific_risk_premium: float | None = None
    pretax_cost_of_debt: float
    target_debt_weight: float
    target_equity_weight: float


class Wacc(_Permissive):
    shared: WaccShared
    per_management: WaccScenario
    independent: WaccScenario


# ─── Section G: Cocos + multiples + margins + ratios (length-aligned arrays) ─

class CoCo(_Permissive):
    tier: str | int | None = None
    include: bool | None = None
    company: str
    ticker: str | None = None
    exchange: str | None = None  # e.g. "NASDAQ", "NYSE"; used to filter against engagement.exchange_platform
    business_description: str | None = None  # short one-liner shown on the Comps sheet
    selected_for_wacc: bool | None = None  # one of the 5–6 comps chosen for WACC calc out of the ~20 screened pool


class CoCoMultiples(_Permissive):
    pass  # any of {ev_sales_ltm, ev_sales_ntm, ev_ebitda_ltm, ev_ebitda_ntm, pe_ltm, pe_ntm}


class CoCoMargins(_Permissive):
    pass


class CoCoRatios(_Permissive):
    pass


# ─── Bridge & football field ─────────────────────────────────────────────────

class Bridge(_Permissive):
    shares_outstanding: float
    dlom_pct: float | None = None
    dloc_pct: float | None = None
    equity_interest_pct: float | None = None


class FootballField(_Permissive):
    weight_dcf: float
    weight_comps: float
    weight_precedent: float
    weight_nav: float

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "FootballField":
        s = self.weight_dcf + self.weight_comps + self.weight_precedent + self.weight_nav
        if abs(s - 1.0) > 0.001:
            raise ValueError(
                f"football_field weights sum to {s:.4f}, must sum to 1.0 "
                f"(currently dcf={self.weight_dcf}, comps={self.weight_comps}, "
                f"precedent={self.weight_precedent}, nav={self.weight_nav})"
            )
        return self


# ─── Top-level ───────────────────────────────────────────────────────────────

class ValuationInputs(_Permissive):
    engagement: Engagement
    currency: Currency
    tax: Tax
    projections: Projections
    historical_fs: HistoricalFS
    terminal: Terminal
    wacc: Wacc
    cocos: list[CoCo]
    coco_multiples: list[dict[str, Any]]
    coco_margins: list[dict[str, Any]]
    coco_ratios: list[dict[str, Any]]
    bridge: Bridge
    football_field: FootballField
    sources: dict[str, Any]

    @model_validator(mode="after")
    def _coco_arrays_aligned(self) -> "ValuationInputs":
        n = len(self.cocos)
        for name in ("coco_multiples", "coco_margins", "coco_ratios"):
            arr = getattr(self, name)
            if len(arr) != n:
                raise ValueError(
                    f"{name} has length {len(arr)} but cocos has length {n}. "
                    f"Each coco entry must have a corresponding {name} entry at the same index."
                )
        return self

    @model_validator(mode="after")
    def _sources_cover_critical(self) -> "ValuationInputs":
        # Every scalar listed in the prompt's MANDATORY-SOURCES rule must have
        # a sources.<id> entry.
        required = {
            "company_name", "valuation_date", "tax_rate_high", "revenue_y0",
            "nwc_y0", "risk_free_rate", "equity_risk_premium",
            "country_risk_premium", "unlevered_beta_per_mgmt", "dlom_pct",
            "dloc_pct", "shares_outstanding", "terminal_growth_rate",
        }
        missing = sorted(required - set(self.sources.keys()))
        if missing:
            raise ValueError(
                f"sources.<id> missing for required parameters: {missing}. "
                f"Every scalar above MUST have a sources entry of shape "
                f"{{source, detail, notes}}."
            )
        return self


def validate(payload: dict) -> tuple[ValuationInputs | None, str | None]:
    """Returns (model, None) on success or (None, formatted_error) on failure.
    Formatted error is suitable for inclusion in a retry prompt."""
    try:
        return ValuationInputs.model_validate(payload), None
    except Exception as e:
        # Format pydantic errors into a compact, model-readable list
        return None, _format_error(e)


def _format_error(exc: Exception) -> str:
    from pydantic import ValidationError
    if not isinstance(exc, ValidationError):
        return str(exc)
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        msg = err["msg"]
        lines.append(f"- {loc}: {msg}")
    return "\n".join(lines)
