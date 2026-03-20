"""Generate branded presentation decks as PDF using HTML templates + WeasyPrint.
No AI tokens needed — template-based with company data slotted in."""

import json
from uuid import UUID
from io import BytesIO

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.document import Document
from app.services.deck.styles import CSS


def _footer(deck_name: str) -> str:
    return f'<div class="footer"><span class="brand">ORIONMANO</span><span>{deck_name}</span></div>'


def _esc(val: str | None) -> str:
    if not val:
        return ""
    return val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bullets(items: list[str]) -> str:
    return "".join(
        f'<div class="bullet-item"><span class="bullet">&#9654;</span><span>{_esc(item)}</span></div>'
        for item in items
    )


async def _get_company_data(db: AsyncSession, company_id: UUID) -> dict:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise ValueError("Company not found")

    doc_result = await db.execute(
        select(Document).where(Document.company_id == company_id, Document.extraction_status == "completed")
    )
    documents = list(doc_result.scalars().all())

    # Merge extracted data
    extracted = {}
    for doc in documents:
        if doc.extracted_data:
            for key, val in doc.extracted_data.items():
                if key not in extracted or not extracted[key]:
                    extracted[key] = val

    return {
        "name": company.name or "",
        "legal_name": company.legal_name or company.name or "",
        "industry": company.industry or "Financial Services",
        "sub_industry": company.sub_industry or "",
        "country": company.country or "Malaysia",
        "description": company.description or "",
        "website": company.website or "",
        "engagement_type": (company.engagement_type or "advisory").upper(),
        "target_exchange": (company.target_exchange or "").upper(),
        "extracted": extracted,
    }


def build_sales_deck(data: dict) -> str:
    name = _esc(data["name"])
    industry = _esc(data["industry"])
    country = _esc(data["country"])
    description = _esc(data["description"]) or f"A {industry.lower()} company based in {country}."
    f = _footer("Sales Deck")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>

<!-- SLIDE 1: COVER -->
<div class="slide">
  <div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
  <div class="glow glow-b" style="width:300px;height:300px;bottom:-50px;left:100px;opacity:0.08;"></div>
  <div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
    <div>
      <div style="font-size:16px;letter-spacing:10px;color:#14B8A6;font-weight:600;margin-bottom:36px;">ORIONMANO</div>
      <div style="font-size:11px;letter-spacing:4px;color:#64748B;margin-bottom:40px;">ASSURANCE SERVICES</div>
      <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
      <h1>{name}</h1>
      <p style="font-size:17px;color:#94A3B8;">Advisory Engagement Proposal</p>
      <p style="font-size:12px;color:#475569;margin-top:50px;">Strictly Private and Confidential</p>
    </div>
  </div>
</div>

<!-- SLIDE 2: ABOUT ORIONMANO -->
<div class="slide" style="padding:56px 70px;">
  <div class="glow glow-t" style="width:400px;height:400px;top:-150px;left:-150px;opacity:0.1;"></div>
  <div class="rel">
    <div class="label">About Orionmano</div>
    <h2>Your trusted <span class="teal">financial advisory</span> partner</h2>
    <div class="divider"></div>
    <div class="g2" style="gap:50px;margin-top:12px;">
      <div>
        <p style="margin-bottom:20px;">Orionmano International Holdings is a Hong Kong-based financial advisory firm specializing in business valuation, due diligence, accounting & tax services, and regulatory compliance.</p>
        <p>Our work follows international standards including IFRS 13 and ASC 820, ensuring accurate and reliable financial guidance for clients across Asia-Pacific.</p>
      </div>
      <div class="g2" style="gap:16px;">
        <div class="card" style="text-align:center;padding:20px;">
          <div class="stat-num" style="font-size:36px;">IFRS 13</div>
          <div class="stat-label">Fair Value</div>
        </div>
        <div class="card" style="text-align:center;padding:20px;">
          <div class="stat-num" style="font-size:36px;">ASC 820</div>
          <div class="stat-label">Compliance</div>
        </div>
        <div class="card" style="text-align:center;padding:20px;">
          <div class="stat-num" style="font-size:36px;">HK</div>
          <div class="stat-label">Headquarters</div>
        </div>
        <div class="card" style="text-align:center;padding:20px;">
          <div class="stat-num" style="font-size:36px;">APAC</div>
          <div class="stat-label">Coverage</div>
        </div>
      </div>
    </div>
  </div>
  {f}
</div>

<!-- SLIDE 3: UNDERSTANDING YOUR BUSINESS -->
<div class="slide" style="padding:56px 70px;">
  <div class="glow glow-b" style="width:400px;height:400px;bottom:-100px;right:-100px;opacity:0.06;"></div>
  <div class="rel">
    <div class="label">Understanding Your Business</div>
    <h2>{name}</h2>
    <div class="divider"></div>
    <div class="g2" style="gap:50px;margin-top:16px;">
      <div>
        <p style="margin-bottom:20px;">{description}</p>
        <div style="margin-top:24px;">
          <div class="bullet-item"><span class="bullet">&#9654;</span><span><strong>Industry:</strong> {industry}</span></div>
          <div class="bullet-item"><span class="bullet">&#9654;</span><span><strong>Country:</strong> {country}</span></div>
          {f'<div class="bullet-item"><span class="bullet">&#9654;</span><span><strong>Target:</strong> {_esc(data["target_exchange"])} Listing</span></div>' if data["target_exchange"] else ''}
          {f'<div class="bullet-item"><span class="bullet">&#9654;</span><span><strong>Website:</strong> {_esc(data["website"])}</span></div>' if data["website"] else ''}
        </div>
      </div>
      <div class="card-teal" style="display:flex;align-items:center;justify-content:center;text-align:center;">
        <div>
          <div class="stat-num" style="font-size:42px;">{data["engagement_type"]}</div>
          <div class="stat-label">Engagement Type</div>
        </div>
      </div>
    </div>
  </div>
  {f}
</div>

<!-- SLIDE 4: SCOPE OF SERVICES -->
<div class="slide" style="padding:56px 70px;">
  <div class="glow glow-t" style="width:350px;height:350px;top:-80px;left:-80px;opacity:0.08;"></div>
  <div class="rel">
    <div class="label">Proposed Scope</div>
    <h2>Comprehensive <span class="teal">advisory services</span></h2>
    <div class="divider"></div>
    <div class="g3" style="margin-top:24px;gap:16px;">
      <div class="card" style="padding:22px;">
        <div class="icon-box">&#128200;</div>
        <h3 style="font-size:15px;margin-bottom:6px;">Industry Expert Report</h3>
        <p style="font-size:12px;">Market research, competitive landscape, growth drivers, and strategic positioning analysis</p>
      </div>
      <div class="card" style="padding:22px;">
        <div class="icon-box">&#128269;</div>
        <h3 style="font-size:15px;margin-bottom:6px;">Due Diligence Report</h3>
        <p style="font-size:12px;">Financial DD, internal controls evaluation, risk assessment, and key findings</p>
      </div>
      <div class="card" style="padding:22px;">
        <div class="icon-box">&#128176;</div>
        <h3 style="font-size:15px;margin-bottom:6px;">Valuation Report</h3>
        <p style="font-size:12px;">DCF analysis, comparable companies, sensitivity analysis, and valuation reconciliation</p>
      </div>
      <div class="card" style="padding:22px;">
        <div class="icon-box">&#128196;</div>
        <h3 style="font-size:15px;margin-bottom:6px;">Company Teaser</h3>
        <p style="font-size:12px;">Concise 2-4 page investor teaser highlighting key metrics and opportunity</p>
      </div>
      <div class="card" style="padding:22px;">
        <div class="icon-box">&#127891;</div>
        <h3 style="font-size:15px;margin-bottom:6px;">Company Deck</h3>
        <p style="font-size:12px;">Full investor presentation with investment thesis, financials, and growth strategy</p>
      </div>
      <div class="card-teal" style="padding:22px;display:flex;align-items:center;justify-content:center;text-align:center;">
        <div>
          <div class="stat-num" style="font-size:32px;">AI</div>
          <div class="stat-label">Powered Platform</div>
          <p style="font-size:11px;margin-top:8px;">Faster delivery, deeper insights</p>
        </div>
      </div>
    </div>
  </div>
  {f}
</div>

<!-- SLIDE 5: OUR APPROACH -->
<div class="slide" style="padding:56px 70px;">
  <div class="glow glow-b" style="width:400px;height:400px;bottom:-100px;left:-100px;opacity:0.06;"></div>
  <div class="rel">
    <div class="label">Our Approach</div>
    <h2>AI-powered <span class="teal">advisory platform</span></h2>
    <div class="divider"></div>
    <p style="max-width:700px;margin-bottom:30px;">Our platform combines senior advisory expertise with AI automation — delivering faster, more thorough analysis while maintaining the professional rigor expected by underwriters and investors.</p>
    <div class="g3" style="gap:16px;">
      <div class="card" style="text-align:center;padding:28px;">
        <div style="font-size:48px;margin-bottom:12px;">1</div>
        <h3 style="font-size:15px;margin-bottom:8px;">Upload & Extract</h3>
        <p style="font-size:12px;">Drop in your documents — AI auto-extracts company data, financials, and key information</p>
      </div>
      <div class="card" style="text-align:center;padding:28px;">
        <div style="font-size:48px;margin-bottom:12px;">2</div>
        <h3 style="font-size:15px;margin-bottom:8px;">Analyze & Score</h3>
        <p style="font-size:12px;">AI performs industry research, financial analysis, risk assessment, and valuation modeling</p>
      </div>
      <div class="card" style="text-align:center;padding:28px;">
        <div style="font-size:48px;margin-bottom:12px;">3</div>
        <h3 style="font-size:15px;margin-bottom:8px;">Generate & Deliver</h3>
        <p style="font-size:12px;">Professional reports and decks generated automatically, reviewed by senior advisors</p>
      </div>
    </div>
  </div>
  {f}
</div>

<!-- SLIDE 6: NEXT STEPS -->
<div class="slide">
  <div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
  <div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
    <div>
      <div class="label">Next Steps</div>
      <h1 style="margin-bottom:20px;">Ready to <span class="teal">get started</span>?</h1>
      <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
      <p style="max-width:500px;margin:0 auto 40px;font-size:16px;">Let's schedule a kick-off meeting to align on scope, timeline, and deliverables for {name}.</p>
      <div class="g3" style="max-width:600px;margin:0 auto;gap:16px;">
        <div class="card" style="text-align:center;padding:20px;">
          <h3 style="font-size:14px;">Step 1</h3>
          <p style="font-size:12px;margin-top:6px;">Sign engagement letter</p>
        </div>
        <div class="card" style="text-align:center;padding:20px;">
          <h3 style="font-size:14px;">Step 2</h3>
          <p style="font-size:12px;margin-top:6px;">Upload company materials</p>
        </div>
        <div class="card" style="text-align:center;padding:20px;">
          <h3 style="font-size:14px;">Step 3</h3>
          <p style="font-size:12px;margin-top:6px;">Receive first deliverables</p>
        </div>
      </div>
      <p style="font-size:12px;color:#475569;margin-top:50px;">ORIONMANO ASSURANCE SERVICES &middot; Strictly Private and Confidential</p>
    </div>
  </div>
</div>

</body></html>"""


def build_kickoff_deck(data: dict) -> str:
    name = _esc(data["name"])
    industry = _esc(data["industry"])
    country = _esc(data["country"])
    f = _footer("Kick-off Meeting Deck")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="slide">
  <div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
  <div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
    <div>
      <div style="font-size:16px;letter-spacing:10px;color:#14B8A6;font-weight:600;margin-bottom:36px;">ORIONMANO</div>
      <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
      <h1>{name}</h1>
      <p style="font-size:17px;">Engagement Kick-off</p>
      <p style="font-size:12px;color:#475569;margin-top:50px;">Strictly Private and Confidential</p>
    </div>
  </div>
</div>
<div class="slide" style="padding:56px 70px;">
  <div class="rel">
    <div class="label">Scope of Services</div>
    <h2>Engagement <span class="teal">Overview</span></h2>
    <div class="divider"></div>
    <div class="g2" style="gap:40px;margin-top:20px;">
      <div>
        {_bullets(["Industry Expert Report", "Due Diligence Report", "Valuation Report", "Investor Materials"])}
      </div>
      <div>
        <div class="card"><h3 style="font-size:14px;margin-bottom:6px;">Company</h3><p style="font-size:13px;color:#CBD5E1;">{name}</p><p style="font-size:12px;">{industry} &middot; {country}</p></div>
      </div>
    </div>
  </div>
  {f}
</div>
<div class="slide" style="padding:56px 70px;">
  <div class="rel">
    <div class="label">Timeline</div>
    <h2>Engagement <span class="teal">Phases</span></h2>
    <div class="divider"></div>
    <div class="g2" style="gap:16px;margin-top:20px;">
      <div class="card" style="text-align:center;padding:24px;"><div class="stat-num" style="font-size:32px;">1-2</div><div class="stat-label">Weeks</div><h3 style="font-size:13px;margin-top:12px;">Data Collection</h3></div>
      <div class="card" style="text-align:center;padding:24px;"><div class="stat-num" style="font-size:32px;">3-6</div><div class="stat-label">Weeks</div><h3 style="font-size:13px;margin-top:12px;">Analysis</h3></div>
      <div class="card" style="text-align:center;padding:24px;"><div class="stat-num" style="font-size:32px;">5-8</div><div class="stat-label">Weeks</div><h3 style="font-size:13px;margin-top:12px;">Drafting</h3></div>
      <div class="card" style="text-align:center;padding:24px;"><div class="stat-num" style="font-size:32px;">8-10</div><div class="stat-label">Weeks</div><h3 style="font-size:13px;margin-top:12px;">Finalization</h3></div>
    </div>
  </div>
  {f}
</div>
<div class="slide">
  <div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
  <div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
    <div>
      <div class="label">Next Steps</div>
      <h1>Let's <span class="teal">begin</span></h1>
      <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
      <div class="g3" style="max-width:600px;margin:0 auto;gap:16px;">
        <div class="card" style="text-align:center;padding:20px;"><h3 style="font-size:14px;">Upload Documents</h3></div>
        <div class="card" style="text-align:center;padding:20px;"><h3 style="font-size:14px;">Schedule Interviews</h3></div>
        <div class="card" style="text-align:center;padding:20px;"><h3 style="font-size:14px;">Confirm Timeline</h3></div>
      </div>
    </div>
  </div>
</div>
</body></html>"""


def build_teaser(data: dict) -> str:
    name = _esc(data["name"])
    industry = _esc(data["industry"])
    country = _esc(data["country"])
    description = _esc(data["description"]) or f"A {industry.lower()} company based in {country}."
    f = _footer("Company Teaser")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="slide">
  <div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
  <div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
    <div>
      <div style="font-size:16px;letter-spacing:10px;color:#14B8A6;font-weight:600;margin-bottom:20px;">ORIONMANO</div>
      <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
      <h1 style="font-size:48px;">{name}</h1>
      <p style="font-size:18px;margin-top:8px;">{industry} &middot; {country}</p>
      <p style="font-size:14px;color:#475569;margin-top:50px;">Investment Teaser &middot; Strictly Private and Confidential</p>
    </div>
  </div>
</div>
<div class="slide" style="padding:56px 70px;">
  <div class="rel">
    <div class="label">Company Overview</div>
    <h2>{name}</h2>
    <div class="divider"></div>
    <div class="g2" style="gap:50px;margin-top:16px;">
      <div>
        <p style="margin-bottom:20px;">{description}</p>
        <h3 style="margin-top:24px;margin-bottom:12px;">Investment Highlights</h3>
        {_bullets(["Established market position in " + _esc(data["industry"]), "Strong growth trajectory", "Experienced management team", "Clear path to capital markets"])}
      </div>
      <div>
        <div class="card" style="text-align:center;padding:24px;margin-bottom:16px;"><div class="stat-num" style="font-size:36px;">{_esc(data["engagement_type"])}</div><div class="stat-label">Transaction Type</div></div>
        {f'<div class="card" style="text-align:center;padding:24px;"><div class="stat-num" style="font-size:36px;">{_esc(data["target_exchange"])}</div><div class="stat-label">Target Exchange</div></div>' if data["target_exchange"] else ''}
      </div>
    </div>
  </div>
  {f}
</div>
</body></html>"""


def build_company_deck(data: dict) -> str:
    name = _esc(data["name"])
    industry = _esc(data["industry"])
    country = _esc(data["country"])
    description = _esc(data["description"]) or f"A {industry.lower()} company based in {country}."
    f = _footer("Investor Presentation")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="slide">
  <div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
  <div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
    <div>
      <div style="font-size:16px;letter-spacing:10px;color:#14B8A6;font-weight:600;margin-bottom:36px;">{name.upper()}</div>
      <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
      <h1 style="font-size:40px;">Investor Presentation</h1>
      <p style="font-size:16px;margin-top:8px;">{industry} &middot; {country}</p>
      <p style="font-size:12px;color:#475569;margin-top:50px;">Prepared by Orionmano Assurance Services</p>
    </div>
  </div>
</div>
<div class="slide" style="padding:56px 70px;">
  <div class="rel">
    <div class="label">Investment Thesis</div>
    <h2>Why <span class="teal">{name}</span></h2>
    <div class="divider"></div>
    <div class="g2" style="gap:40px;margin-top:20px;">
      <div>
        <p style="margin-bottom:20px;">{description}</p>
        {_bullets(["Proven business model in " + _esc(data["industry"]), "Strong revenue growth trajectory", "Experienced leadership team", "Large addressable market", "Clear competitive advantages"])}
      </div>
      <div class="g2" style="gap:16px;">
        <div class="card" style="text-align:center;padding:20px;"><div class="stat-num" style="font-size:24px;">{_esc(data["industry"])[:12]}</div><div class="stat-label">Industry</div></div>
        <div class="card" style="text-align:center;padding:20px;"><div class="stat-num" style="font-size:24px;">{country[:8]}</div><div class="stat-label">Market</div></div>
        <div class="card" style="text-align:center;padding:20px;"><div class="stat-num" style="font-size:24px;">{_esc(data["engagement_type"])[:8]}</div><div class="stat-label">Transaction</div></div>
        <div class="card-teal" style="text-align:center;padding:20px;"><div class="stat-num" style="font-size:24px;">Growth</div><div class="stat-label">Stage</div></div>
      </div>
    </div>
  </div>
  {f}
</div>
<div class="slide" style="padding:56px 70px;">
  <div class="rel">
    <div class="label">Business Model</div>
    <h2>How we <span class="teal">create value</span></h2>
    <div class="divider"></div>
    <div class="g3" style="gap:16px;margin-top:24px;">
      <div class="card" style="text-align:center;padding:28px;"><div class="icon-box" style="margin:0 auto 12px;">&#128200;</div><h3 style="font-size:15px;">Revenue Model</h3><p style="font-size:12px;margin-top:6px;">Diversified revenue streams</p></div>
      <div class="card" style="text-align:center;padding:28px;"><div class="icon-box" style="margin:0 auto 12px;">&#127919;</div><h3 style="font-size:15px;">Market Position</h3><p style="font-size:12px;margin-top:6px;">Established in {_esc(data["industry"])}</p></div>
      <div class="card" style="text-align:center;padding:28px;"><div class="icon-box" style="margin:0 auto 12px;">&#128640;</div><h3 style="font-size:15px;">Growth Strategy</h3><p style="font-size:12px;margin-top:6px;">Multiple expansion vectors</p></div>
    </div>
  </div>
  {f}
</div>
<div class="slide">
  <div class="glow glow-t" style="width:500px;height:500px;top:-100px;right:-100px;opacity:0.15;"></div>
  <div class="rel" style="display:flex;align-items:center;justify-content:center;height:100%;text-align:center;">
    <div>
      <h1 style="margin-bottom:20px;">{name}</h1>
      <div class="divider" style="width:60px;margin:0 auto 28px;"></div>
      <p style="font-size:16px;">For further information, please contact Orionmano Assurance Services</p>
      <p style="font-size:12px;color:#475569;margin-top:50px;">Strictly Private and Confidential</p>
    </div>
  </div>
</div>
</body></html>"""


async def generate_deck_pdf(db: AsyncSession, company_id: UUID, deck_type: str) -> bytes:
    """Generate a branded PDF deck. Returns raw PDF bytes."""
    data = await _get_company_data(db, company_id)

    builders = {
        "sales_deck": build_sales_deck,
        "kickoff_deck": build_kickoff_deck,
        "teaser": build_teaser,
        "company_deck": build_company_deck,
    }

    builder = builders.get(deck_type)
    if not builder:
        raise ValueError(f"Unknown deck type: {deck_type}")

    html_content = builder(data)

    from weasyprint import HTML
    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes
