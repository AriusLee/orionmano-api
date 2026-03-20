import json
import fitz  # pymupdf

from app.services.ai.client import generate_text


def extract_text_from_pdf(file_path: str, max_pages: int = 50) -> str:
    doc = fitz.open(file_path)
    text_parts = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        text_parts.append(page.get_text())
    doc.close()
    return "\n\n".join(text_parts)


async def extract_document(file_path: str) -> dict:
    if file_path.lower().endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    else:
        with open(file_path, "r", errors="ignore") as f:
            text = f.read()[:50000]

    if not text.strip():
        return {"error": "No text content extracted", "raw_text": ""}

    system_prompt = """You are a financial document analyst for Orionmano Assurance Services.
Extract structured data from the provided document. Return valid JSON with the following structure
(include only fields that are present in the document):

{
  "document_type": "prospectus|audit_report|financial_statement|interview|legal|corporate|other",
  "company_info": {
    "name": "",
    "legal_name": "",
    "registration_number": "",
    "incorporation_date": "",
    "jurisdiction": "",
    "industry": "",
    "description": "",
    "website": ""
  },
  "financial_data": {
    "currency": "",
    "periods": ["FY2023", "FY2024"],
    "income_statement": {
      "revenue": {},
      "cost_of_revenue": {},
      "gross_profit": {},
      "operating_expenses": {},
      "finance_costs": {},
      "profit_before_tax": {},
      "taxation": {},
      "net_income": {}
    },
    "balance_sheet": {
      "total_assets": {},
      "total_liabilities": {},
      "total_equity": {},
      "current_assets": {},
      "current_liabilities": {},
      "cash": {}
    },
    "cash_flow": {
      "operating": {},
      "investing": {},
      "financing": {},
      "net_change": {}
    }
  },
  "shareholders": [
    {"name": "", "shares": 0, "percentage": 0}
  ],
  "key_personnel": [
    {"name": "", "title": "", "background": ""}
  ],
  "key_findings": [""],
  "summary": ""
}

Only include sections where you found relevant data. Keep values as numbers where possible.
For financial data, use the period as key (e.g. {"FY2023": 7522, "FY2024": 15291}).
"""

    result = await generate_text(
        system_prompt=system_prompt,
        user_prompt=f"Extract structured data from this document:\n\n{text[:30000]}",
        max_tokens=4096,
    )

    try:
        # Try to parse JSON from the response
        # Handle case where response has markdown code blocks
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_extraction": result, "parse_error": True}
