"""Translation cache I/O. Each call opens its own short-lived session — sharing
a session across parallel translations races SQLAlchemy's transaction state."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import async_session
from app.models.translation import TranslationCache


async def get(
    segment_hash: str,
    target_lang: str,
    glossary_ver: str,
) -> str | None:
    async with async_session() as db:
        stmt = select(TranslationCache.translation).where(
            TranslationCache.segment_hash == segment_hash,
            TranslationCache.target_lang == target_lang,
            TranslationCache.glossary_ver == glossary_ver,
        )
        return (await db.execute(stmt)).scalar_one_or_none()


async def store(
    segment_hash: str,
    target_lang: str,
    glossary_ver: str,
    translation: str,
    model: str,
) -> None:
    """Idempotent insert — races on identical keys are dropped silently."""
    async with async_session() as db:
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
