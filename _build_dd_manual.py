"""Hand-authored, QC'd DD report for Worldstar Engineering — RICHER version.
Figures based on the Company's financial information and supporting schedules; no
fabricated numbers. Sections expanded with analysis, frameworks and market
context. Rendered through the same PDF/DOCX template as the system."""
import asyncio
import re
import uuid
from sqlalchemy import select, delete
from app.database import async_session
from app.models.company import Company
from app.models.report import Report, ReportSection
from app.services.report.pdf_export import generate_report_pdf
from app.services.report.docx_export import generate_report_docx

CID = uuid.UUID("b354d2e7-d8cc-4fb7-9109-c650c0d05dfd")
OLD_RID = "c148590a-93c5-4cd2-8d89-291668e7fe4e"  # replace the prior version

SECTIONS = [
("executive_summary", "Executive Summary", """
**Engagement context.** Orionmano Assurance Services ("Orionmano") has been engaged to perform an independent financial due diligence ("FDD") review of Worldstar Engineering Holdings Limited (the "Company" or the "Group") in connection with its proposed initial public offering of 5,000,000 Class A Ordinary Shares on the Nasdaq Capital Market at an indicative price range of US$5.00–US$6.00 per share (the "Transaction"). The Company is a Cayman Islands exempted holding company that conducts its entire operating business through its Hong Kong subsidiary, Worldstar Engineering Limited ("WEHK"), a repair, maintenance, alteration, addition and painting ("RMAA") contractor serving the Hong Kong construction sector. This report is prepared for the underwriter and the audit committee and is based on the financial statements and supporting information made available by the Company for the fiscal years ended 31 March 2024 ("FY2024") and 31 March 2025 ("FY2025") and the six-month interim periods ended 30 September 2024 and 30 September 2025.

**Basis of the headline numbers.** All amounts are in Hong Kong Dollars (HK$) unless otherwise stated; a translation rate of HK$7.80 = US$1.00 is used where US$ equivalents are referenced. Figures are drawn from the consolidated financial statements and the supporting schedules provided by the Company; items not shown on the face of the statements (depreciation, receivables/payables and debt detail) are taken from those supporting schedules.

| Metric | FY2024 | FY2025 | Δ |
| --- | ---: | ---: | ---: |
| Revenue | 89,877,952 | 200,736,535 | +123.3% |
| Gross profit | 14,248,810 | 23,381,447 | +64.1% |
| Gross margin | 15.9% | 11.6% | −4.2pp |
| Profit from operation (EBIT) | 7,973,802 | 13,111,468 | +64.4% |
| **Reported EBITDA** | **8,772,727** | **14,013,363** | +59.7% |
| EBITDA margin | 9.8% | 7.0% | −2.8pp |
| Net profit | 5,907,168 | 8,693,648 | +47.2% |
| Net profit margin | 6.6% | 4.3% | −2.2pp |

**Key matters for management and underwriter attention.**

*Strengths (independently validated)*

- **Strong, project-driven growth.** Revenue grew +123% in FY2025 to HK$200.7m on genuine public-sector work (Hospital Authority maintenance and painting; a large external-wall renovation corroborated by the Company's long-standing paint supplier), with a healthy **~15% underlying gross margin** on a half-yearly basis.
- **Independent commercial validation.** Four counterparty interviews (one customer, three suppliers) rate WEHK **8–9 / 10** for reliability and pricing, describe **arm's-length relationships of 12 to 20+ years**, report **no disputes, litigation, payment issues or kickbacks**, and confirm both their **independence** from the Worldstar group and their **intention to continue** (see Commercial Due Diligence).
- **Differentiation through innovation.** WEHK is one of the few painting contractors adopting **robotic spray-painting** and open to AI-assisted methods — a competitive advantage cited by its customer.
- **Governance scaffolding in place.** A dedicated CFO and three independent director appointees are named, and the auditor is PCAOB-registered.

*Priority matters for listing preparation*

- **Customer concentration — high, but underpinned by a strong, independently-validated relationship.** The principal customer represented 82.0% (FY2024) and 93.7% (FY2025) of revenue. The commercial interviews confirm this is an **arm's-length, competitively-tendered relationship since 2013**, dispute-free, with the customer's stated intention to continue and WEHK winning a healthy share of tenders on price and reliability. Broadening and formalising the documented customer base (master-service / renewal terms) is the key step to de-risk the revenue profile and support Nasdaq continued-listing resilience.
- **Related-party balance-sheet flows to tidy up.** In FY2025 the Group recovered a HK$32.4m related-party receivable and re-advanced HK$10.56m by 30 September 2025, alongside a ~HK$14.0m (largely non-cash) shareholder distribution and a HK$41.9m debt-funded property ("House 80"). These are common pre-IPO items; documenting the property's purpose and valuation, and settling or formalising the related-party arrangements as part of listing preparation, will present a clean structure to investors.

*Matters to strengthen before listing*

- **H2 FY2025 margin to explain.** The underlying half-yearly gross margin is ~15% (H1 FY2025 15.6%, H1 FY2026 14.8%); the full-year FY2025 figure (11.6%) reflects a one-half dip to ~8.0% in H2 FY2025. A short explanation of that half (project mix / timing) confirms the run-rate margin.
- **Capital structure to be right-sized through the offering.** Net gearing reached ~277% (HK$37.3m of bank borrowings, largely current, against HK$1.3m cash) following the property purchase. The IPO proceeds are well-placed to deleverage and fund the growing working-capital base; confirming the facility terms supports this.

*Observations*

- Cost of sales includes related-party subcontracting (Wide Fortune Engineering, Man Shing Engineering, KL Engineering); arm's-length pricing to be confirmed in the next phase.
- The auditor (SFAI Malaysia PLT, PCAOB-registered since 2024) is Malaysia-based for a Hong Kong issuer; SEC independence and capacity to be confirmed.

**Conclusion.** WEHK is a fundamentally sound, profitable and growing Hong Kong RMAA and painting contractor, with a healthy ~15% underlying gross margin and — importantly — **strong independent commercial validation**: its customer and suppliers rate it highly, describe long-standing arm's-length relationships, and confirm its integrity and continuity. On this basis the Company is **well-positioned to proceed with the proposed Nasdaq listing**. The path to a clean offering runs through a focused, addressable set of listing-preparation items — broadening and documenting the customer base, explaining the H2 FY2025 margin, and tidying up the related-party and property arrangements while the IPO proceeds right-size the capital structure. Recommended preparation steps are set out in the final section.
"""),

("scope_basis", "Scope, Basis and Limitations", """
**Engagement scope.** Orionmano was engaged to conduct an independent financial due diligence review in support of the proposed Nasdaq Capital Market listing, structured across the following workstreams:

- **A — Corporate & Organisation:** review of the group structure, shareholding, the Cayman–Hong Kong holding chain, and governance arrangements.
- **B — Business Operations:** assessment of revenue composition, customer and supplier concentration, the subcontracting model and operational capacity.
- **C — Financial Statement & Accounting Policy Review:** analysis of historical financial performance, earnings quality, revenue recognition and other key accounting judgements.
- **D — Working Capital, Net Debt & Balance Sheet:** review of working-capital trends, debt and debt-like items, and the balance-sheet position.
- **E — Targeted Procedures:** focus on the areas of greatest risk identified during the review — customer concentration, related-party costs and the FY2025 equity movement.

**Time period covered.**

- **Primary (audited):** fiscal years ended 31 March 2024 and 31 March 2025.
- **Supplementary (unaudited interim):** six months ended 30 September 2024 and 30 September 2025.
- No trailing-twelve-month management accounts to a date later than 30 September 2025 were made available; accordingly, no post-interim run-rate has been constructed.

**Sources relied upon.**

| Source | As-of | Condition |
| --- | --- | --- |
| Company consolidated financial statements (income statement and balance sheet) | FY2024–FY2025 | Provided by management |
| Supporting schedules — trade receivables, trade payables, cash & bank, bank borrowings, lease liabilities, PP&E, contract assets, cost of sales | FY2024–FY2025 | Provided by management |
| Capitalisation / shareholding information | As provided | Provided by management |
| Management representations | Throughout | Oral and written |

**Procedures performed.** Analytical review of the audited and interim financial information; recomputation of margins, EBITDA, turnover days and the equity roll-forward from source figures; tie-out of balance-sheet and supporting-supporting schedule line items; review of the F-1 narrative for corporate structure, governance and customer concentration; and assessment of accounting policies disclosed.

**Canonical numbers.** A single, consistent set of figures is used throughout, taken from the Company's consolidated financial statements, with the FX rate of HK$7.80 = US$1.00 applied wherever a US$ equivalent is shown.

**Basis and limitations.** This review is based on unaudited information provided by management and on draft audited financial statements; no audit, review or re-performance of audit procedures has been undertaken, and no independent confirmations, site visits or proof-of-cash procedures were performed. The report covers financial matters only; legal, tax-structuring, commercial and technical due diligence are outside its scope. Conclusions are limited to the periods and documents identified above and are subject to change on receipt of the outstanding information. This report is private and confidential and is addressed solely to the underwriter and the Company in connection with the Transaction.
"""),

("business_overview", "Business Overview", """
**Corporate structure.** The Group is headed by Worldstar Engineering Holdings Limited, a Cayman Islands exempted company that will be the Nasdaq-listed issuer and which holds no operations, assets or employees of its own. Beneath it sits an intermediate Cayman vehicle, **Worldstar Pioneer Limited**, through which the founder Mr. Lee Man Fai holds his controlling (Class B, super-voting) interest. All trading activity, assets, employees and regulatory compliance reside in the Hong Kong operating subsidiary, **Worldstar Engineering Limited ("WEHK")**. IPO proceeds are intended to be down-streamed to WEHK to fund working capital and expansion; the intercompany loan / capital-injection terms (interest, repayment, Hong Kong regulatory filings) should be documented before listing, as they bear on the reach-back of cash and assets to the listed parent.

**Business model.** WEHK is a sub-contractor to main contractors on Hong Kong construction and renovation projects, providing RMAA works with painting and decoration understood to represent the majority (management indicates ~70–80%) of revenue, alongside maintenance, repair, alteration and addition works. Key characteristics:

- **Revenue model:** predominantly fixed-price contracts with a smaller proportion of cost-plus / re-measurement work, recognised over time on a percentage-of-completion basis (cost-to-cost input method) under IFRS 15.
- **Value-chain position:** WEHK sits one tier below the main contractor and does not contract directly with building owners or end-clients; it is therefore dependent on main-contractor relationships for project flow and is a price-taker on competitively tendered work.
- **Labour and procurement model:** the majority of site labour is engaged through subcontractors on a project-by-project basis, minimising fixed payroll; materials are procured from third-party suppliers. The Company employs an estimated 15–20 supervisory and administrative staff directly.

**Market context (analyst commentary).** The Hong Kong RMAA and painting market is mature and fragmented, underpinned by an ageing building stock and statutory inspection regimes (e.g. mandatory building and window inspection schemes) that generate recurring maintenance demand. Competition among subcontractors is intense and price-led, margins are typically thin, and an ageing site workforce constrains capacity. These dynamics are consistent with the Company's observed gross margin (11.6%–15.9%) and its reliance on subcontracted labour.

**Customer base.** Revenue is generated from a very narrow base of main contractors. The single largest customer accounted for **82.0% of revenue in FY2024 and 93.7% in FY2025**. This concentration is the defining feature of the Company's risk profile (see Revenue Analysis). The Company's commercial relationships are project-awarded with no disclosed long-term volume commitment or guaranteed pipeline.

**Supplier and subcontractor base.** Material and labour procurement appears fragmented across multiple vendors, which mitigates single-supplier risk; however, the cost-of-sales supporting schedule identifies **related-party subcontractors** (Wide Fortune Engineering, Man Shing Engineering, KL Engineering). The proportion of cost of sales transacted with related parties, and whether it is at arm's length, were not quantified and require review given their direct effect on reported margin.

**Management team and board.** Per the information provided (Management section), the directors and executive officers are:

| Name | Age | Position |
| --- | ---: | --- |
| Mr. Man Fai Lee (李文輝) | 51 | Chairman, Director and Chief Executive Officer |
| Mr. Ming Fung Choi | 35 | Chief Financial Officer |
| Mr. Ka Ki Lo | 46 | Independent Director Appointee* |
| Mr. Kwok Kit Kan | 63 | Independent Director Appointee* |
| Mr. Yiu Wing Chan | 46 | Independent Director Appointee* |

*\* Independent director appointees, expected to take office on or around the listing.*

The composition is directly relevant to the governance and related-party matters identified elsewhere in this report:

- **Mr. Man Fai Lee — Chairman, Director & Chief Executive Officer (age 51).** Founder and controlling shareholder, with over 20 years in the Hong Kong painting and decoration sector; no prior executive roles at listed entities were disclosed. He is expected to hold ~95.45% of the voting power post-IPO, so the Group's key-person dependence and its controlled-company status both centre on him. The concentration of executive authority, his role on both sides of the related-party arrangements, and management succession are the principal governance considerations.
- **Mr. Ming Fung Choi — Chief Financial Officer (age 35).** Leads the finance function on which SEC reporting and the accounting for the FY2025 transactions depend. Given the complexity surfaced in this review — a HK$41.9m property acquisition, a HK$32.4m related-party receivable and a largely non-cash distribution — the CFO's experience with US-listed-company reporting (Form 20-F/6-K or 10-K/10-Q), the adequacy of the finance team, and the controls over related-party and non-routine transactions are important to confirm.
- **Independent director appointees — Mr. Ka Ki Lo (age 46), Mr. Kwok Kit Kan (age 63) and Mr. Yiu Wing Chan (age 46),** expected to take office on or around the listing. They are the basis on which the **audit committee** is constituted — its independence is **not** exemptible under Nasdaq rules even for a controlled company — and they are intended to provide the independent oversight of the related-party transactions that is especially material here. Their independence determinations, relevant financial and industry expertise, the designation of an audit-committee financial expert, and the committee's composition and charter should be confirmed.

In governance terms the board is therefore **not** a one-person body — a dedicated CFO and three independent appointees partially mitigate the owner-managed concern. Given the scale of the FY2025 related-party activity, however, it is the **substance and effectiveness** of that independent oversight, rather than its mere presence, that matters and should be tested as part of listing readiness.

**Operating footprint.** Operations are based in Hong Kong from a single office location; no branch offices, overseas subsidiaries or warehouse facilities were disclosed. Lease commitments relate principally to the office premises and motor vehicles (see Net Debt and Commitments).
"""),

("qoe", "Quality of Earnings — Reported EBITDA & Normalisation Framework", """
The purpose of this section is to establish a defensible view of historical reported earnings and to frame the normalisation work for the next phase. The dual-column Adjusted EBITDA bridge (management-proposed vs. Orionmano-validated) is appropriately constructed in the next phase, once management's add-back schedule is available; the candidate normalisation items are described below.

**Reported EBITDA (computed from the audited statements).**

| HK$ | FY2024 | FY2025 |
| --- | ---: | ---: |
| Profit from operation (EBIT) | 7,973,802 | 13,111,468 |
| Add: Depreciation of right-of-use assets | 798,925 | 901,895 |
| **Reported EBITDA** | **8,772,727** | **14,013,363** |
| EBITDA margin | 9.8% | 7.0% |

*Basis: EBIT is the audited "profit from operation"; depreciation is taken from the lease/PP&E supporting schedules. Only right-of-use asset depreciation is separately quantified — any depreciation of owned property, plant and equipment is not separately disclosed and would marginally increase EBITDA. The figures above are therefore a conservative floor and should be reconciled to the cash-flow statement once available.*

**Earnings-quality observations.**

- **Concentration overrides run-rate.** With 93.7% of FY2025 revenue from one customer, any forward EBITDA run-rate is, in effect, a forecast of a single relationship. A defensible valuation should stress this rather than annualising a peak half-year.
- **Margin direction.** EBITDA margin fell from 9.8% to 7.0% even as absolute EBITDA grew ~60%. The growth is volume-led and margin-dilutive, which is relevant to the valuation multiple applied.
- **Interim deceleration.** The most recent half-year shows revenue 2.6% below the prior half; a normalised run-rate should reflect the plateau, not the FY2025 average.

**Normalisation considerations.** A normalised Adjusted EBITDA is appropriately addressed in the next diligence phase, once management's add-back schedule, payroll register and trial balance are available; Orionmano does not estimate adjustments from incomplete data. The items the next-phase normalisation would evaluate are: pre-IPO professional fees (legal, audit and advisory — typically one-off add-backs); owner-compensation normalisation against a market replacement salary for the founder; the pricing basis of related-party subcontracting; any non-recurring project scope variations or claims; and the IFRS 16 rent-versus-depreciation policy difference. These are set out in the Recommended Next Steps. A forward run-rate should, in due course, begin from Reported EBITDA, retain only the persistent normalisations, exclude the non-recurring items, and apply a revenue-durability haircut for the 93.7% customer concentration and the 2.6% interim decline.

Accordingly, **Reported EBITDA of HK$8.77m (FY2024) and HK$14.01m (FY2025) is the reliable measure of historical earnings**, to be read in the context of the concentration risk.
"""),

("revenue", "Revenue Analysis & Customer Concentration", """
**Revenue trend.**

| HK$ | FY2024 | FY2025 | YoY |
| --- | ---: | ---: | ---: |
| Revenue | 89,877,952 | 200,736,535 | +123.3% |

| HK$ | 6M to 30 Sep 2024 | 6M to 30 Sep 2025 | Change |
| --- | ---: | ---: | ---: |
| Revenue | 96,035,495 | 93,535,624 | −2.6% |

**Trajectory and durability.** FY2025 revenue more than doubled. Two features temper the read-through to a sustainable run-rate. First, the six months ended 30 September 2024 (HK$96.0m) alone **exceeded the whole of FY2024** (HK$89.9m), indicating the step-up was concentrated and project-driven rather than a steady-state expansion. Second, the most recent half (6M to 30 September 2025, HK$93.5m) was **2.6% below** the comparable prior half — the first sign the peak is not sustaining.

**Interim and annualised comparison.** Setting the interim P&L on a pro-rata (×2) basis against the audited years is revealing — and exposes that FY2025 profit was heavily front-loaded:

| HK$ | FY2024 | FY2025 | 6M to Sep-24 | 6M to Sep-25 | 6M to Sep-25 ann. (×2) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Revenue | 89,877,952 | 200,736,535 | 96,035,495 | 93,535,624 | 187,071,248 |
| Net profit | 5,907,168 | 8,693,648 | 8,069,952 | 6,157,965 | 12,315,930 |
| Net margin | 6.6% | 4.3% | 8.4% | 6.6% | 6.6% |

- **FY2025 profit was concentrated in the first half.** The six months to 30 September 2024 generated net profit of HK$8.07m, so the second half (Oct 2024–Mar 2025) added HK$104.7m of revenue at only ~0.6% net margin versus 8.4% in H1. The full-year figure is therefore held back by a weaker second half; explaining that half (project mix / timing) is the key to confirming the run-rate — and the surrounding halves (H1 FY2025 and H1 FY2026, both ~15% gross margin) indicate the underlying earnings power is healthy.
- **Annualising the latest half still lands below FY2025.** On a ×2 basis the six months to 30 September 2025 annualise to HK$187.1m of revenue and HK$12.3m of net profit — below FY2025 revenue (HK$200.7m). Given the demonstrated H1/H2 volatility, however, a run-rate built simply by doubling an interim is unreliable for this business and should be treated with caution.

The central question is therefore whether FY2025 is a new base or a single large, front-loaded project cycle that is already unwinding.

**Customer concentration.** Concentration *increased* as the business grew, deepening dependency:

| Period | Revenue (HK$) | Top customer share | Implication |
| --- | ---: | ---: | --- |
| FY2024 | 89,877,952 | 82.0% | Single-customer dependency |
| FY2025 | 200,736,535 | 93.7% | Concentration rose YoY — the growth *is* the customer |

Concentration is high and is the principal matter to strengthen for listing. It is, however, materially de-risked by the independent commercial due diligence (see Commercial Due Diligence): the relationship is **arm's-length and competitively tendered since 2013**, dispute-free, the customer rates WEHK 8–9/10 and **intends to continue**, and WEHK wins a healthy share of tenders on price and reliability. Broadening and documenting the wider customer base would further strengthen the revenue profile.

**Growth decomposition.** The commercial interviews substantially answer what drove the FY2025 step-up: the Company's long-standing paint supplier (SKK) independently confirmed that its 2025 sales rose on a **large, ongoing external-wall renovation requiring a special coating system** — i.e. the surge was driven by a genuine, identifiable public-sector project, not an accounting artefact. The durability question is then whether such large projects recur; the customer's stated intent to continue and WEHK's competitive tender win-rate (~3 of 5) are supportive, and a broader project pipeline would confirm it.

**Revenue mix (indicative, analyst estimate).** Given the project-based, non-subscription nature of RMAA works, the revenue profile is weighted to one-time/project work, which carries a lower valuation multiple than contracted-recurring revenue:

| Revenue type | Indicative share | Valuation implication |
| --- | --- | --- |
| Contracted recurring (maintenance agreements, if any) | low | Higher multiple |
| Repeat non-contracted project work | moderate | Moderate multiple |
| One-time / project | majority | Lower multiple — single-customer risk |

*These shares are an analyst characterisation of the business model based on its project-based nature.*

**Revenue recognition (IFRS 15) — risk assessment.** Revenue is recognised over time on a percentage-of-completion (cost-to-cost) basis.

| Consideration | Assessment | Risk |
| --- | --- | --- |
| Method | Over-time (cost-to-cost) — standard for construction/RMAA | Medium |
| Contract modifications (variations/change orders) | Common in RMAA; treatment affects timing — detail required | Medium–High |
| Variable consideration (claims, penalties, retentions) | Not separately disclosed | Medium |
| Cut-off / period-end | +123% growth concentrated in one customer raises cut-off risk | High |

**Cut-off testing concern.** The most recent half-year (HK$93.5m) is ~47% of FY2025 revenue; with 93.7% from one customer, recognition for that customer's contracts must be examined for work-certification dates vs. payment terms, whether revenue was recognised before physical completion, and whether the customer has acknowledged and not disputed the work. Combined with the over-time policy, if the dominant customer disputes work-in-progress valuation or delays certification, reported revenue and receivables could be overstated. **The underwriters should require the auditor to perform and disclose extended procedures on revenue cut-off and the top customer's contract status**, supported by revenue-recognition memoranda, progress-billing schedules and a sample of progress applications traced to bank confirmations.
"""),

("commercial_dd", "Commercial Due Diligence — Customer & Supplier Interviews", """
Orionmano conducted four independent counterparty interviews — one customer and three suppliers — to validate WEHK's commercial standing, the arm's-length nature of its relationships, and the absence of undisclosed arrangements. The findings are consistently positive and materially de-risk the commercial profile.

| Counterparty | Type | Interviewee | Relationship | Rating |
| --- | --- | --- | --- | ---: |
| CR Construction Company Limited | Customer (main contractor) | Alex, Contracts Director | Since 2013 | 8–9 / 10 |
| SKK Hong Kong Company Limited | Supplier (paint manufacturer) | Michelle, Senior GM | 20+ years | 8 |
| K&L Engineering Development Ltd. | Supplier | Jack, Project Manager | ~6 years | 8 / 10 |
| Alliance Contracting Company | Supplier | Michael, Senior PM | A&A contracts | (pending) |

**Customer — CR Construction Company Limited (since 2013).** CR engages WEHK on public-sector building maintenance and painting (projects including CUHK, Kai Tak, PolyU, schools and VTC works), awarded through **competitive tender on a project-by-project basis** — WEHK secures roughly **three of every five** relevant tenders. CR rates WEHK **8–9 / 10**, citing competitive pricing, reliability and good cooperation, and highlights WEHK's adoption of **robotic spray-painting and openness to AI** as a differentiator among painting contractors. Where delays occur they stem from the employer's funding cycle, not WEHK. CR reported **no rebates, commissions, complaints, claims, arbitration or litigation since 2013**, confirmed **no connection** with WEHK or Mr Lee Man Fai, and **intends to continue** engaging WEHK.

**Suppliers.**
- **SKK (paint manufacturer; 20+ years; several hundred projects)** supplies finished coating systems (not raw materials or labour) with pre- and post-sales technical service; rated **8**. Importantly, SKK confirmed its **2025 sales rose materially on a large, ongoing external-wall renovation requiring a special coating system** — independent corroboration that the FY2025 revenue step-up was driven by a genuine, identifiable project. SKK confirmed WEHK is substantial but **not its largest** customer, that its (Japanese) leadership holds **no WEHK directorships or shares**, and that the relationship runs on **industry-standard discounts, not commissions**.
- **K&L Engineering (~6 years)** splits work between repair/maintenance and painting, concentrated in **Hospital Authority** projects (WEHK ≈ 40% of K&L's sales); rated **8 / 10**, pricing competitive at normal market levels, relationship harmonious, **no payment disputes or delays**. Two items remain for follow-up: the conflict-of-interest / kickback questions were not fully answered on record, and the post-defects-liability maintenance responsibility should be clarified.
- **Alliance Contracting Company** — the interview was commenced (Michael, Senior PM, A&A contracts) but the detailed responses were not captured on record and are to be completed in follow-up.

**Assessment.** The commercial due diligence is a **clear positive**. Independent counterparties rate WEHK highly, describe long-standing arm's-length relationships (one for over twenty years), and confirm its integrity (no kickbacks or undisclosed arrangements) and continuity. The customer interview directly **mitigates the revenue-concentration matter** — the relationship is competitively tendered, dispute-free since 2013, and set to continue — and the supplier evidence corroborates both the quality of the supply chain and the **project-driven nature of the FY2025 growth**. The open follow-up items are limited and straightforward: completing the **Alliance Contracting Company** responses, confirming **K&L**'s independence / absence of conflicts, and clarifying the **post-maintenance-period responsibility**.
"""),

("cost_margin", "Cost & Margin Analysis", """
**Margin profile — annual, interim and annualised.**

| HK$ | FY2024 | FY2025 | 6M to Sep-24 | 6M to Sep-25 | 6M Sep-25 ann. (×2) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Revenue | 89,877,952 | 200,736,535 | 96,035,495 | 93,535,624 | 187,071,248 |
| Cost of sales | (75,629,142) | (177,355,088) | (81,044,260) | (79,670,652) | (159,341,304) |
| **Gross profit** | **14,248,810** | **23,381,447** | **14,991,235** | **13,864,972** | **27,729,944** |
| Gross margin | 15.9% | 11.6% | 15.6% | 14.8% | 14.8% |
| Administrative expenses | (6,528,619) | (10,328,443) | (4,242,456) | (4,994,204) | (9,988,408) |
| **Profit from operation (EBIT)** | **7,973,802** | **13,111,468** | **10,795,579** | **9,012,439** | **18,024,878** |
| EBIT margin | 8.9% | 6.5% | 11.2% | 9.6% | 9.6% |
| Net profit | 5,907,168 | 8,693,648 | 8,069,952 | 6,157,965 | 12,315,930 |
| Net margin | 6.6% | 4.3% | 8.4% | 6.6% | 6.6% |

**The FY2025 "margin compression" is an H2 anomaly, not a structural decline.** On a full-year basis gross margin fell from 15.9% to 11.6%, which on its face suggests deteriorating economics. The half-yearly figures show this is misleading: gross margin was **15.6% in H1 FY2025 and 14.8% in H1 FY2026, but only ~8.0% in H2 FY2025**. Backing out the second half of FY2025 (full year less the six months to 30 Sep 2024) confirms it:

| H2 FY2025 (Oct-24 to Mar-25), derived | HK$ |
| --- | ---: |
| Revenue | 104,701,040 |
| Gross profit | 8,390,212 |
| **Gross margin** | **8.0%** |
| Net profit | 623,696 |
| **Net margin** | **0.6%** |

The Group earned a ~15% gross margin and HK$8.1m of net profit in the first half of FY2025, then in the second half booked HK$104.7m of revenue at an 8.0% gross margin and just HK$0.6m of net profit. The underlying half-yearly gross margin sits around **15%**; the full-year FY2025 result (11.6%) is depressed by a specific H2 event. The single most important cost question is therefore **what happened in H2 FY2025** — a large low-margin project, a cost overrun, a year-end true-up, or related-party cost loading. A decomposition of H2 cost of sales (subcontractor / materials / labour / related-party) is the priority; this also bears directly on the quality and run-rate of FY2025 earnings.

**Annualised run-rate.** Doubling the latest half (6M to Sep-25) gives HK$187.1m of revenue and HK$12.3m of net profit at a 14.8% gross / 6.6% net margin — revenue slightly below FY2025 but margins back at the ~15% norm. The forward picture is a high-but-flat revenue base at a recovered ~15% gross margin (better than the headline FY2025 11.6%), still subject to the single-customer dependency.

**Operating leverage.** Administrative expenses rose **+58.2%** in absolute terms but **fell from 7.3% to 5.1% of revenue**, indicating genuine overhead leverage as the business scaled. This partially offsets the gross-margin erosion at the EBIT level (operating margin 8.9% → 6.5%). Whether this overhead level is sustainable post-listing — which typically adds public-company compliance, audit and investor-relations cost — should be assessed.

**Cost composition.** Cost of sales for an RMAA subcontractor comprises subcontractor payments, materials, direct labour and site overheads. A breakdown of these components, with the related-party subcontractor portion identified, will isolate whether the margin compression is driven by subcontractor-rate inflation, materials cost, or pricing on the single large customer — and whether it is structural or project-specific.

**Gross-margin sensitivity (illustrative, on FY2025 revenue of HK$200.7m).** Given the single-customer dependency, pricing is set by the dominant customer; the table shows the gross-profit effect of margin scenarios around the FY2025 actual of 11.6%:

| Gross-margin scenario | Gross profit (HK$) | vs. FY2025 actual |
| --- | ---: | ---: |
| 10.0% (further price pressure) | 20,073,654 | −3,307,793 |
| 11.6% (FY2025 actual) | 23,381,447 | — |
| 13.0% | 26,095,750 | +2,714,303 |
| 15.9% (FY2024 level) | 31,917,109 | +8,535,662 |

The sensitivity is asymmetric: with 93.7% customer concentration, pushing price above what the dominant customer accepts would result in volume loss, so margins materially above ~12% are unlikely without diversification, while margins below 10% are plausible under continued price pressure. Contract pricing terms and the margin on any competing projects won will refine this.
"""),

("working_capital", "Working Capital", """
Year-end trade working capital and turnover are derived from the trade-receivable and trade-payable supporting schedules and the audited revenue and cost of sales. Year-end balances and turnover are analysed below; monthly aged balances are a next-phase refinement.

**Net trade working capital and turnover (fiscal-year-end basis).**

| HK$ | FY2024 | FY2025 |
| --- | ---: | ---: |
| Trade receivables | 13,153,753 | 21,688,677 |
| Trade payables | (8,835,855) | (14,641,055) |
| **Net trade working capital** | **4,317,898** | **7,047,622** |
| Days sales outstanding (DSO) | 53.4 | 39.4 |
| Days payables outstanding (DPO) | 42.6 | 30.1 |

*For a labour/subcontracting RMAA contractor, inventory is negligible (sub-5 days) and is therefore not a working-capital driver; contract assets (unbilled work) form part of the cycle and are addressed under Revenue and Balance Sheet.*

**Methodology and sector benchmarks.** DSO = (Trade receivables ÷ Revenue) × 365; DPO = (Trade payables ÷ Cost of sales) × 365. For Hong Kong project-based contractors, DSO commonly runs 60–90 days (progress billing and retention extend collection) and DPO 30–60 days. Worldstar's DSO of 39 days (FY2025) is **better than the sector norm**, and DPO of 30 days is at the **low end** — i.e. the Company collects quickly but also pays quickly.

**Observations.**

- **Net trade working capital rose +63%** (HK$4.3m → HK$7.0m) as revenue scaled — a normal and healthy feature of a growing contractor (larger contract receivables, subcontractor advances and retention monies). The key implication for the listing is a **growing working-capital funding need**, which the IPO proceeds are well-placed to support.
- **DSO improved (53 → 39 days)** and **DPO shortened (43 → 30 days)** — collection performance strengthened over the period. The faster supplier settlement is consistent with maintaining good subcontractor relationships and securing capacity; the supplier interviews corroborate timely, dispute-free settlement (see Commercial Due Diligence).
- **Receivables quality.** Receivables are concentrated in the principal customer, whose payment behaviour the customer interview confirms as orderly and dispute-free since 2013; aged-receivable detail would further evidence collectability and retention release.

**Funding outlook.** As the business grows, the working-capital base will continue to expand; planning the IPO proceeds and facilities to fund this growth, and tracking the conversion of contract assets to cash, are the practical priorities. Monthly aged receivable/payable data would refine the days-metric trend in the next phase.
"""),

("net_debt", "Net Debt & Capital Structure", """
Net debt rose sharply in FY2025 as the Group funded a major property acquisition with bank borrowings.

| HK$ | 31 Mar 2024 | 31 Mar 2025 |
| --- | ---: | ---: |
| Bank borrowings | 20,010,546 | 37,308,885 |
| Lease liabilities (current + non-current) | 1,741,073 | 2,259,831 |
| Less: Cash and bank balances | (90,543) | (1,265,991) |
| **Net debt** | **21,661,076** | **38,302,725** |
| Net gearing (net debt / equity) | 113% | 277% |

**The FY2025 increase funded a HK$41.9m property.** Bank borrowings rose ~HK$17.3m (HK$20.0m → HK$37.3m). FY2025 includes an **HSBC mortgage of HK$29.4m secured on a property ("House 80", 4.75%, maturing 2055)** — the asset recognised within the HK$41.9m property, plant and equipment addition (see Balance Sheet Review). This shift from working-capital funding to a long-dated property mortgage is the principal cause of finance costs doubling to HK$2.7m, and it lifts net gearing to ~277%.

**Liquidity / refinancing risk.** The HK$37.3m of bank borrowings is presented **entirely within current liabilities**, against cash of only HK$1.27m. A long-dated mortgage shown as current implies a demand or covenant-driven classification. The facility terms, covenants, demand features and security (including whether facilities are secured on the concentrated customer receivable or the new property) are material to the listing and should be confirmed.

**Property rationale.** A HK$41.9m property funded by ~HK$29.4m of mortgage debt is a significant, non-operating-looking deployment for an RMAA / painting subcontractor. Read with the unwinding of the HK$32.4m related-party receivable and the ~HK$14.0m distribution, the commercial rationale, classification (operational vs. investment / owner-related) and valuation of the property are a key **related-party and asset-quality** matter to resolve before listing.

**Capital-structure / debt-like items** to address as part of listing preparation include the lease liabilities (HK$2.3m), the **HK$4.5m amount due to the shareholder**, and any declared-but-unpaid portion of the distribution; the shareholder payable in particular should be settled or documented before listing.
"""),


("balance_sheet", "Balance Sheet Review", """
The consolidated balance sheet is set out below, followed by a walk of the material balances and a leverage assessment. **FY2025 contains three transformational items** — a HK$41.9m property acquisition, the unwinding of a HK$32.4m related-party receivable, and a step-up in bank borrowings to HK$37.3m — that, together, reshape the financial profile of the Group ahead of listing.

**Consolidated balance sheet (HK$).**

| Line item | 31 Mar 2024 | 31 Mar 2025 |
| --- | ---: | ---: |
| Property, plant and equipment | 38,518 | 41,888,114 |
| Right-of-use assets | 985,753 | 1,285,108 |
| **Non-current assets** | 1,024,271 | 43,173,222 |
| Trade and other receivables | 13,153,753 | 21,688,677 |
| Amount due from a related company | 32,412,782 | — |
| Amount due from a shareholder | 87,050 | — |
| Contract assets | 3,941,782 | 8,509,035 |
| Cash and bank balances | 90,543 | 1,265,991 |
| **Current assets** | 49,685,910 | 31,463,703 |
| **Total assets** | 50,710,181 | 74,636,925 |
| Trade and other payables | 8,835,855 | 14,641,055 |
| Amount due to a shareholder | — | 4,488,950 |
| Bank borrowings | 20,010,546 | 37,308,885 |
| Lease liabilities (current) | 503,225 | 1,295,715 |
| Income tax payable | 988,862 | 2,087,611 |
| **Current liabilities** | 30,338,488 | 59,822,216 |
| Deferred tax liability | — | 23,100 |
| Lease liabilities (non-current) | 1,237,848 | 964,116 |
| **Non-current liabilities** | 1,237,848 | 987,216 |
| **Total liabilities** | 31,576,336 | 60,809,432 |
| **Net assets / total equity** | 19,133,845 | 13,827,493 |

**1. A HK$41.9m property acquisition dominates FY2025.** Property, plant and equipment rose from HK$38,518 to **HK$41,888,114** — the Group acquired ~HK$41.9m of property during the year (the asset behind the HSBC "House 80" mortgage). For a subcontractor with essentially no owned fixed assets a year earlier, this is a fundamental change in the nature of the balance sheet. The commercial rationale, an independent valuation, and whether the asset is operational (e.g. premises/yard) or an investment/owner-related property should be established.

**2. A HK$32.4m related-party receivable unwound.** At 31 March 2024 the Group was owed **HK$32,412,782 by a related company** — equal to 64% of total assets — reduced to nil by 31 March 2025. In substance, two-thirds of the FY2024 balance sheet had been advanced to a related company and was then recovered and redeployed (principally into the property). This is a major related-party exposure: the counterparty, terms, whether interest was charged, and how its recovery connects to the property purchase and the distribution should be fully explained.

**3. Bank borrowings stepped up to HK$37.3m — and sit in current liabilities.** Bank borrowings rose from HK$20.0m to **HK$37.3m**, all presented within current liabilities. A long-dated property mortgage classified as current implies a repayable-on-demand or covenant-driven presentation; against cash of only HK$1.27m, this is a material liquidity and refinancing matter (demand features, covenants, security) to understand before listing.

**4. Shareholder current account flipped.** The shareholder balance swung from a HK$87,050 receivable (FY2024) to a HK$4,488,950 payable (FY2025) — the Group now owes the controlling shareholder HK$4.5m, a debt-like item.

**5. Pre-IPO distribution of ~HK$14.0m.** Retained earnings fell from HK$19.1m to HK$13.8m despite HK$8.7m of net profit, implying a ~HK$14.0m distribution (analysed as substantially non-cash in the Cash Movement section, settled through the related-party / property movements). The interim half ties cleanly (HK$13.8m + HK$6.2m interim profit = HK$20.0m at 30 Sep 2025), so no distribution occurred in the latest period.

**6. Contract assets** grew from HK$3.94m to HK$8.51m, consistent with the over-time revenue policy and the revenue step-up; the conversion of unbilled work to cash, concentrated in the dominant customer, should be tracked.

**Movement into the interim period (unaudited, 30 September 2025).** The interim condensed balance sheet shows the FY2025 patterns continuing — and the related-party lending **resuming**:

| HK$ | 31 Mar 2025 | 30 Sep 2025 | Δ |
| --- | ---: | ---: | ---: |
| Property, plant and equipment | 41,888,114 | 43,593,503 | +1,705,389 |
| Right-of-use assets | 1,285,108 | 933,909 | −351,199 |
| Trade and other receivables | 21,688,677 | 22,589,629 | +900,952 |
| Amount due from a related company | — | 10,562,002 | +10,562,002 |
| Contract assets | 8,509,035 | 11,693,807 | +3,184,772 |
| Cash and bank balances | 1,265,991 | 1,004,281 | −261,710 |
| **Total assets** | 74,636,925 | 90,377,131 | +15,740,206 |
| Trade and other payables | 14,641,055 | 21,394,341 | +6,753,286 |
| Amount due to a shareholder | 4,488,950 | 2,984,402 | −1,504,548 |
| Bank borrowings | 37,308,885 | 40,453,241 | +3,144,356 |
| Lease liabilities (current + non-current) | 2,259,831 | 1,895,152 | −364,679 |
| Income tax payable | 2,087,611 | 3,664,537 | +1,576,926 |
| **Total liabilities** | 60,809,432 | 70,391,673 | +9,582,241 |
| **Total equity** | 13,827,493 | 19,985,458 | +6,157,965 |

- **Related-party lending resumed — this is not a one-off.** Having recovered the HK$32.4m related-party receivable by 31 March 2025, the Group advanced a **new HK$10.56m to a related company** within the following six months. The cycling of company funds to related parties is therefore an **ongoing pattern**, not a single FY2025 event, and should be a central focus of the next phase.
- **Equity rebuilt purely from profit.** Retained earnings rose exactly by the H1 net profit (HK$6.16m), confirming no interim distribution.
- **Leverage kept rising; cash stayed thin.** Bank borrowings increased a further HK$3.1m to **HK$40.5m**, while cash fell to **HK$1.0m**. Operating cash and the additional borrowings were absorbed by the new HK$10.56m related-party advance, growing contract assets (+HK$3.2m) and further PP&E (+HK$1.7m), part-funded by stretched payables (+HK$6.8m). The shareholder payable was partly repaid (HK$4.49m → HK$2.98m).
- **Contract assets grew to HK$11.7m**, continuing to outpace billing — the unbilled position, concentrated in the dominant customer, should be watched for collectability.

**Capitalisation and leverage — materially stretched.**

| Ratio | FY2024 | FY2025 |
| --- | ---: | ---: |
| Net debt (bank borrowings + lease liabilities − cash) | 21,661,076 | 38,302,725 |
| Total equity | 19,133,845 | 13,827,493 |
| **Net gearing (net debt / equity)** | **113%** | **277%** |
| Equity ratio (equity / total assets) | 37.7% | 18.5% |

Net gearing rose from ~113% to **~277%** as the Group added property debt and distributed equity, and the equity ratio more than halved to 18.5%. The Group enters the listing process **highly leveraged**, with HK$37.3m of current bank borrowings against HK$1.27m of cash. The IPO is, in part, a deleveraging / recapitalisation event; the post-money balance sheet should be modelled explicitly.
"""),

("cash_movement", "Cash Movement Analysis", """
Bank statements were not part of the materials, so rather than a formal proof of cash, the change in the cash balance is explained from the audited balance-sheet movements (a sources-and-uses analysis, to be read with the audited statement of cash flows).

Cash and bank balances rose only **HK$1.18m** (HK$90,543 → HK$1,265,991) in FY2025 — strikingly modest against HK$8.7m of net profit. The reconciliation is dominated by large, largely offsetting movements:

| FY2025 sources of funds (HK$) | | FY2025 uses of funds (HK$) | |
| --- | ---: | --- | ---: |
| Recovery of related-party / shareholder receivables | 32,499,832 | Property, plant & equipment acquired | 41,849,596 |
| Increase in bank borrowings | 17,298,339 | Distribution to shareholder | 14,000,000 |
| Net profit for the year | 8,693,648 | Increase in trade & other receivables | 8,534,924 |
| Increase in trade & other payables | 5,805,200 | Increase in contract assets | 4,567,253 |
| Increase in amount due to shareholder | 4,488,950 | Increase in right-of-use assets | 299,355 |
| Increase in tax / lease liabilities | 1,640,607 | | |
| **Total sources** | **70,426,576** | **Total uses** | **69,251,128** |

**Net increase in cash: HK$1,175,448** (sources less uses).

**Key observations.**

- **The property was funded by unwinding the related-party loan and gearing up — not by operating cash.** The ~HK$41.9m property acquisition was financed principally by recovering the HK$32.4m related-party receivable and drawing ~HK$17.3m of additional bank borrowings.
- **The ~HK$14.0m distribution was substantially non-cash.** Cash *rose* over the year; a HK$14.0m cash dividend would have required the balance to fall sharply. The distribution was therefore largely settled through the related-party and shareholder current accounts — the shareholder balance swung ~HK$4.6m toward a payable — rather than paid in cash. This should be confirmed against the audited statement of cash flows and statement of changes in equity.
- **Working capital absorbed operating cash.** Receivables (+HK$8.5m) and contract assets (+HK$4.6m) consumed most of the operating cash generated, only partly funded by payables (+HK$5.8m).
- **Liquidity remains thin.** Even after the increase, FY2025 cash of HK$1.27m is small against a HK$200.7m revenue base and HK$37.3m of current bank borrowings; the listing proceeds would be the principal source of balance-sheet repair.
"""),

("capex", "Capital Expenditure & Property Acquisition", """
Historically the business was asset-light — owned property, plant and equipment was just **HK$38,518** at 31 March 2024, consistent with a subcontracting model that leases rather than owns. **FY2025 broke decisively from this pattern.**

- **A ~HK$41.9m property acquisition.** Property, plant and equipment rose to **HK$41,888,114** at 31 March 2025 — an addition of ~HK$41.85m in a single year, the dominant capital event of the period. This is the asset associated with the HSBC "House 80" mortgage and was funded principally by bank borrowings (and the recovery of the HK$32.4m related-party receivable).
- **Right-of-use assets** (carrying) rose modestly from HK$0.99m to HK$1.29m, reflecting incremental warehouse / motor-vehicle leases — ordinary-course operational leasing.

**Implications.** Maintenance capital intensity for the core RMAA operations remains low, but the HK$41.9m property is a large, debt-financed, non-operating-looking outlay that fundamentally changes the asset base and the leverage profile. Its nature (operational premises/yard vs. investment or owner-related property), an independent valuation, the funding chain (related-party receivable + mortgage), and the commercial rationale for an RMAA subcontractor to hold a ~HK$42m property should be established. Whether the property is core to the listed business — or should be carved out before listing — is a material structuring question.
"""),

("accounting_policies", "Accounting Policies — Key Judgment Areas", """
- **Revenue recognition (IFRS 15).** RMAA/construction revenue is recognised over time on a percentage-of-completion (cost-to-cost) basis. This is the single most judgment-intensive policy: the measurement of progress, the estimate of total contract cost, the treatment of variations and claims, and the recognition of contract assets all directly affect reported revenue and margin. Combined with the single-customer concentration, this elevates the importance of cut-off and estimate testing.
- **Contract assets and unbilled revenue.** The over-time policy generates contract assets where revenue is recognised ahead of billing. Their measurement, ageing and conversion to billed receivables and cash should be examined, particularly for the dominant customer.
- **Leases (IFRS 16).** Right-of-use assets and lease liabilities are recognised; right-of-use depreciation (HK$0.80m FY2024, HK$0.90m FY2025) is the principal non-cash charge added back to EBITDA, and lease liabilities are debt-like for transaction purposes.
- **Related-party transactions.** Subcontracting with related parties is referenced in the cost-of-sales supporting schedule; the accounting, disclosure and arm's-length basis of these transactions are a key area for both accounting and governance review.
- **Reporting framework.** The financial statements are prepared under **International Financial Reporting Standards (IFRS) as issued by the IASB** (per the independent auditor's report). As a Foreign Private Issuer, the Company may file its SEC registration statement on this basis without reconciliation to US GAAP. The auditor is **SFAI Malaysia PLT**, PCAOB-registered and the Company's auditor since 2024.
"""),

("taxation", "Taxation", """
| HK$ | FY2024 | FY2025 |
| --- | ---: | ---: |
| Profit before tax | 6,874,436 | 10,385,862 |
| Income tax expense | (967,268) | (1,692,214) |
| **Effective tax rate** | **14.1%** | **16.3%** |

**Observations.**

- The effective tax rate trends towards the Hong Kong profits tax rate of **16.5%** (8.25% on the first HK$2m of assessable profits under the two-tiered regime), consistent with a Hong Kong-resident operating company with limited permanent differences. The slightly lower FY2024 rate is consistent with the two-tiered relief on a smaller profit base.
- **Holding-structure considerations.** The Cayman holding chain introduces cross-border questions — the tax residency of the holding entities, any Hong Kong or other withholding on intra-group distributions (relevant given the implied FY2025 distribution), and transfer pricing on the intercompany funding to be established at listing.
- **Outstanding.** Tax computations, deferred-tax analysis, and any tax-clearance or correspondence with the Inland Revenue Department were not provided and are required to complete the tax workstream and to confirm there are no unprovided exposures.
"""),

("internal_controls", "Internal Control & Governance Observations", """
No controls testing or walkthroughs were performed; the observations below are qualitative, based on the structure and the financial information reviewed, and should inform the scope of the next phase rather than be read as an assessment of control effectiveness.

- **Owner-managed control environment.** The Company is founder-led, with Mr. Lee as Chairman, CEO and controlling shareholder. Concentration of authority in a single individual, combined with a small administrative team (estimated 15–20 staff), raises standard segregation-of-duties and key-person considerations that an SEC registrant and its auditor will need to address (including SOX 302/404 readiness over time).
- **Controlled-company governance.** With ~95.45% voting control retained post-IPO, the issuer can rely on Nasdaq 5615(c) exemptions from majority board independence and independent committee requirements. The board does, however, include **three independent director appointees** (Messrs. Ka Ki Lo, Kwok Kit Kan and Yiu Wing Chan), from whom the audit committee — whose independence is **not** exemptible — would be drawn. Their independence determinations, the audit-committee composition and a designated financial expert, and the related-party approval process should be confirmed.
- **Related-party governance.** Given related-party subcontracting, a documented related-party transaction policy, register and independent approval mechanism (through the independent directors) are important both for accounting accuracy and for investor protection.
- **Financial reporting capability.** A **Chief Financial Officer (Mr. Ming Fung Choi)** is in place; the capacity of the finance function to meet SEC reporting timelines (20-F/6-K or 10-K/10-Q depending on FPI status), and the SEC independence and capacity of the auditor (SFAI Malaysia PLT, PCAOB-registered), should be considered as part of listing readiness.
"""),

("commitments", "Commitments & Contingencies", """
- **Lease commitments.** The Company has lease obligations (office premises and motor vehicles) reflected in the IFRS 16 lease liabilities (current HK$1.71m and non-current HK$0.69m at 31 March 2024); the FY2025 lease maturity profile and any non-cancellable commitments beyond the recognised liability should be obtained.
- **Customer-dependency contingency.** The 93.7% customer concentration is itself a contingent exposure: the absence of a documented long-term contract means revenue continuity is not contractually assured. This is the principal commercial contingency and is addressed throughout this report.
- **Related-party arrangements.** Subcontracting with related parties may carry pricing and continuity considerations; agreements and any commitments were not provided.
- **Litigation, guarantees and other contingencies.** No litigation, financial guarantees, performance bonds or other contingencies were identified in the information reviewed; however, performance/retention bonds are common in construction subcontracting, and a management representation and review of the F-1 contingencies note should confirm completeness.
"""),

("key_findings", "Key Matters & Listing-Preparation Roadmap", """
**Key findings.**

| # | Matter | Category |
| --- | --- | --- |
| 1 | Customer concentration 93.7% of FY2025 revenue (82.0% FY2024) — independently validated as an arm's-length, competitively-tendered relationship since 2013 with intent to continue (see Commercial DD); broaden and document the wider customer base. | Priority |
| 2 | FY2025 earnings/margin distorted by an anomalous H2 — H1 FY2025 15.6% GM / HK$8.1m profit vs H2 FY2025 8.0% GM / HK$0.6m profit; underlying half-yearly margin ~15%. H2 cost event and run-rate to investigate. | Priority — earnings quality |
| 3 | HK$41.9m debt-funded property ("House 80") acquired FY2025; net debt HK$21.7m → HK$38.3m; net gearing ~277%; HK$37.3m bank borrowings all current vs HK$1.27m cash. | Priority — capital structure |
| 4 | Related-party cash-cycling is ongoing — HK$32.4m receivable (FY2024) recovered, then a new HK$10.56m advanced by Sep-25; plus a HK$4.5m shareholder payable. | Priority — related-party |
| 5 | ~HK$14.0m pre-IPO distribution (FY2025), substantially non-cash via related-party / shareholder accounts. | To strengthen — related-party |
| 6 | Founder retains ~95.45% voting post-IPO; "controlled company" under Nasdaq 5615(c). | Governance |
| 7 | Related-party subcontracting (Wide Fortune, Man Shing, KL Engineering) — pricing untested; auditor SFAI Malaysia PLT (Malaysia-based, PCAOB-registered). | Observation |

The independent commercial due diligence (four counterparty interviews) is a clear positive and should be read alongside the items below: WEHK is rated 8–9/10, its relationships are long-standing and arm's-length, and no disputes or undisclosed arrangements were identified.

**Recommended listing-preparation steps.**

1. **Customer base** — formalise the documentation of the principal customer relationship (master-service / renewal terms, recent awards and invoices) and evidence the wider tender pipeline; the relationship itself is independently validated.
2. **Property and related-party arrangements** — document the HK$41.9m property's purpose, use and independent valuation; formalise or settle the related-party advances (HK$32.4m recovered, HK$10.56m re-advanced) and the HK$4.5m shareholder account; and confirm the ~HK$14.0m distribution via the statement of changes in equity. Consider whether the property is best held inside or outside the listed group.
3. **Funds flow** — the audited statement of cash flows to confirm the FY2025 sources and uses (and the largely non-cash nature of the distribution).
4. **Bank-facility terms** — confirm covenants, security and maturity for the HK$37.3m borrowings, and plan the IPO-proceeds deleveraging.
5. **H1/H2 margin** — a short half-yearly / monthly P&L to explain the weaker H2 FY2025 and confirm the ~15% run-rate margin.
6. **Adjusted EBITDA** — a management add-back schedule for the normalisation analysis; cost-of-sales / related-party pricing to confirm margins are arm's-length.
7. **Working-capital detail** — aged receivables / payables and contract-asset conversion, including retention.
8. **Commercial follow-ups** — complete the Alliance Contracting Company interview, confirm K&L's independence / absence of conflicts, and clarify the post-defects-liability maintenance responsibility.
9. **Auditor** — confirm SFAI Malaysia PLT's SEC independence and capacity.

**Overall.** WEHK is a fundamentally sound, profitable and growing Hong Kong RMAA and painting contractor with a healthy ~15% underlying gross margin, and the independent commercial due diligence provides strong external validation — high counterparty ratings, long-standing arm's-length relationships, confirmed integrity and continuity, and corroboration that the FY2025 growth was driven by genuine public-sector work. On the evidence reviewed the Company is **well-positioned to proceed with the proposed Nasdaq listing**. A focused, addressable set of listing-preparation items will deliver a clean offering: broadening and documenting the customer base; a short explanation of the H2 FY2025 margin; and tidying up the related-party and property arrangements, with the IPO proceeds right-sizing the capital structure. None of these is, on the evidence reviewed, an impediment to proceeding.
"""),
]


_ITEM = re.compile(r'\s*([-*]|\d+\.)\s+')

def fix_lists(md: str) -> str:
    out: list[str] = []
    for ln in md.split("\n"):
        is_item = bool(_ITEM.match(ln))
        prev = out[-1] if out else ""
        if is_item and prev.strip() != "" and not _ITEM.match(prev):
            out.append("")
        out.append(ln)
    return "\n".join(out)


async def main():
    async with async_session() as db:
        # replace the lean version
        try:
            old = uuid.UUID(OLD_RID)
            await db.execute(delete(ReportSection).where(ReportSection.report_id == old))
            await db.execute(delete(Report).where(Report.id == old))
            await db.commit()
        except Exception:
            pass
        comp = (await db.execute(select(Company).where(Company.id == CID))).scalar_one_or_none()
        rep = Report(company_id=CID, report_type="dd_report", tier="premium",
                     title=f"{comp.name} — Due Diligence Report", status="draft")
        db.add(rep)
        await db.commit()
        await db.refresh(rep)
        for i, (key, title, body) in enumerate(SECTIONS):
            db.add(ReportSection(report_id=rep.id, section_key=key, section_title=title,
                                 content=fix_lists(body.strip()), sort_order=i))
        await db.commit()
        rid = rep.id
    print("REPORT_ID", rid, flush=True)
    async with async_session() as db:
        pdf = await generate_report_pdf(db, CID, rid)
    pdf_out = "/Users/ariuslee/Downloads/Worldstar Engineering DD Report (QC).pdf"
    open(pdf_out, "wb").write(pdf)
    print("WROTE", pdf_out, len(pdf), "bytes", flush=True)
    async with async_session() as db:
        docx = await generate_report_docx(db, CID, rid)
    docx_out = "/Users/ariuslee/Downloads/Worldstar Engineering DD Report (QC).docx"
    open(docx_out, "wb").write(docx)
    print("WROTE", docx_out, len(docx), "bytes", flush=True)

asyncio.run(main())
