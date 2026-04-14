"""Skill wrapper for document extraction."""

from __future__ import annotations

from typing import Any

from app.services.agent.skill import Skill, SkillResult, SkillParameter
from app.services.agent.context import AgentContext


class ExtractDocumentSkill(Skill):
    name = "extract_document"
    description = (
        "Extract structured data (financials, company info, shareholders, key personnel) "
        "from an uploaded document. Requires a document_id of an already-uploaded file."
    )
    parameters = [
        SkillParameter(
            name="document_id",
            type="string",
            description="UUID of the uploaded document to extract",
        ),
    ]

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        import uuid
        from sqlalchemy import select
        from app.models.document import Document
        from app.services.ai.document_parser import extract_document
        from app.services.company_intelligence import auto_fill_company

        doc_id = kwargs["document_id"]

        try:
            doc_uuid = uuid.UUID(doc_id)
        except ValueError:
            return SkillResult.failed(f"Invalid document ID: {doc_id}")

        result = await ctx.db.execute(select(Document).where(Document.id == doc_uuid))
        doc = result.scalar_one_or_none()
        if not doc:
            return SkillResult.failed(f"Document {doc_id} not found")

        if doc.extraction_status == "completed" and doc.extracted_data:
            return SkillResult.success(
                data=doc.extracted_data,
                message=f"Document '{doc.filename}' already extracted.",
            )

        try:
            doc.extraction_status = "processing"
            await ctx.db.commit()

            extracted = await extract_document(doc.file_path)
            doc.extracted_data = extracted
            doc.extraction_status = "completed"
            await ctx.db.commit()

            # Auto-fill company profile
            if ctx.company_id:
                await auto_fill_company(ctx.db, ctx.company_id)

            return SkillResult.success(
                data=extracted,
                message=f"Successfully extracted data from '{doc.filename}'.",
                artifacts={"extracted_data": extracted},
            )
        except Exception as e:
            doc.extraction_status = "failed"
            await ctx.db.commit()
            return SkillResult.failed(f"Extraction failed: {str(e)}")
