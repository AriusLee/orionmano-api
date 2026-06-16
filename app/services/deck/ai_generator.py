"""Two-pass AI deck generator.

Pass 1 (outline) — one LLM call produces a slide outline: for each slide, the
chosen layout, a one-line intent, and which company facts to use.
Pass 2 (content) — one LLM call per slide fills the layout's content payload,
validated against the layout's pydantic schema. Retries once on validation
failure with the error fed back in.

Why two passes:
- Pass 1 decides global structure once (cheap; sees the full picture).
- Pass 2 is per-slide and parallelizable. Its system prompt is byte-identical
  across slides (catalog + theme + company context) so DeepSeek's prefix cache
  fires on every slide after the first, dropping cost to ~10%.

The LLM never emits HTML — only JSON the renderer knows how to draw. Malformed
JSON / wrong-shape content gets rejected; we don't pass invalid specs to
WeasyPrint.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.client import generate_text
from app.services.agent.memory import retrieve_memories
from app.services.deck.context import build_deck_context, context_to_prompt_block
from app.services.deck.schema import (
    LayoutName,
    Slide,
    SlideSpec,
    _LAYOUT_TO_MODEL,
    layout_catalog_for_prompt,
)
from app.services.deck.themes import Theme, get_theme

SKILL_NAME = "generate_deck"

# Preset prompts — buttons in the UI that prefill the user prompt. The
# generation path is identical for preset vs free-prompt decks.
PRESETS: dict[str, str] = {
    "sales_deck": (
        "Generate a 6-slide engagement proposal: cover, about Orionmano, "
        "understanding this client's business, comprehensive scope of advisory "
        "services, our AI-powered approach, and a next-steps closing slide."
    ),
    "kickoff_deck": (
        "Generate a 4-slide engagement kick-off: cover, scope of services, "
        "timeline phases (1-2 / 3-6 / 5-8 / 8-10 weeks), and next steps."
    ),
    "teaser": (
        "Generate a 2-3 slide investor teaser: cover, company overview with "
        "investment highlights, and transaction details (engagement type, "
        "target exchange)."
    ),
    "company_deck": (
        "Generate a 4-6 slide investor presentation: cover, investment thesis, "
        "business model and growth drivers, market position with key stats, "
        "and a closing slide."
    ),
}


# ---------------------------------------------------------------------------
# Outline-pass intermediate types. These are NOT the final SlideSpec — they
# capture the LLM's plan for each slide before content is generated.
# ---------------------------------------------------------------------------


class OutlineSlide(BaseModel):
    model_config = ConfigDict(extra="ignore")
    layout: LayoutName
    intent: str = Field(..., description="One-line description of what this slide should communicate.")
    key_facts: list[str] = Field(
        default_factory=list,
        description="Bullet list of facts from the company context this slide must reference (verbatim where possible).",
    )


class Outline(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    rationale: str | None = None
    slides: list[OutlineSlide] = Field(..., min_length=1, max_length=30)


# ---------------------------------------------------------------------------
# JSON extraction — DeepSeek occasionally wraps JSON in ```json fences or
# adds a sentence of prose. Be tolerant.
# ---------------------------------------------------------------------------


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of an LLM response. Tries (1) strict parse,
    (2) fenced ```json block, (3) first {...} substring. Raises on total failure."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    m = _JSON_OBJECT_RE.search(text)
    if m:
        return json.loads(m.group(0))

    raise ValueError(f"No JSON object found in LLM response: {text[:200]}...")


# ---------------------------------------------------------------------------
# Prompts. Kept as module-level functions so the system prompt for any given
# (theme, context, memory) tuple is byte-stable across all per-slide calls.
# ---------------------------------------------------------------------------


def _theme_block(theme: Theme) -> str:
    return (
        f"Theme: {theme.name} (id={theme.id})\n"
        f"Brand: {theme.brand_label}\n"
        f"Tagline: {theme.brand_tagline}\n"
    )


def _memory_block(rules: list[str]) -> str:
    if not rules:
        return "(no prior style preferences)"
    return "\n".join(f"- {r}" for r in rules)


def _outline_system_prompt(
    theme: Theme,
    context_block: str,
    memory_block: str,
) -> str:
    """Stable across all calls in one generation. Cacheable."""
    return f"""You design slide deck outlines.

You will be given a user prompt describing the deck they want, plus structured \
company data. Your job: pick the slides (layout + intent for each) that best \
satisfy the prompt using the data we have.

Hard rules:
- Pick layouts only from the catalog below. Never invent a layout.
- The first slide MUST be a `cover`. The last slide SHOULD be `cta`.
- Decks should be 4-20 slides unless the user explicitly asks otherwise.
- For each slide, list the specific facts from the company data the slide must \
reference (verbatim values where applicable: company name, financial numbers, \
target exchange, etc.). If no specific data applies (e.g. an "about us" slide \
for the advisory firm), leave key_facts empty.
- Do not write the slide *content* yet — only the plan. A separate pass will \
fill content per slide.

{layout_catalog_for_prompt()}

{_theme_block(theme)}

Style preferences (apply these unless the user prompt overrides them):
{memory_block}

Company data (use only what fits the slide's intent):
{context_block}

Output: a single JSON object with this exact shape, and nothing else:
{{
  "title": "<short deck title>",
  "rationale": "<one sentence on how the outline matches the prompt>",
  "slides": [
    {{"layout": "<layout_name>", "intent": "<one line>", "key_facts": ["..."]}},
    ...
  ]
}}
""".strip()


def _content_system_prompt(
    theme: Theme,
    context_block: str,
    memory_block: str,
) -> str:
    """Stable across every per-slide content call in one generation. The
    variable parts (which layout, intent, key_facts) go in the user prompt.
    Byte-identical system prompt = full DeepSeek cache hits after slide 1."""
    return f"""You fill in the content for one slide of a deck.

You will receive: the slide's chosen layout, a one-line intent, key facts to \
reference, and the JSON schema for that layout's content. Return a JSON object \
matching that schema exactly — no extra fields, no prose around it.

Hard rules:
- Output JSON only. No markdown, no commentary.
- Field types must match the schema (strings for strings, arrays for arrays).
- Keep text tight: titles ≤ 8 words, eyebrows ≤ 4 words and uppercase-ish, \
bullet text ≤ 18 words, card body ≤ 24 words, stat values short (e.g. "45%", \
"$12M", "IFRS 13"), stat labels uppercase-style 1-3 words.
- Use facts verbatim from `key_facts` when given. Never fabricate financial \
numbers, currencies, dates, or named entities that aren't in the context.
- If a field is optional and you have nothing strong to put there, omit it \
(don't pad).

{layout_catalog_for_prompt()}

{_theme_block(theme)}

Style preferences:
{memory_block}

Company data available (reference but don't invent):
{context_block}
""".strip()


def _content_user_prompt(
    slide_index: int,
    total_slides: int,
    outline_slide: OutlineSlide,
    layout_schema: dict[str, Any],
) -> str:
    return f"""Slide {slide_index + 1} of {total_slides}.

Layout: {outline_slide.layout}
Intent: {outline_slide.intent}
Key facts to reference: {json.dumps(outline_slide.key_facts, ensure_ascii=False)}

Content schema for this layout (JSON Schema):
{json.dumps(layout_schema, ensure_ascii=False)}

Return only a JSON object matching that schema. Nothing else.""".strip()


def _outline_user_prompt(prompt: str, preset: str | None) -> str:
    preset_note = f"\n(Started from preset: {preset})" if preset else ""
    return f"""User prompt:
{prompt}{preset_note}

Generate the outline now.""".strip()


# ---------------------------------------------------------------------------
# Validation + retry helpers.
# ---------------------------------------------------------------------------


async def _generate_slide_content(
    *,
    slide_index: int,
    total_slides: int,
    outline_slide: OutlineSlide,
    content_system_prompt: str,
    company_id: UUID,
    max_retries: int = 1,
) -> dict[str, Any]:
    """Run pass 2 for a single slide. On validation failure, retry up to
    `max_retries` times with the validation error fed back into the user
    prompt. Raises ValueError if all attempts fail."""
    model_cls = _LAYOUT_TO_MODEL[outline_slide.layout]
    layout_schema = model_cls.model_json_schema()

    base_user_prompt = _content_user_prompt(
        slide_index, total_slides, outline_slide, layout_schema
    )

    last_error: str | None = None
    user_prompt = base_user_prompt
    for attempt in range(max_retries + 1):
        if attempt > 0:
            user_prompt = (
                f"{base_user_prompt}\n\n"
                f"Your previous attempt failed validation with:\n{last_error}\n"
                "Fix it and return valid JSON for the schema. JSON only."
            )

        raw = await generate_text(
            system_prompt=content_system_prompt,
            user_prompt=user_prompt,
            max_tokens=1200,
            skill=SKILL_NAME,
            company_id=company_id,
        )

        try:
            payload = _extract_json_object(raw)
            # Validate against the layout's pydantic class. Raises on shape mismatch.
            model_cls.model_validate(payload)
            return payload
        except (ValueError, ValidationError) as e:
            last_error = str(e)[:400]
            continue

    raise ValueError(
        f"Slide {slide_index + 1} ({outline_slide.layout}) failed validation "
        f"after {max_retries + 1} attempts. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Public entry: full two-pass generation.
# ---------------------------------------------------------------------------


async def generate_deck_spec(
    db: AsyncSession,
    *,
    company_id: UUID,
    theme_id: str,
    prompt: str,
    preset: str | None = None,
    parallel_content: bool = True,
) -> SlideSpec:
    """Generate a complete, validated SlideSpec for the given company + theme +
    prompt. Caller is responsible for persisting it.

    If `preset` is provided and `prompt` is empty, the preset's prompt is used.
    If both are provided, the user's prompt wins and the preset is recorded only
    for analytics.
    """
    if not prompt and preset:
        prompt = PRESETS.get(preset, "")
    if not prompt:
        raise ValueError("Either prompt or a known preset must be provided.")

    theme = get_theme(theme_id)

    # 1. Gather everything the LLM will reference.
    ctx = await build_deck_context(db, company_id)
    context_block = context_to_prompt_block(ctx)
    memory_rules = await retrieve_memories(
        db, company_id=company_id, skill_name=SKILL_NAME
    )
    memory_block = _memory_block(memory_rules)

    # 2. Outline pass.
    outline_sys = _outline_system_prompt(theme, context_block, memory_block)
    outline_user = _outline_user_prompt(prompt, preset)
    outline_raw = await generate_text(
        system_prompt=outline_sys,
        user_prompt=outline_user,
        max_tokens=2000,
        skill=SKILL_NAME,
        company_id=company_id,
    )
    outline = Outline.model_validate(_extract_json_object(outline_raw))

    # 3. Content pass — per-slide, optionally parallel. The system prompt is
    # byte-identical across calls so DeepSeek's prefix cache amortizes the
    # context block across all slides.
    content_sys = _content_system_prompt(theme, context_block, memory_block)
    total = len(outline.slides)

    async def _one(idx: int, outline_slide: OutlineSlide) -> Slide:
        content = await _generate_slide_content(
            slide_index=idx,
            total_slides=total,
            outline_slide=outline_slide,
            content_system_prompt=content_sys,
            company_id=company_id,
        )
        return Slide(layout=outline_slide.layout, content=content)

    if parallel_content:
        slides = await asyncio.gather(
            *[_one(i, s) for i, s in enumerate(outline.slides)]
        )
    else:
        slides = []
        for i, s in enumerate(outline.slides):
            slides.append(await _one(i, s))

    # 4. Assemble and final-validate.
    spec = SlideSpec(
        theme_id=theme_id,
        title=outline.title,
        slides=list(slides),
        outline_rationale=outline.rationale,
    )
    spec.validate_all_content()
    return spec


# ---------------------------------------------------------------------------
# Amend pass — same shape as generation but operates on an existing spec.
# ---------------------------------------------------------------------------


def _amend_system_prompt(theme: Theme, context_block: str, memory_block: str) -> str:
    return f"""You edit an existing slide deck spec in response to a user instruction.

You receive: the current SlideSpec as JSON, a layout catalog, the company \
data, and a user instruction describing what to change. Return a complete \
NEW SlideSpec JSON applying that change. Preserve everything the user didn't \
ask to change. Output JSON only.

Hard rules:
- Output a complete SlideSpec, not a diff/patch. Easier to validate.
- Only use layouts from the catalog. Never invent.
- Keep the theme_id field unchanged unless the user explicitly asked for a swap.
- If the user asks to add a slide, insert it at the position they describe \
(or just before the closing slide if unspecified).
- If the user asks to remove a slide, drop it. If they ask to reorder, reorder.
- If they ask to rewrite content, regenerate that slide's content payload \
in-place (same layout unless they say otherwise).
- Never fabricate financial numbers / dates / entities not in the company data.

{layout_catalog_for_prompt()}

{_theme_block(theme)}

Style preferences:
{memory_block}

Company data:
{context_block}
""".strip()


async def amend_deck_spec(
    db: AsyncSession,
    *,
    company_id: UUID,
    current_spec: SlideSpec,
    prompt: str,
    theme_id_override: str | None = None,
) -> SlideSpec:
    """Apply a user instruction to an existing spec. Returns a new validated
    SlideSpec. The caller persists the new version and re-renders the PDF."""
    theme = get_theme(theme_id_override or current_spec.theme_id)

    ctx = await build_deck_context(db, company_id)
    context_block = context_to_prompt_block(ctx)
    memory_rules = await retrieve_memories(
        db, company_id=company_id, skill_name=SKILL_NAME
    )
    memory_block = _memory_block(memory_rules)

    sys_prompt = _amend_system_prompt(theme, context_block, memory_block)
    user_prompt = (
        f"Current SlideSpec:\n{current_spec.model_dump_json(indent=2)}\n\n"
        f"User instruction:\n{prompt}\n\n"
        "Return the new SlideSpec JSON."
    )

    raw = await generate_text(
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        max_tokens=4000,
        skill=SKILL_NAME,
        company_id=company_id,
    )
    new_spec_dict = _extract_json_object(raw)

    # Force theme_id if override given (don't trust the LLM on this).
    if theme_id_override:
        new_spec_dict["theme_id"] = theme_id_override

    new_spec = SlideSpec.model_validate(new_spec_dict)
    new_spec.validate_all_content()
    return new_spec
