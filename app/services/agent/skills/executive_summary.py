"""Skill wrapper for executive summary generation."""

from __future__ import annotations

from typing import Any

from app.services.agent.skill import Skill, SkillResult, SkillParameter
from app.services.agent.context import AgentContext


class ExecutiveSummarySkill(Skill):
    name = "executive_summary"
    description = (
        "Generate a concise AI executive summary of the current company "
        "based on all uploaded and extracted document data."
    )
    parameters = []

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        from app.services.company_intelligence import generate_executive_summary

        if not ctx.company_id:
            return SkillResult.failed("No company selected")

        try:
            summary = await generate_executive_summary(ctx.db, ctx.company_id)
            if not summary:
                return SkillResult.failed("No document data available to generate summary.")

            return SkillResult.success(
                data={"summary": summary},
                message=summary,
                artifacts={"executive_summary": summary},
            )
        except Exception as e:
            return SkillResult.failed(f"Summary generation failed: {str(e)}")
