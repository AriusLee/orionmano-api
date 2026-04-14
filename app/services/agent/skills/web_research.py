"""Skill wrapper for web research via Tavily."""

from __future__ import annotations

from typing import Any

from app.services.agent.skill import Skill, SkillResult, SkillParameter
from app.services.agent.context import AgentContext


class WebResearchSkill(Skill):
    name = "web_research"
    description = (
        "Search the web for market data, industry trends, competitor info, regulations, "
        "or any other research topic. Returns summarized search results."
    )
    parameters = [
        SkillParameter(
            name="query",
            type="string",
            description="The search query",
        ),
        SkillParameter(
            name="max_results",
            type="integer",
            description="Maximum number of results to return",
            required=False,
            default=5,
        ),
    ]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        from app.services.ai.web_search import web_search, format_search_results

        query = kwargs["query"]
        max_results = kwargs.get("max_results", 5)

        try:
            results = await web_search(query, max_results=max_results)
            formatted = format_search_results(results)
            return SkillResult.success(
                data={"results": results, "count": len(results)},
                message=formatted or "No results found.",
                artifacts={"search_results": results},
            )
        except Exception as e:
            return SkillResult.failed(f"Web search failed: {str(e)}")
