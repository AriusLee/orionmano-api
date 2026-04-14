"""Skill wrapper for financial analysis and risk detection."""

from __future__ import annotations

from typing import Any

from app.services.agent.skill import Skill, SkillResult, SkillParameter
from app.services.agent.context import AgentContext


class AnalyzeFinancialsSkill(Skill):
    name = "analyze_financials"
    description = (
        "Analyze the current company's financial data from uploaded documents. "
        "Detects risk flags (leverage, liquidity, profitability, cash flow) and returns structured findings."
    )
    parameters = []

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        from app.services.company_intelligence import detect_risk_flags

        if not ctx.company_id:
            return SkillResult.failed("No company selected")

        if not ctx.documents:
            await ctx.load_company_data()

        # Merge all extracted data
        merged_data: dict = {}
        for doc in ctx.documents:
            ext = doc.get("extracted_data", {})
            if isinstance(ext, dict):
                for key, val in ext.items():
                    if key not in merged_data or not merged_data[key]:
                        merged_data[key] = val

        if not merged_data:
            return SkillResult.failed("No extracted financial data available. Upload and process documents first.")

        flags = detect_risk_flags(merged_data)

        high = [f for f in flags if f["severity"] == "high"]
        medium = [f for f in flags if f["severity"] == "medium"]

        summary_parts = [f"Found {len(flags)} risk flag(s): {len(high)} high, {len(medium)} medium."]
        for f in flags:
            severity_icon = "HIGH" if f["severity"] == "high" else "MEDIUM"
            summary_parts.append(f"- [{severity_icon}] {f['title']}: {f['detail']}")

        return SkillResult.success(
            data={"flags": flags, "high_count": len(high), "medium_count": len(medium)},
            message="\n".join(summary_parts),
            artifacts={"risk_flags": flags},
        )
