"""Generate branded PDF reports using WeasyPrint.

Brand (Orionmano vs MVPI) is selected per report_type — see app.services.branding.
"""

import os
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import markdown

from app.models.report import Report, ReportSection
from app.models.company import Company
from app.services.branding import brand_for, brand_logo_data_uri


REPORT_TYPE_LABELS = {
    "gap_analysis": "Gap Analysis",
    "industry_report": "Industry Expert Report",
    "dd_report": "Draft Financial Due Diligence Report",
    "valuation_report": "Valuation Report",
    "teaser": "Company Teaser",
    "sales_deck": "Sales Deck",
    "kickoff_deck": "Kick-off Meeting Deck",
    "company_deck": "Company Deck",
}

REPORT_ICONS = {
    "gap_analysis": "&#128203;",
    "industry_report": "&#127919;",
    "dd_report": "&#128187;",
    "valuation_report": "&#128200;",
    "teaser": "&#128196;",
}

def _page_css(brand_name: str, brand_subtitle: str) -> str:
    return (
        "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');\n"
        "@page {\n"
        "  size: A4;\n"
        "  margin: 25mm 20mm 30mm 20mm;\n"
        f'  @top-left {{ content: "{brand_name}"; font-family: \'Inter\', sans-serif; font-size: 8px; font-weight: 700; letter-spacing: 3px; color: #14B8A6; }}\n'
        f'  @top-right {{ content: "{brand_subtitle}"; font-family: \'Inter\', sans-serif; font-size: 8px; color: #94A3B8; letter-spacing: 1px; }}\n'
        "  @bottom-left { content: counter(page); font-family: 'Inter', sans-serif; font-size: 8px; color: #64748B; }\n"
        "  @bottom-right { content: \"Strictly Private and Confidential\"; font-family: 'Inter', sans-serif; font-size: 7px; color: #64748B; font-weight: 600; }\n"
        "}\n"
    )


_STATIC_CSS = """
@page :first {
  margin: 0;
  @top-left { content: none; }
  @top-right { content: none; }
  @bottom-left { content: none; }
  @bottom-right { content: none; }
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Inter', sans-serif; font-size: 10pt; color: #1E293B; line-height: 1.6; }

.cover {
  width: 210mm; height: 297mm; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center;
  background: #0C1929; color: #F8FAFC; page-break-after: always;
}
.cover .brand-logo { max-height: 56px; max-width: 180px; margin-bottom: 18px; object-fit: contain; }
.cover .brand { font-size: 14pt; font-weight: 700; letter-spacing: 8px; color: #14B8A6; margin-bottom: 8px; }
.cover .sub { font-size: 8pt; letter-spacing: 4px; color: #64748B; margin-bottom: 50px; text-transform: uppercase; }
.cover .icon { font-size: 72pt; margin-bottom: 40px; opacity: 0.6; }
.cover .company-logo { max-width: 120px; max-height: 120px; margin-bottom: 30px; border-radius: 12px; object-fit: contain; }
.cover h1 { font-size: 22pt; font-weight: 700; margin-bottom: 8px; }
.cover .report-type { font-size: 13pt; color: #94A3B8; margin-bottom: 6px; }
.cover .date { font-size: 9pt; color: #475569; margin-top: 50px; }
.cover .conf { font-size: 7pt; color: #475569; margin-top: 8px; font-weight: 600; }

.toc { page-break-after: always; padding-top: 20mm; }
.toc h2 { font-size: 16pt; font-weight: 700; color: #0C1929; margin-bottom: 20px; border-bottom: 2px solid #14B8A6; padding-bottom: 8px; }
.toc-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #E2E8F0; font-size: 10pt; }
.toc-item span:first-child { color: #1E293B; }

.notice { page-break-after: always; padding-top: 20mm; }
.notice h2 { font-size: 14pt; font-weight: 700; color: #0C1929; margin-bottom: 16px; }
.notice p { font-size: 9pt; color: #475569; margin-bottom: 12px; line-height: 1.7; }
.notice strong { font-size: 10pt; color: #1E293B; }

.section { page-break-before: always; }
.section:first-of-type { page-break-before: auto; }
.section h2 { font-size: 16pt; font-weight: 700; color: #0C1929; margin-bottom: 6px; padding-bottom: 8px; border-bottom: 2px solid #14B8A6; }
.section .content { margin-top: 16px; }
.section .content h1 { font-size: 14pt; font-weight: 700; color: #0C1929; margin-top: 16px; margin-bottom: 8px; }
.section .content h2 { font-size: 13pt; font-weight: 600; color: #0F172A; margin-top: 14px; margin-bottom: 6px; border: none; padding: 0; }
.section .content h3 { font-size: 11pt; font-weight: 600; color: #1E293B; margin-top: 12px; margin-bottom: 4px; }
.section .content p { margin-bottom: 8px; font-size: 10pt; color: #334155; }
.section .content ul, .section .content ol { margin: 8px 0 8px 20px; }
.section .content li { margin-bottom: 4px; font-size: 10pt; color: #334155; }
.section .content strong { color: #0F172A; }
.section .content code { background: #F1F5F9; padding: 1px 4px; border-radius: 3px; font-size: 9pt; }
.section .content pre { background: #F1F5F9; padding: 12px; border-radius: 6px; margin: 8px 0; overflow-x: auto; font-size: 8pt; }
.section .content blockquote { border-left: 3px solid #14B8A6; padding-left: 12px; margin: 8px 0; color: #475569; font-style: italic; }
.section .content table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 8pt; table-layout: fixed; word-wrap: break-word; overflow-wrap: break-word; }
.section .content th { background: #0C1929; color: #F8FAFC; padding: 5px 6px; text-align: left; font-weight: 600; word-wrap: break-word; overflow-wrap: break-word; }
.section .content td { padding: 4px 6px; border-bottom: 1px solid #E2E8F0; word-wrap: break-word; overflow-wrap: break-word; vertical-align: top; }
.section .content tr:nth-child(even) td { background: #F8FAFC; }
.section .content hr { border: none; border-top: 1px solid #CBD5E1; margin: 16px 0; }
.section .content h4 { font-size: 10pt; font-weight: 600; color: #334155; margin-top: 10px; margin-bottom: 4px; }
.section .content h5 { font-size: 9pt; font-weight: 600; color: #475569; margin-top: 8px; margin-bottom: 3px; }
.section .content em { color: #475569; }
.section .content a { color: #14B8A6; text-decoration: underline; }
.section .content img { max-width: 100%; height: auto; }
.section .content br { line-height: 0.5; }

/* Inline chart figures generated from ```chart``` JSON blocks */
.section .content figure.chart { margin: 16px 0; page-break-inside: avoid; }
.section .content figure.chart .chart-title { font-size: 10pt; font-weight: 600; color: #0F172A; margin-bottom: 6px; }
.section .content figure.chart .chart-body { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px; }
.section .content figure.chart .chart-body svg { display: block; max-width: 100%; height: auto; }
.section .content figure.chart .chart-source { font-size: 8pt; font-style: italic; color: #64748B; margin-top: 4px; }
.section .content pre.chart-error { background: #FEF2F2; color: #991B1B; padding: 8px; border-radius: 6px; font-size: 8pt; white-space: pre-wrap; }
"""


def _md_to_html(text: str) -> str:
    import re
    from app.services.report.chart_renderer import replace_chart_blocks

    # Strip wrapping markdown code fences the LLM sometimes adds
    stripped = text.strip()
    if stripped.startswith("```markdown"):
        stripped = stripped[len("```markdown"):].strip()
    if stripped.startswith("```md"):
        stripped = stripped[len("```md"):].strip()
    # Only strip an outer ``` fence if the OPENING fence isn't immediately
    # followed by a known code-block language we care about (`chart`).
    # Otherwise we'd swallow the chart block.
    if stripped.startswith("```") and not stripped.startswith("```chart"):
        stripped = stripped[3:].strip()
    if stripped.endswith("```") and not re.search(r"```chart\b[ \t]*\n?[\s\S]*?```\s*$", stripped):
        stripped = stripped[:-3].strip()

    # Convert ```chart {...}``` fences into inline-SVG <figure> blocks BEFORE
    # passing to the markdown parser so the JSON never reaches the renderer.
    stripped = replace_chart_blocks(stripped)

    # Ensure blank line before tables — markdown requires it for table parsing
    stripped = re.sub(r'(\S[^\n]*)\n(\|[^\n]+\|\s*\n\|[\s:|-]+\|)', r'\1\n\n\2', stripped)

    return markdown.markdown(
        stripped,
        extensions=[
            "tables",
            "fenced_code",
            "sane_lists",
            "md_in_html",
        ],
    )


async def generate_report_pdf(db: AsyncSession, company_id: UUID, report_id: UUID) -> bytes:
    result = await db.execute(
        select(Report).options(selectinload(Report.sections)).where(Report.id == report_id, Report.company_id == company_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise ValueError("Report not found")

    comp_result = await db.execute(select(Company).where(Company.id == company_id))
    company = comp_result.scalar_one_or_none()

    company_name = company.name if company else "Company"
    report_type_label = REPORT_TYPE_LABELS.get(report.report_type, report.report_type)
    icon = REPORT_ICONS.get(report.report_type, "&#128196;")
    date_str = datetime.now().strftime("%d %B %Y")
    brand = brand_for(report.report_type)
    brand_logo = brand_logo_data_uri(brand)
    brand_logo_html = (
        f'<img class="brand-logo" src="{brand_logo}" alt="{brand.name} logo" />'
        if brand_logo else ""
    )

    # Build company logo HTML — use fetched logo or fallback to icon
    logo_html = f'<div class="icon">{icon}</div>'
    if company and company.logo_path and os.path.exists(company.logo_path):
        import base64
        with open(company.logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        ext = company.logo_path.rsplit(".", 1)[-1].lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "ico": "image/x-icon", "webp": "image/webp"}.get(ext, "image/png")
        logo_html = f'<img class="company-logo" src="data:{mime};base64,{logo_b64}" alt="{company_name} logo" />'

    # Build sections HTML
    sections_html = ""
    toc_html = ""
    for i, section in enumerate(sorted(report.sections, key=lambda s: s.sort_order)):
        content_html = _md_to_html(section.content) if section.content else "<p><em>Content pending</em></p>"
        sections_html += f'<div class="section"><h2>{section.section_title}</h2><div class="content">{content_html}</div></div>'
        toc_html += f'<div class="toc-item"><span>{section.section_title}</span></div>'

    css = _page_css(brand.name, brand.subtitle) + _STATIC_CSS
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>

<!-- COVER PAGE -->
<div class="cover">
  {brand_logo_html}
  <div class="brand">{brand.name}</div>
  <div class="sub">{brand.subtitle}</div>
  {logo_html}
  <h1>{company_name}</h1>
  <div class="report-type">{report_type_label}</div>
  <div class="date">Transaction Services | {date_str}</div>
  <div class="conf">Strictly Private and Confidential</div>
</div>

<!-- TABLE OF CONTENTS -->
<div class="toc">
  <h2>Contents</h2>
  {toc_html}
</div>

<!-- IMPORTANT NOTICE -->
<div class="notice">
  <h2>Important Notice and Disclaimer</h2>
  <p><strong>Confidentiality Notice</strong></p>
  <p>This report is strictly private and confidential to {company_name} in accordance with the terms of our engagement agreement. Save as expressly provided for in the Contract, this report must not be recited or referred to in any document, or copied or made available (in whole or in part) to any other party.</p>
  <p><strong>Limitation of Liability</strong></p>
  <p>No party is entitled to rely on this report for any purpose whatsoever, and we accept no responsibility or liability for the contents of this report to any party other than {company_name}.</p>
  <p><strong>Document Authenticity</strong></p>
  <p>For your convenience, this report may have been made available to you in electronic and hardcopy format. Multiple copies and versions of this report may, therefore, exist in different media. Only a final signed copy of this report should be regarded as definitive.</p>
</div>

<!-- REPORT SECTIONS -->
{sections_html}

</body></html>"""

    from weasyprint import HTML
    return HTML(string=html).write_pdf()
