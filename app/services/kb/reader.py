"""Read-side helper for compiled kb pages. Skills call get_kb_pages() to fetch
the dict of {slug: content} for a company, then inject the relevant subset into
their LLM prompt — instead of flattening the raw extracted_data blob."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_kb_page import ClientKbPage


async def get_kb_pages(
    db: AsyncSession,
    company_id: uuid.UUID,
    slugs: list[str] | None = None,
) -> dict[str, str]:
    """Return {slug: content} for the requested slugs (or all pages if None).
    Empty dict if no pages compiled yet — caller is responsible for falling
    back to raw extracted_data in that case."""
    stmt = select(ClientKbPage.slug, ClientKbPage.content).where(
        ClientKbPage.company_id == company_id
    )
    if slugs:
        stmt = stmt.where(ClientKbPage.slug.in_(slugs))
    rows = (await db.execute(stmt)).all()
    return {slug: content for slug, content in rows}


def format_kb_pages_for_prompt(pages: dict[str, str]) -> str:
    """Render the {slug: content} dict as a single context block for the LLM.
    Returns empty string if no pages — caller should detect and fall back."""
    if not pages:
        return ""
    parts = ["## Company Knowledge Base (compiled from uploaded documents)"]
    for slug, content in pages.items():
        parts.append(f"\n<!-- page: {slug} -->\n{content}")
    return "\n".join(parts)
