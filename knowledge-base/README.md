# Orionmano AI Advisory Platform — Knowledge Base

This knowledge base powers the Orionmano AI advisory tool, which takes customer company information and files (prospectus, audit reports, interview materials, legal findings) as input and generates professional deliverables (PDF/Word reports and PowerPoint decks).

## Platform Overview

**Client:** Orionmano International Holding Co. (Hong Kong)
**Core Services:** Business valuation, accounting & tax, due diligence & advisory, regulatory compliance (KYC/AML)
**Standards:** IFRS 13 / ASC 820

## Deliverables (ordered by engagement lifecycle)

| # | Deliverable | Audience | Format |
|---|-------------|----------|--------|
| 0 | **Gap Analysis** | **Client management / Advisory team** | **PDF (4 pages)** |
| 1 | Sales Deck | Potential customer | PPTX |
| 2 | Kick-off Meeting Deck | Customer | PPTX |
| 3 | Industry Expert Report | Customer (deliverable) | PDF/Word |
| 4 | Due Diligence Report | Underwriter reference | PDF/Word |
| 5 | Valuation Report | Customer / Underwriter / Investor | PDF/Word |
| 6 | Company Teaser | Potential investor | PDF |
| 7 | Company Deck | Investor presentation | PPTX |

> **Note:** The Gap Analysis (#0) is the first and most frequently used report. It is delivered between the first and second client meetings and determines whether to proceed with a full engagement. It assesses the company's Nasdaq IPO readiness across financial, governance, reporting, and industry-specific dimensions.

## Knowledge Base Structure

```
knowledge-base/
├── 01-input-framework/          # What data to collect from customers
│   ├── input-overview.md        # Engagement stages & data requirements
│   ├── stage-1-onboarding.md    # Basic company info & documents
│   ├── stage-2-financial.md     # Financial deep dive & audit materials
│   └── stage-3-market-ready.md  # Full DD, valuation & investor materials
│
├── 02-due-diligence/            # Financial DD & gap analysis frameworks
│   ├── gap-analysis.md          # Gap analysis methodology (Nasdaq IPO readiness)
│   ├── dd-framework.md          # Overall DD methodology & scope
│   ├── financial-analysis.md    # BS/IS/CF analytical review framework
│   ├── internal-controls.md     # Internal control evaluation framework
│   └── risk-assessment.md       # Risk identification & flag system
│
├── 03-industry-research/        # Industry expert report framework
│   ├── industry-framework.md    # Research methodology & report structure
│   └── market-analysis.md       # Market sizing, competitive landscape, trends
│
├── 04-valuation/                # Valuation report framework
│   ├── valuation-framework.md   # Methodologies (DCF, comps, precedent, NAV)
│   ├── financial-modeling.md    # Financial model construction & projection
│   ├── valuation-model-reference.md  # Actual OM workpaper template (from Project TP)
│   ├── project-tp-calc-graph.md      # Reverse-engineered formula spec from real TP workpaper
│   ├── inputs-sheet-schema.md        # v1 Inputs sheet schema + JSON contract
│   ├── broken-refs-audit.md          # Audit of 985 #REF! errors in TP vs v1 schema
│   └── v1-implementation.md          # v1 build status, file inventory, run instructions
│
├── 05-report-templates/         # Section-by-section templates for each deliverable
│   ├── 00-gap-analysis.md       # Gap analysis report (4-page Nasdaq readiness assessment)
│   ├── 01-sales-deck.md
│   ├── 02-kickoff-deck.md
│   ├── 03-industry-report.md
│   ├── 04-dd-report.md
│   ├── 05-valuation-report.md
│   ├── 06-company-teaser.md
│   └── 07-company-deck.md
│
├── 06-reference-data/           # Regulatory, accounting & market references
│   ├── accounting-standards.md  # IFRS, MFRS, US GAAP key policies
│   ├── tax-regulatory.md        # Multi-jurisdiction tax & compliance
│   ├── listing-standards.md     # US exchange requirements (Nasdaq tiers + NYSE)
│   └── engagement-legal.md     # Engagement letters, disclaimers, confidentiality
│
└── README.md                    # This file
```

## How the Knowledge Base Is Used

1. **Input Framework** defines what data to collect at each engagement stage
2. **Analysis Frameworks** (DD, Industry, Valuation) guide how AI analyzes the collected data
3. **Report Templates** define the section-by-section structure for each deliverable
4. **Reference Data** provides regulatory/accounting context for accurate, compliant analysis
5. **AI generates** professional narratives for each report section using the frameworks + customer data as context

## Active build threads

| Module | Status | See |
|---|---|---|
| Valuation report v1 | Skeleton + JSON export pipeline built; formulas TODO | [04-valuation/v1-implementation.md](04-valuation/v1-implementation.md) |
