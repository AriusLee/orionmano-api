"""Call _plan_outline in isolation and dump the raw response so we can see
why the JSON parse is failing in the live pipeline."""

from __future__ import annotations

import asyncio
from datetime import date

from app.services.article.generator import (
    _plan_outline,
    OUTLINE_SYSTEM_PROMPT,
)
from app.services.ai.client import generate_text
from app.services.ai.web_search import web_search, format_search_results


TOPIC = "global-lithium-supply"
CLAIM = (
    "Australia and Chile together accounted for roughly 75% of global mined "
    "lithium supply in 2023."
)


async def main() -> None:
    print("Fetching web sources …")
    try:
        results = await web_search(f"{TOPIC.replace('-', ' ')} {CLAIM[:120]}", max_results=6)
    except Exception as e:
        print("web_search failed:", e)
        results = []
    sources_block = format_search_results(results) or "(No external web results available.)"
    print(f"  got {len(results)} results, {len(sources_block)} chars\n")

    # First, try via _plan_outline (the real entrypoint).
    print("=== _plan_outline (production call path) ===")
    try:
        outline = await _plan_outline(
            title="probe", topic=TOPIC, claim=CLAIM,
            article_date=date.today(), sources_block=sources_block,
        )
        print("OK — keys:", list(outline.keys()))
        print("exhibits count:", len(outline.get("exhibits") or []))
    except Exception as e:
        print("FAILED:", type(e).__name__, str(e)[:300])

    # Then, dump the raw LLM response (no JSON parsing) so we can see what
    # the model actually returned.
    print("\n=== raw LLM response (for inspection) ===")
    user_prompt_minimal = (
        f"Plan an analysis article. Topic: {TOPIC}. Claim: {CLAIM}\n\n"
        "Return ONLY a JSON object with these keys: headline, deck, "
        "key_takeaways, topic_tags, lede_angle, sections, exhibits, outlook."
    )
    raw = await generate_text(
        system_prompt=OUTLINE_SYSTEM_PROMPT,
        user_prompt=user_prompt_minimal,
        max_tokens=2500,
        use_reasoner=True,
    )
    print("--- first 1800 chars ---")
    print(raw[:1800])
    print("\n--- last 300 chars ---")
    print(raw[-300:])
    print(f"\ntotal length: {len(raw)} chars")


if __name__ == "__main__":
    asyncio.run(main())
