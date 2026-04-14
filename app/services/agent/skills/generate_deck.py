"""Individual skill wrappers for each deck type."""

from __future__ import annotations

from typing import Any

from app.services.agent.skill import Skill, SkillResult, SkillParameter
from app.services.agent.context import AgentContext


async def _run_deck(ctx: AgentContext, deck_type: str) -> SkillResult:
    from app.services.deck.generator import generate_deck_pdf

    if not ctx.company_id:
        return SkillResult.failed("No company selected")

    try:
        pdf_bytes = await generate_deck_pdf(ctx.db, ctx.company_id, deck_type)
        return SkillResult.success(
            data={"deck_type": deck_type, "size_bytes": len(pdf_bytes)},
            message=f"Deck '{deck_type}' generated successfully ({len(pdf_bytes):,} bytes).",
            artifacts={"deck_pdf": pdf_bytes, "deck_type": deck_type},
        )
    except Exception as e:
        return SkillResult.failed(f"Deck generation failed: {str(e)}")


class GenerateSalesDeckSkill(Skill):
    name = "generate_sales_deck"
    description = (
        "Generate a Sales Deck — an engagement proposal presentation covering "
        "Orionmano's services, the client's business, proposed scope, approach, and next steps."
    )
    parameters = []

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_deck(ctx, "sales_deck")


class GenerateKickoffDeckSkill(Skill):
    name = "generate_kickoff_deck"
    description = (
        "Generate a Kick-off Meeting Deck — a project kick-off presentation covering "
        "engagement overview, scope of services, timeline phases, and immediate next steps."
    )
    parameters = []

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_deck(ctx, "kickoff_deck")


class GenerateTeaserDeckSkill(Skill):
    name = "generate_teaser_deck"
    description = (
        "Generate a Teaser Deck — a visual investor teaser PDF with company overview, "
        "investment highlights, and transaction details. Branded Orionmano template."
    )
    parameters = []

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_deck(ctx, "teaser")


class GenerateCompanyDeckSkill(Skill):
    name = "generate_company_deck"
    description = (
        "Generate a Company Deck — a full investor presentation PDF covering investment thesis, "
        "business model, market position, and growth strategy. Branded Orionmano template."
    )
    parameters = []

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        return await _run_deck(ctx, "company_deck")
