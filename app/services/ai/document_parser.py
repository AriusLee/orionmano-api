import json
import os
import re
import fitz  # pymupdf

from app.services.ai.client import generate_text


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tiff")


# Filename keyword → category map. Order matters: more specific keywords first so
# generic tokens (e.g. "incorporation" → legal) don't swallow narrower ones
# (e.g. "tin certificate" → tax_return). Filenames are normalized to lowercase
# alphanumeric tokens before matching, so keywords here should be too.
FILENAME_KEYWORDS: list[tuple[str, str]] = [
    # tax
    ("cp204", "tax_return"),
    ("lhdn", "tax_return"),
    ("tin certificate", "tax_return"),
    ("tin", "tax_return"),
    ("ea form", "tax_return"),
    ("tax return", "tax_return"),
    ("tax computation", "tax_return"),
    ("tax filing", "tax_return"),
    # audit
    ("audited", "audit_report"),
    ("audit report", "audit_report"),
    ("auditor", "audit_report"),
    ("afs", "audit_report"),  # Audited Financial Statements
    ("statutory audit", "audit_report"),
    # management accounts
    ("management accounts", "management_accounts"),
    ("management account", "management_accounts"),
    ("mgmt account", "management_accounts"),
    # prospectus
    ("prospectus", "prospectus"),
    ("offering memorandum", "prospectus"),
    # org chart
    ("org chart", "org_chart"),
    ("organization chart", "org_chart"),
    ("organisation chart", "org_chart"),
    ("corporate structure", "org_chart"),
    ("group structure", "org_chart"),
    ("holding structure", "org_chart"),
    # cap table
    ("cap table", "cap_table"),
    ("shareholder register", "cap_table"),
    ("share register", "cap_table"),
    # shareholder agreement
    ("shareholders agreement", "shareholder_agreement"),
    ("shareholder agreement", "shareholder_agreement"),
    ("investment agreement", "shareholder_agreement"),
    ("subscription agreement", "shareholder_agreement"),
    ("term sheet", "shareholder_agreement"),
    ("sha", "shareholder_agreement"),
    # board minutes
    ("board minutes", "board_minutes"),
    ("board resolution", "board_minutes"),
    ("directors resolution", "board_minutes"),
    ("minutes of meeting", "board_minutes"),
    ("written resolution", "board_minutes"),
    # material contracts
    ("licensing agreement", "material_contract"),
    ("franchise agreement", "material_contract"),
    ("distribution agreement", "material_contract"),
    ("supply agreement", "material_contract"),
    ("mou", "material_contract"),
    # projections
    ("projection", "projections"),
    ("forecast", "projections"),
    ("budget", "projections"),
    ("business plan", "projections"),
    ("financial model", "projections"),
    # company profile
    ("company profile", "company_profile"),
    ("pitch deck", "company_profile"),
    ("company overview", "company_profile"),
    # interviews
    ("interview", "interview"),
    # legal (generic keywords last — "certificate" and "incorporation" match many filenames)
    ("certificate of incorporation", "legal"),
    ("memorandum of association", "legal"),
    ("articles of association", "legal"),
    ("legal opinion", "legal"),
    ("litigation", "legal"),
    ("incorporation", "legal"),
    ("ssm", "legal"),
    ("companies act", "legal"),
    ("constitution", "legal"),
]


def classify_by_filename(filename: str | None) -> str | None:
    """Best-effort classifier for when LLM extraction yields no document_type
    (scanned PDFs, image uploads, parse errors). Returns a taxonomy slug or None."""
    if not filename:
        return None
    norm = " " + re.sub(r"[^a-z0-9]+", " ", filename.lower()).strip() + " "
    for keyword, category in FILENAME_KEYWORDS:
        if f" {keyword} " in norm:
            return category
    return None


def extract_text_from_pdf(file_path: str, max_pages: int = 50) -> str:
    doc = fitz.open(file_path)
    text_parts = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        text_parts.append(page.get_text())
    doc.close()
    return "\n\n".join(text_parts)


async def extract_document(file_path: str, filename: str | None = None) -> dict:
    lower = file_path.lower()
    fname = filename or os.path.basename(file_path)

    # Images: hand to the vision model. A single image can legitimately satisfy
    # multiple slots (e.g. an org chart that also shows the cap table).
    if lower.endswith(IMAGE_EXTS):
        from app.services.ai.vision import classify_image_file

        try:
            v = await classify_image_file(file_path)
            cats = v.get("categories") or []
            if not cats or cats == ["other"]:
                # Vision said nothing useful — fall back to filename hint
                guessed = classify_by_filename(fname)
                if guessed:
                    cats = [guessed]
            return {
                "document_type": cats[0] if cats else "other",
                "categories": cats or ["other"],
                "classification_source": "vision",
                "summary": v.get("summary", ""),
            }
        except Exception as e:
            guessed = classify_by_filename(fname)
            return {
                "document_type": guessed or "other",
                "categories": [guessed] if guessed else ["other"],
                "classification_source": "filename" if guessed else "default",
                "error": f"Vision failed: {e}",
            }

    if lower.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    else:
        with open(file_path, "r", errors="ignore") as f:
            text = f.read()[:50000]

    # Scanned PDFs / empty docs — no text layer. Try vision on the first pages
    # before falling back to filename keywords.
    if not text.strip():
        if lower.endswith(".pdf"):
            from app.services.ai.vision import classify_pdf_via_vision

            try:
                v = await classify_pdf_via_vision(file_path, max_pages=2)
                cats = v.get("categories") or []
                if not cats or cats == ["other"]:
                    guessed = classify_by_filename(fname)
                    if guessed:
                        cats = [guessed]
                return {
                    "document_type": cats[0] if cats else "other",
                    "categories": cats or ["other"],
                    "classification_source": "vision_pdf",
                    "summary": v.get("summary", ""),
                    "raw_text": "",
                }
            except Exception:
                pass

        guessed = classify_by_filename(fname)
        return {
            "document_type": guessed or "other",
            "categories": [guessed] if guessed else ["other"],
            "classification_source": "filename" if guessed else "scan_needed",
            "error": "No text content extracted",
            "raw_text": "",
        }

    system_prompt = """You are a financial document analyst for Orionmano Assurance Services.
Extract structured data from the provided document. Return valid JSON with the following structure
(include only fields that are present in the document).

For `categories`, return an ARRAY of every slug that applies — a single document can satisfy
multiple slots. E.g. an annex inside an audit report that includes the shareholder register
matches BOTH "audit_report" AND "cap_table". Be generous but accurate: include a slug only
when the document's content clearly supports it. `document_type` should be the single primary
category (the first / most representative of the list).

Valid slugs for `document_type` and `categories`:
- audit_report — audited financial statements, auditor's opinion, PCAOB/MIA statutory audit reports
- management_accounts — interim/management P&L, balance sheet, unaudited financials
- tax_return — tax returns, tax filings, tax computations, CP204/LHDN filings
- org_chart — organization chart, corporate structure chart, group holding diagram
- cap_table — cap table, shareholder register, shareholding structure, share ledger
- board_minutes — board minutes, board resolutions, committee minutes, written resolutions
- shareholder_agreement — shareholders agreement, investment agreement, SHA, term sheet
- material_contract — customer / supplier / distribution / licensing / franchise contracts
- company_profile — company profile, pitch deck, corporate proposal, introduction slides
- projections — financial projections, budgets, forecasts, business plans with forward numbers
- legal — legal opinion, litigation report, regulatory correspondence, compliance letter
- prospectus — prospectus, offering memorandum, registration statement (S-1/F-1/20-F drafts)
- interview — management interview transcript, Q&A notes
- other — anything that does not clearly match the above

{
  "document_type": "audit_report|management_accounts|tax_return|org_chart|cap_table|board_minutes|shareholder_agreement|material_contract|company_profile|projections|legal|prospectus|interview|other",
  "categories": ["audit_report"],
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
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        guessed = classify_by_filename(fname)
        return {
            "raw_extraction": result,
            "parse_error": True,
            "document_type": guessed or "other",
            "categories": [guessed] if guessed else ["other"],
            "classification_source": "filename" if guessed else "default",
        }

    # Normalize categories: prefer the array the LLM returned, fall back to the
    # singular document_type, then filename heuristic. Keep document_type synced
    # to the first entry for any legacy callers.
    if isinstance(parsed, dict):
        raw_cats = parsed.get("categories")
        cats: list[str] = []
        if isinstance(raw_cats, list):
            for c in raw_cats:
                if isinstance(c, str) and c.strip():
                    c = c.strip().lower()
                    if c not in cats:
                        cats.append(c)

        doc_type = str(parsed.get("document_type") or "").strip().lower()

        if not cats and doc_type and doc_type != "other":
            cats = [doc_type]

        if not cats or cats == ["other"]:
            guessed = classify_by_filename(fname)
            if guessed:
                cats = [guessed]
                parsed["classification_source"] = "filename_fallback"

        if not cats:
            cats = ["other"]

        parsed["categories"] = cats
        parsed["document_type"] = cats[0]
    return parsed
