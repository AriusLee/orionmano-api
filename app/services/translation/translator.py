"""Translation entry points.

translate_segment: paragraph-level, cache-aware. Hits the LLM only on cache miss.
translate_document: splits markdown into paragraphs and translates them in
parallel (bounded), preserving paragraph order.

Per the design discussion: same EN content + same target lang + same glossary_ver
→ guaranteed cache hit. Numbers are part of the hash, so per-deal figures are
cached separately as intended."""
import asyncio

from app.services.ai.client import generate_text, DEEPSEEK_MODEL
from app.services.translation import cache, glossary, segmenter

SUPPORTED_LANGS = {"zh-CN", "ja"}

_LANG_NAMES = {
    "zh-CN": "Simplified Chinese (mainland PRC business-finance register)",
    "ja": "Japanese (formal business-finance register suitable for an IPO prospectus)",
}


def _build_system_prompt(target_lang: str, glossary_block: str) -> str:
    lang_name = _LANG_NAMES[target_lang]
    glossary_section = glossary_block if glossary_block else "(no glossary terms apply to this segment)"
    return (
        f"You translate Nasdaq IPO advisory report content from English into {lang_name}.\n"
        "\n"
        "RULES (in priority order):\n"
        "1. Use the glossary below for every listed term — these renderings are required, not suggestions. "
        "If a term is marked \"keep as English literal\", do not translate it.\n"
        "2. Preserve all numbers, dates, currencies, percentages, ticker symbols, and proper nouns "
        "exactly as written in the source.\n"
        "3. Preserve markdown structure: headers (#), lists (-, *, 1.), bold/italic (**, *), tables (|), code (`).\n"
        "4. Keep the same paragraph count — one input paragraph → one output paragraph.\n"
        "5. Do not add commentary, explanations, or anything not in the source. Output only the translation.\n"
        "\n"
        f"GLOSSARY (English → required {target_lang} rendering):\n"
        f"{glossary_section}\n"
    )


async def translate_segment(en_text: str, target_lang: str) -> str:
    if target_lang not in SUPPORTED_LANGS:
        raise ValueError(f"Unsupported target_lang: {target_lang!r}; must be one of {SUPPORTED_LANGS}")
    if not segmenter.is_translatable(en_text):
        return en_text

    normalized = segmenter.normalize_for_hash(en_text)
    seg_hash = segmenter.segment_hash(normalized)
    ver = glossary.glossary_version()

    hit = await cache.get(seg_hash, target_lang, ver)
    if hit is not None:
        return hit

    relevant = glossary.relevant_terms(en_text)
    glossary_block = glossary.render_glossary_for_prompt(relevant, target_lang)
    system_prompt = _build_system_prompt(target_lang, glossary_block)

    translation = (await generate_text(
        system_prompt=system_prompt,
        user_prompt=en_text,
        max_tokens=max(2048, len(en_text) * 2),
        skill=f"translate:{target_lang}",
    )).strip()

    await cache.store(seg_hash, target_lang, ver, translation, model=DEEPSEEK_MODEL)
    return translation


async def translate_document(en_text: str, target_lang: str, concurrency: int = 5) -> str:
    """Translate a full markdown document by paragraphs in parallel."""
    segments = segmenter.split_paragraphs(en_text)
    sem = asyncio.Semaphore(concurrency)

    async def one(seg: str) -> str:
        async with sem:
            return await translate_segment(seg, target_lang)

    results = await asyncio.gather(*(one(s) for s in segments))
    return "\n\n".join(results)
