"""Individual skill wrappers for each report type."""

from __future__ import annotations

from typing import Any

from app.services.agent.skill import Skill, SkillResult, SkillParameter
from app.services.agent.context import AgentContext


TIER_PARAM = SkillParameter(
    name="tier",
    type="string",
    description="Report depth tier",
    required=False,
    default="standard",
    enum=["essential", "standard", "premium"],
)


async def _run_report(ctx: AgentContext, report_type: str, tier: str) -> SkillResult:
    from app.models.report import Report
    from app.services.report.generator import generate_report_bg

    if not ctx.company_id:
        return SkillResult.failed("No company selected")

    report = Report(
        company_id=ctx.company_id,
        report_type=report_type,
        tier=tier,
        status="pending",
    )
    ctx.db.add(report)
    await ctx.db.commit()
    await ctx.db.refresh(report)

    await generate_report_bg(ctx.db, ctx.company_id, report_type, report.id)

    await ctx.db.refresh(report)
    if report.status == "failed":
        return SkillResult.failed(
            f"Report generation failed: {report.error_message}",
            data={"report_id": str(report.id)},
        )

    return SkillResult.success(
        data={"report_id": str(report.id), "title": report.title, "status": report.status},
        message=f"Report '{report.title}' generated successfully ({tier} tier).",
        artifacts={"report_id": str(report.id)},
    )


class GenerateGapAnalysisSkill(Skill):
    name = "generate_gap_analysis"
    description = (
        "Generate a Gap Analysis report assessing the company's readiness for Nasdaq listing. "
        "Covers financial standards, governance gaps, reporting gaps, and regulatory compliance."
    )
    parameters = [TIER_PARAM]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_report(ctx, "gap_analysis", kwargs.get("tier", "standard"))


class GenerateIndustryReportSkill(Skill):
    name = "generate_industry_report"
    description = (
        "Generate an Industry Expert Report with market research, competitive landscape, "
        "market sizing (TAM/SAM/SOM), growth drivers, and strategic positioning analysis."
    )
    parameters = [TIER_PARAM]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_report(ctx, "industry_report", kwargs.get("tier", "standard"))


class GenerateDDReportSkill(Skill):
    name = "generate_dd_report"
    description = (
        "Generate a Due Diligence Report covering financial analysis (balance sheet, "
        "income statement, cash flow), internal controls evaluation, and key findings."
    )
    parameters = [TIER_PARAM]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_report(ctx, "dd_report", kwargs.get("tier", "standard"))


class GenerateValuationReportSkill(Skill):
    name = "generate_valuation_report"
    description = (
        "Generate a Valuation Report with DCF analysis, WACC derivation, comparable company "
        "benchmarking, implied multiples, sensitivity analysis, and EV-to-equity bridge."
    )
    parameters = [TIER_PARAM]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_report(ctx, "valuation_report", kwargs.get("tier", "standard"))


class GenerateTeaserSkill(Skill):
    name = "generate_teaser"
    description = (
        "Generate a Company Teaser — a concise investor-facing document highlighting "
        "company snapshot, investment highlights, key financials, and transaction overview."
    )
    parameters = [TIER_PARAM]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_report(ctx, "teaser", kwargs.get("tier", "standard"))
