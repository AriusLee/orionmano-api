"""Agent execution context shared across skills."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentContext:
    """Shared context passed to every skill during execution."""

    db: AsyncSession
    company_id: uuid.UUID | None = None

    # Populated lazily by the router before skill execution
    company: Any = None
    documents: list[dict] = field(default_factory=list)
    reports: list[dict] = field(default_factory=list)

    # Outputs from prior skills in a chain (skill_name -> result data)
    artifacts: dict[str, Any] = field(default_factory=dict)

    # Memory rules injected for the current task
    memory_rules: list[str] = field(default_factory=list)

    # User info
    user_id: uuid.UUID | None = None

    # Conversation context (for chat-triggered skills)
    conversation_id: uuid.UUID | None = None
    message_history: list[dict] = field(default_factory=list)

    async def load_company_data(self) -> None:
        """Load company, documents, and reports from DB."""
        if self.company_id is None:
            return

        from sqlalchemy import select
        from app.models import Company, Document, Report

        result = await self.db.execute(
            select(Company).where(Company.id == self.company_id)
        )
        self.company = result.scalar_one_or_none()

        if self.company:
            result = await self.db.execute(
                select(Document).where(
                    Document.company_id == self.company_id,
                    Document.extraction_status == "completed",
                )
            )
            docs = result.scalars().all()
            self.documents = [
                {
                    "id": str(d.id),
                    "filename": d.filename,
                    "extracted_data": d.extracted_data or {},
                }
                for d in docs
            ]

            result = await self.db.execute(
                select(Report).where(
                    Report.company_id == self.company_id,
                    Report.status == "draft",
                )
            )
            reports = result.scalars().all()
            self.reports = [
                {
                    "id": str(r.id),
                    "report_type": r.report_type,
                    "tier": r.tier,
                }
                for r in reports
            ]

    def get_company_context_str(self) -> str:
        """Build a concise company context string for prompts."""
        if not self.company:
            return ""

        c = self.company
        parts = [f"Company: {c.name}"]
        if c.industry:
            parts.append(f"Industry: {c.industry}")
        if c.country:
            parts.append(f"Country: {c.country}")
        if c.description:
            parts.append(f"Description: {c.description[:500]}")
        if c.engagement_type:
            parts.append(f"Engagement: {c.engagement_type}")
        if c.target_exchange:
            parts.append(f"Target Exchange: {c.target_exchange}")

        # Add extracted document data
        if self.documents:
            parts.append("\n--- Extracted Document Data ---")
            for doc in self.documents:
                ext = doc.get("extracted_data", {})
                if ext:
                    parts.append(f"\n[{doc['filename']}]")
                    summary = ext.get("summary", "")
                    if summary:
                        parts.append(summary[:2000])

        return "\n".join(parts)

    def get_memory_prompt(self) -> str:
        """Format memory rules as a prompt section."""
        if not self.memory_rules:
            return ""

        rules = "\n".join(f"- {rule}" for rule in self.memory_rules)
        return (
            "\n## Guidelines from past feedback (follow these strictly):\n"
            f"{rules}\n"
        )
