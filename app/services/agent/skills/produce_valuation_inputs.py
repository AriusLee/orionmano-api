"""Skill: produce a JSON object conforming to the valuation Inputs schema.

Reads company data + extracted document content from the AgentContext, calls
Claude with the schema spec as a cached system prompt, and parses the JSON
response. Output flows into GenerateValuationWorkpaperSkill which writes the
populated xlsx via export_workpaper.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import anthropic

from app.config import settings
from app.services.agent.context import AgentContext
from app.services.agent.skill import Skill, SkillResult


REPO_ROOT = Path(__file__).resolve().parents[5]
SCHEMA_PATH = REPO_ROOT / "knowledge-base" / "04-valuation" / "inputs-sheet-schema.md"


SYSTEM_INSTRUCTION = (
    "You are a valuation analyst at a US/Nasdaq IPO advisory firm. Your task "
    "is to produce a single JSON object conforming to the inputs-sheet schema. "
    "The output is consumed by an automated Excel export pipeline — any deviation "
    "from valid JSON breaks the build. Output JSON only, no prose, no markdown, "
    "no code fences. Default jurisdiction perspective: US/SEC (Nasdaq IPO targets); "
    "do NOT default to HKEX or HK regulatory framing."
)


def _build_user_prompt(context: str) -> str:
    return f"""# Company context (from extracted documents and database)

{context if context else '(No extracted documents available — use sensible defaults consistent with US/Nasdaq IPO advisory practice for a generic Asia-Pacific tech target.)'}

# Task

Produce a JSON object that conforms to the schema document above. Use the company context to fill as many fields as possible. For fields you cannot determine from the context, use sensible defaults consistent with US/Nasdaq IPO advisory practice.

# Required completeness

Every section listed below MUST be present in the output:

- `engagement` — all 11 fields (company_name, company_country, company_industry_us, company_industry_global, valuation_date, report_purpose, accounting_standard, engagement_team{{partner,manager,department}}, client_name)
- `currency` — primary, unit, alt, fx_rate_alt
- `tax` — jurisdiction, type ("flat"/"two_tier"/"progressive"), rate_low, rate_high, threshold, effective_rate_override
- `projections` — years (typically 5), revenue_growth_method, and Y1-Y5 arrays for revenue_growth, gross_margin, opex_pct_revenue, capex_pct_revenue, dep_pct_revenue, nwc_pct_sales (all 6 arrays, each length-5)
- `terminal` — method ("gordon_growth"), growth_rate, exit_multiple_type, exit_multiple_value
- `wacc.shared` — risk_free_rate, risk_free_rate_source, equity_risk_premium, country_risk_premium
- `wacc.per_management` — unlevered_beta, target_debt_to_equity, size_premium, specific_risk_premium, pretax_cost_of_debt, target_debt_weight, target_equity_weight
- `wacc.independent` — same fields, slightly more conservative (higher beta, higher specific risk)
- `cocos` — array of 0-30 comparable companies with (tier, include, company, ticker, country, accounting, market_cap_usd_mm, d_to_e, raw_beta, tax_rate)
- `precedents` — array of 0-15 transactions with (include, date, acquirer, target, ev_usd_mm, ev_revenue, ev_ebitda, premium, rationale)
- `bridge` — surplus_assets, net_debt_override (null OK), minority_interests, non_operating_assets, dlom_pct, dloc_pct, equity_interest_pct, shares_outstanding, shares_outstanding_diluted (null OK), pre_money_pct (null OK)
- `adjustments` — capitalize_rd, rd_amortization_years, convert_operating_leases, lease_discount_rate (null OK)
- `football_field` — weight_dcf, weight_comps, weight_precedent, weight_nav (sum must equal 1.0; weight_nav typically 0)
- `sensitivity` — wacc_step (0.005), wacc_count (5), terminal_g_step (0.005), terminal_g_count (5), revenue_g_step (0.02), ebitda_margin_step (0.02)
- `sources` — object with one entry per major parameter id, each {{source, detail, notes}}; populate at least company_name, valuation_date, tax_rate_high, risk_free_rate, equity_risk_premium, country_risk_premium, dlom_pct, dloc_pct

# Output

JSON object only. No prose, no markdown fences, no leading or trailing text."""


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

        # Load company + extracted docs
        await ctx.load_company_data()
        company_context = ctx.get_company_context_str()

        schema_doc = SCHEMA_PATH.read_text()

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # System prompt: instruction + schema doc (cached — large + stable)
        system_prompt = [
            {"type": "text", "text": SYSTEM_INSTRUCTION},
            {
                "type": "text",
                "text": f"# Inputs Schema (canonical)\n\n{schema_doc}",
                "cache_control": {"type": "ephemeral"},
            },
        ]

        try:
            response = await client.messages.create(
                model="claude-opus-4-7",
                max_tokens=16000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": _build_user_prompt(company_context)}
                ],
            )
        except anthropic.APIError as e:
            return SkillResult.failed(f"Anthropic API error: {e}")

        # Extract text
        text_blocks = [b.text for b in response.content if b.type == "text"]
        if not text_blocks:
            return SkillResult.failed("Model returned no text content")
        text = text_blocks[0]

        payload = _parse_json_response(text)
        if payload is None:
            return SkillResult.failed(
                f"Could not parse JSON from model response. First 500 chars: {text[:500]}"
            )

        # Capture cache + token usage for visibility
        usage = getattr(response, "usage", None)
        usage_summary = {}
        if usage is not None:
            usage_summary = {
                "input_tokens": getattr(usage, "input_tokens", 0),
                "output_tokens": getattr(usage, "output_tokens", 0),
                "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
                "cache_creation_input_tokens": getattr(
                    usage, "cache_creation_input_tokens", 0
                ),
            }

        return SkillResult.success(
            data=payload,
            message=(
                f"Produced valuation inputs JSON ({len(json.dumps(payload))} bytes; "
                f"cache_read={usage_summary.get('cache_read_input_tokens', 0)} tokens)"
            ),
            artifacts={
                "valuation_inputs": payload,
                "usage": usage_summary,
            },
            token_usage=(
                usage_summary.get("input_tokens", 0)
                + usage_summary.get("output_tokens", 0)
            ),
        )
