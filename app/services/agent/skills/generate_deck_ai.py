"""AI-driven deck skills — replace the four type-specific deck skills with a
single prompt-driven `GenerateDeckSkill` plus `AmendDeckSkill` and
`SwapDeckThemeSkill`.

The old `generate_deck.py` skills (sales/kickoff/teaser/company) still exist
and still wrap the template-based generator. Both are registered side-by-side
during the transition; once the frontend ships, the old ones get retired.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.services.agent.skill import Skill, SkillParameter, SkillResult
from app.services.agent.context import AgentContext


class GenerateDeckSkill(Skill):
    name = "generate_deck"
    description = (
        "Generate a slide deck from a user prompt under a chosen theme. The AI "
        "picks slide layouts and content from the company's data. Optionally "
        "seed with a preset (sales_deck, kickoff_deck, teaser, company_deck) "
        "that prefills a known-good prompt. Returns the persisted deck id."
    )
    parameters = [
        SkillParameter(
            name="theme_id",
            type="string",
            description="Theme id (e.g. 'orionmano_navy'). See GET /api/v1/decks/themes.",
            required=False,
            default="orionmano_navy",
        ),
        SkillParameter(
            name="prompt",
            type="string",
            description="What the deck should be about. Optional if a preset is given.",
            required=False,
        ),
        SkillParameter(
            name="preset",
            type="string",
            description="Optional preset that seeds the prompt.",
            required=False,
            enum=["sales_deck", "kickoff_deck", "teaser", "company_deck"],
        ),
    ]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        from app.models.deck import Deck, DeckVersion
        from app.services.deck.ai_generator import generate_deck_spec, PRESETS

        if not ctx.company_id:
            return SkillResult.failed("No company selected")

        theme_id = kwargs.get("theme_id") or "orionmano_navy"
        prompt = (kwargs.get("prompt") or "").strip()
        preset = kwargs.get("preset")

        if not prompt and not preset:
            return SkillResult.failed("Provide a `prompt` or pick a `preset`.")
        if not prompt and preset:
            prompt = PRESETS.get(preset, "")

        try:
            spec = await generate_deck_spec(
                ctx.db,
                company_id=ctx.company_id,
                theme_id=theme_id,
                prompt=prompt,
                preset=preset,
            )
        except Exception as e:
            return SkillResult.failed(f"Deck generation failed: {e}")

        deck = Deck(
            company_id=ctx.company_id,
            title=spec.title,
            theme_id=theme_id,
            preset=preset,
            prompt=prompt,
            spec=spec.model_dump(),
            current_version=1,
            status="ready",
            created_by=ctx.user_id,
        )
        ctx.db.add(deck)
        await ctx.db.flush()  # populate deck.id

        ctx.db.add(DeckVersion(
            deck_id=deck.id,
            version_no=1,
            spec=spec.model_dump(),
            theme_id=theme_id,
            source="generate",
            prompt=prompt,
            created_by=ctx.user_id,
        ))
        await ctx.db.commit()

        return SkillResult.success(
            data={
                "deck_id": str(deck.id),
                "title": spec.title,
                "slide_count": len(spec.slides),
                "theme_id": theme_id,
                "version": 1,
            },
            message=f"Generated deck '{spec.title}' — {len(spec.slides)} slides.",
            artifacts={"deck_id": str(deck.id), "spec": spec.model_dump()},
        )


class AmendDeckSkill(Skill):
    name = "amend_deck"
    description = (
        "Apply a user instruction to an existing deck — add/remove/edit/reorder "
        "slides, rewrite content, or change tone. The AI returns a new spec; "
        "the old version is preserved for rollback."
    )
    parameters = [
        SkillParameter(
            name="deck_id",
            type="string",
            description="UUID of the deck to amend.",
            required=True,
        ),
        SkillParameter(
            name="prompt",
            type="string",
            description="What to change. e.g. 'make slide 3 punchier', 'add a competitor slide'.",
            required=True,
        ),
    ]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        from app.models.deck import Deck, DeckVersion
        from app.services.deck.ai_generator import amend_deck_spec
        from app.services.deck.schema import SlideSpec

        deck_id_raw = kwargs.get("deck_id")
        prompt = (kwargs.get("prompt") or "").strip()
        if not deck_id_raw or not prompt:
            return SkillResult.failed("Both `deck_id` and `prompt` are required.")

        try:
            deck_id = UUID(str(deck_id_raw))
        except ValueError:
            return SkillResult.failed(f"Invalid deck_id: {deck_id_raw}")

        result = await ctx.db.execute(select(Deck).where(Deck.id == deck_id))
        deck = result.scalar_one_or_none()
        if not deck:
            return SkillResult.failed(f"Deck not found: {deck_id}")
        if ctx.company_id and deck.company_id != ctx.company_id:
            return SkillResult.failed("Deck belongs to a different company.")

        current_spec = SlideSpec.model_validate(deck.spec)

        try:
            new_spec = await amend_deck_spec(
                ctx.db,
                company_id=deck.company_id,
                current_spec=current_spec,
                prompt=prompt,
            )
        except Exception as e:
            return SkillResult.failed(f"Amend failed: {e}")

        new_version = deck.current_version + 1
        deck.spec = new_spec.model_dump()
        deck.title = new_spec.title
        deck.current_version = new_version

        ctx.db.add(DeckVersion(
            deck_id=deck.id,
            version_no=new_version,
            spec=new_spec.model_dump(),
            theme_id=deck.theme_id,
            source="amend",
            prompt=prompt,
            created_by=ctx.user_id,
        ))
        await ctx.db.commit()

        return SkillResult.success(
            data={
                "deck_id": str(deck.id),
                "title": new_spec.title,
                "slide_count": len(new_spec.slides),
                "version": new_version,
            },
            message=f"Amended deck to v{new_version} — {len(new_spec.slides)} slides.",
            artifacts={"deck_id": str(deck.id), "spec": new_spec.model_dump()},
        )


class SwapDeckThemeSkill(Skill):
    name = "swap_deck_theme"
    description = (
        "Re-render an existing deck under a different theme. Content unchanged; "
        "only colors/typography/layout treatment differ. A new version is saved."
    )
    parameters = [
        SkillParameter(name="deck_id", type="string", description="UUID of the deck.", required=True),
        SkillParameter(name="theme_id", type="string", description="Target theme id.", required=True),
    ]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        from app.models.deck import Deck, DeckVersion
        from app.services.deck.themes import get_theme

        deck_id_raw = kwargs.get("deck_id")
        theme_id = kwargs.get("theme_id")
        if not deck_id_raw or not theme_id:
            return SkillResult.failed("Both `deck_id` and `theme_id` are required.")

        try:
            deck_id = UUID(str(deck_id_raw))
        except ValueError:
            return SkillResult.failed(f"Invalid deck_id: {deck_id_raw}")

        try:
            get_theme(theme_id)
        except ValueError as e:
            return SkillResult.failed(str(e))

        result = await ctx.db.execute(select(Deck).where(Deck.id == deck_id))
        deck = result.scalar_one_or_none()
        if not deck:
            return SkillResult.failed(f"Deck not found: {deck_id}")

        if deck.theme_id == theme_id:
            return SkillResult.success(
                data={"deck_id": str(deck.id), "theme_id": theme_id, "version": deck.current_version},
                message="Theme already applied — no change.",
            )

        new_version = deck.current_version + 1
        # Update theme_id inside the spec to keep them in sync.
        spec = dict(deck.spec)
        spec["theme_id"] = theme_id
        deck.spec = spec
        deck.theme_id = theme_id
        deck.current_version = new_version

        ctx.db.add(DeckVersion(
            deck_id=deck.id,
            version_no=new_version,
            spec=spec,
            theme_id=theme_id,
            source="theme_swap",
            prompt=None,
            created_by=ctx.user_id,
        ))
        await ctx.db.commit()

        return SkillResult.success(
            data={"deck_id": str(deck.id), "theme_id": theme_id, "version": new_version},
            message=f"Theme swapped to {theme_id}.",
            artifacts={"deck_id": str(deck.id), "spec": spec},
        )
