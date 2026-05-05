from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.translation import TranslationCache


async def get(
    db: AsyncSession,
    segment_hash: str,
    target_lang: str,
    glossary_ver: str,
) -> str | None:
    stmt = select(TranslationCache.translation).where(
        TranslationCache.segment_hash == segment_hash,
        TranslationCache.target_lang == target_lang,
        TranslationCache.glossary_ver == glossary_ver,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def store(
    db: AsyncSession,
    segment_hash: str,
    target_lang: str,
    glossary_ver: str,
    translation: str,
    model: str,
) -> None:
    """Upsert — concurrent translators on the same segment race; last write wins
    on the translation, but the row is the same key so it's idempotent."""
    stmt = insert(TranslationCache).values(
        segment_hash=segment_hash,
        target_lang=target_lang,
        glossary_ver=glossary_ver,
        translation=translation,
        model=model,
    ).on_conflict_do_nothing(
        index_elements=["segment_hash", "target_lang", "glossary_ver"],
    )
    await db.execute(stmt)
    await db.commit()
