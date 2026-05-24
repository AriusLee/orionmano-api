"""Deterministic legal preamble for prospectus-style deliverables.

Eric 2026-05-24 — the DRS Industry Section opens with a standard third-party-
industry-consultant disclosure (modeled on the Frost & Sullivan exemplar in
real S-1 filings), citing Orionmano International Holdings Co. Limited as
"OM Assurance" and our industry report as "the OM Report". Same text is
rendered into the .docx export AND surfaced on the on-screen viewer so the
analyst sees what the client will see — single source of truth, lives here.
"""
from __future__ import annotations


def industry_drs_disclosure(company_name: str) -> str:
    """Return the italicized disclosure paragraph that sits at the top of the
    DRS Industry chapter, parameterized by the target company's name (which
    becomes the title of the cited industry report)."""
    name = (company_name or "the Company").strip()
    report_title = f"{name} Industry Report"
    return (
        "All the information and data presented in this section have been derived from "
        "Orionmano International Holdings Co. Limited (“OM Assurance”)’s "
        f"industry report commissioned by us entitled “{report_title}” (the "
        "“OM Report”) unless otherwise noted. OM Assurance has advised us that "
        "the statistical and graphical information contained herein is drawn from its "
        "database and other sources. The following discussion contains projections for "
        "future growth, which may not occur at the rates that are projected or at all."
    )
