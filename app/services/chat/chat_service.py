from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.chat import ChatConversation, ChatMessage
from app.models.company import Company
from app.models.document import Document
from app.models.report import Report, ReportSection
from app.services.ai.client import stream_text

import json


async def build_system_prompt(db: AsyncSession, company_id: UUID) -> str:
    # Get company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    parts = [
        "You are an expert financial advisor at Orionmano Assurance Services, a Hong Kong-based financial advisory firm.",
        "You are helping an advisor work on a client engagement. Be professional, insightful, and data-driven.",
        "When discussing financial data, be specific with numbers and percentages.",
        "You can help with: analyzing documents, refining reports, answering questions about the company, and providing advisory insights.",
    ]

    if company:
        parts.append(f"\n## Current Company: {company.name}")
        if company.industry:
            parts.append(f"Industry: {company.industry}")
        if company.description:
            parts.append(f"Description: {company.description}")
        if company.country:
            parts.append(f"Country: {company.country}")
        if company.engagement_type:
            parts.append(f"Engagement Type: {company.engagement_type}")

    # Get extracted document data
    doc_result = await db.execute(
        select(Document).where(
            Document.company_id == company_id,
            Document.extraction_status == "completed",
        )
    )
    docs = doc_result.scalars().all()
    if docs:
        parts.append("\n## Extracted Document Data")
        for doc in docs:
            parts.append(f"\n### {doc.filename}")
            if doc.extracted_data:
                parts.append(json.dumps(doc.extracted_data, indent=2, default=str)[:5000])

    # Get report sections
    report_result = await db.execute(
        select(Report).where(Report.company_id == company_id, Report.status == "draft")
    )
    reports = report_result.scalars().all()
    if reports:
        parts.append("\n## Generated Reports")
        for report in reports:
            parts.append(f"\n### {report.title} (Status: {report.status})")
            sect_result = await db.execute(
                select(ReportSection).where(ReportSection.report_id == report.id).order_by(ReportSection.sort_order)
            )
            for section in sect_result.scalars().all():
                parts.append(f"\n#### {section.section_title}")
                if section.content:
                    parts.append(section.content[:2000])

    return "\n".join(parts)


async def get_conversation_messages(db: AsyncSession, conversation_id: UUID) -> list[dict]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()
    # Keep last 20 messages to stay within token budget
    recent = list(messages)[-20:]
    return [{"role": m.role, "content": m.content} for m in recent if m.role in ("user", "assistant")]


async def chat_stream(
    db: AsyncSession,
    conversation_id: UUID,
    company_id: UUID,
    user_content: str,
):
    # Save user message
    user_msg = ChatMessage(
        conversation_id=conversation_id,
        role="user",
        content=user_content,
    )
    db.add(user_msg)
    await db.commit()

    # Build context
    system_prompt = await build_system_prompt(db, company_id)
    messages = await get_conversation_messages(db, conversation_id)

    # Stream response
    full_response = []
    async for chunk in stream_text(
        system_prompt=system_prompt,
        messages=messages,
        max_tokens=4096,
    ):
        full_response.append(chunk)
        yield chunk

    # Save assistant message
    assistant_msg = ChatMessage(
        conversation_id=conversation_id,
        role="assistant",
        content="".join(full_response),
    )
    db.add(assistant_msg)
    await db.commit()
