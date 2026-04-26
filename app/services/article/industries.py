"""Fixed industry taxonomy + a keyword classifier.

The classifier looks at an article's title, topic, and topic_tags (all
concatenated, lower-cased) and picks the first industry whose keyword set
matches. Used both for backfill of existing articles and for live
classification at generation time, so the rules are the single source of
truth.

Order matters — more specific industries come first so that articles
straddling categories (e.g. esports + advertising) land in the more
specific bucket.
"""

from __future__ import annotations

import re
from typing import Iterable


# (slug, label, keyword regex patterns). Patterns are matched against the
# concatenated lower-cased text. Use whole-word boundaries where the term
# is a generic English word to avoid false positives (e.g. "ai" alone).
_TAXONOMY: list[tuple[str, str, list[str]]] = [
    (
        "esports",
        "Esports & Gaming",
        [
            r"\besport(s)?\b",
            r"\be-?sports?\b",
            r"\bgaming\b",
            r"\bvideo\s*games?\b",
            r"\bmobile\s*games?\b",
            r"\btournament(s)?\b",
            r"\btwitch\b",
            r"\bdreamhack\b",
            r"\bgarena\b",
            r"\briot\s*games\b",
            r"\bvalve\b",
            r"\btencent\b",
            r"\bdota\b",
            r"\bcounter[-\s]?strike\b",
            r"\bleague\s*of\s*legends\b",
            r"\boverwatch\b",
            r"\bvalorant\b",
            r"\bfortnite\b",
            r"\bmobile\s*legends\b",
            r"\bcall\s*of\s*duty\b",
            r"\bbgmi\b",
        ],
    ),
    (
        "technology",
        "Technology",
        [
            r"\bsoftware\b",
            r"\bsaas\b",
            r"\bartificial\s*intelligence\b",
            r"\bmachine\s*learning\b",
            r"\bcloud\s*comput",
            r"\bsemiconductor(s)?\b",
            r"\bchip(s)?\s*(maker|industry|market)?\b",
            r"\bcybersecurity\b",
            r"\bdata\s*cent(re|er)\b",
            r"\bblockchain\b",
            r"\bquantum\s*comput",
            r"\bdeveloper(s)?\s*platform",
        ],
    ),
    (
        "materials",
        "Materials",
        [
            r"\bnickel\b",
            r"\blithium\b",
            r"\bcobalt\b",
            r"\bcopper\b",
            r"\biron\s*ore\b",
            r"\bsteel\b",
            r"\baluminum\b|\baluminium\b",
            r"\brare\s*earth(s)?\b",
            r"\bmining\b",
            r"\bsmelter(s)?\b",
            r"\bcommodit(y|ies)\b",
            r"\brefining\b",
        ],
    ),
    (
        "energy",
        "Energy",
        [
            r"\boil\s*(and|&)\s*gas\b",
            r"\bcrude\s*oil\b",
            r"\bnatural\s*gas\b",
            r"\blng\b",
            r"\brenewable(s)?\b",
            r"\bsolar\s*(power|panel|pv)?\b",
            r"\bwind\s*(power|farm|turbine)?\b",
            r"\bnuclear\s*(power|reactor)?\b",
            r"\bhydrogen\s*economy\b",
            r"\bbattery\s*storage\b",
            r"\bev\s*battery\b",
            r"\butilit(y|ies)\b",
            r"\bgrid\s*(operator|infrastructure)\b",
        ],
    ),
    (
        "financials",
        "Financials",
        [
            r"\bbank(s|ing)?\b",
            r"\binsuran(ce|ers)\b",
            r"\bfintech\b",
            r"\blending\b",
            r"\bcapital\s*markets?\b",
            r"\bprivate\s*equit(y|ies)\b",
            r"\bventure\s*capital\b",
            r"\bhedge\s*fund(s)?\b",
            r"\bipo(s)?\b",
            r"\bm&a\b|\bmergers\s*(and|&)\s*acquisitions\b",
            r"\bsovereign\s*wealth\b",
            r"\bcredit\s*(card|rating|market)\b",
            r"\bpayment(s)?\b",
            r"\bbrokerage\b",
            r"\basset\s*management\b",
            r"\binvest(ment|or|ing)\b",
        ],
    ),
    (
        "healthcare",
        "Healthcare",
        [
            r"\bpharma(ceutical(s)?)?\b",
            r"\bbiotech\b",
            r"\bhospital(s)?\b",
            r"\bmedical\s*(device|equipment|imaging)?\b",
            r"\bdrug(s)?\s*(maker|pricing|approval)?\b",
            r"\btherapeutic(s)?\b",
            r"\bvaccine(s)?\b",
            r"\bclinical\s*trial\b",
            r"\bhealthcare\b",
            r"\bgenomic(s)?\b",
        ],
    ),
    (
        "telecom",
        "Telecom",
        [
            r"\btelecom(s|munication(s)?)?\b",
            r"\bbroadband\b",
            r"\b5g\b",
            r"\bwireless\s*(carrier|network)\b",
            r"\bmobile\s*network\b",
            r"\bisp(s)?\b",
            r"\bfibre?\s*(broadband|optic|network)\b",
            r"\binternet\s*penetration\b",
            r"\binternet\s*adoption\b",
            r"\binternet\s*connectivity\b",
            r"\binternet\s*infrastructure\b",
        ],
    ),
    (
        "consumer",
        "Consumer",
        [
            r"\bretail(er(s)?)?\b",
            r"\bfmcg\b",
            r"\bfashion\b",
            r"\bluxury\b",
            r"\be-?commerce\b",
            r"\bconsumer\s*goods?\b",
            r"\bfood\s*(and|&)\s*beverage(s)?\b",
            r"\bbeverage(s)?\b",
            r"\bcosmetic(s)?\b",
            r"\bapparel\b",
            r"\bsupermarket(s)?\b",
        ],
    ),
    (
        "industrials",
        "Industrials",
        [
            r"\bmanufactur(ing|er(s)?)\b",
            r"\blogistics\b",
            r"\bshipping\s*(industry|company|line)?\b",
            r"\baerospace\b",
            r"\bdefen[cs]e\b",
            r"\bautomation\b",
            r"\brobotic(s)?\b",
            r"\bautomotive\b",
            r"\bautomakers?\b",
            r"\bindustrial(s)?\b",
            r"\bsupply\s*chain\b",
        ],
    ),
    (
        "real-estate",
        "Real Estate",
        [
            r"\breal\s*estate\b",
            r"\breit(s)?\b",
            r"\bproperty\s*(market|developer|sector)?\b",
            r"\bhousing\s*(market|crisis|starts)?\b",
            r"\bmortgage\b",
            r"\bcommercial\s*property\b",
            r"\boffice\s*market\b",
        ],
    ),
    (
        "media",
        "Media",
        [
            r"\bstreaming\s*(service|platform|wars)?\b",
            r"\bbroadcast(er(s)?|ing)?\b",
            r"\bpublishing\b",
            r"\badvertising\b",
            r"\bsponsorship(s)?\b",
            r"\bmedia\s*(rights|company|outlet)?\b",
            r"\bfilm\s*industry\b",
            r"\bmusic\s*(industry|streaming)?\b",
        ],
    ),
    (
        "government",
        "Government & Policy",
        [
            r"\bregulator(s|y)?\b",
            r"\bregulation(s)?\b",
            r"\bpolic(y|ies)\b",
            r"\bministry\b",
            r"\bcentral\s*bank\b",
            r"\bgovernment\s*(spending|support|funding|policy)?\b",
            r"\bpublic\s*sector\b",
            r"\bsanction(s)?\b",
            r"\btariff(s)?\b",
            r"\bfederal\s*reserve\b",
            r"\bsec\b",  # Securities and Exchange Commission, in regulatory context
        ],
    ),
]


_GENERAL = ("general", "General")


# Pre-compile the regexes once.
_COMPILED: list[tuple[str, str, list[re.Pattern[str]]]] = [
    (slug, label, [re.compile(p, re.IGNORECASE) for p in patterns])
    for slug, label, patterns in _TAXONOMY
]


# Public — slug -> label dictionary, ordered. Useful for the API endpoint.
INDUSTRY_LABELS: dict[str, str] = {
    **{slug: label for slug, label, _ in _TAXONOMY},
    _GENERAL[0]: _GENERAL[1],
}

# Iteration order for nav rendering.
INDUSTRY_ORDER: list[str] = [slug for slug, _, _ in _TAXONOMY] + [_GENERAL[0]]


def classify_industry(
    *, title: str | None, topic: str | None, topic_tags: Iterable[str] | None
) -> str:
    """Return an industry slug for the given article fields. Falls back to
    'general' if nothing matches."""
    parts: list[str] = []
    if title:
        parts.append(title)
    if topic:
        parts.append(topic.replace("-", " ").replace("_", " "))
    if topic_tags:
        parts.extend(t.replace("-", " ").replace("_", " ") for t in topic_tags if t)
    haystack = " ".join(parts).lower()
    if not haystack.strip():
        return _GENERAL[0]

    for slug, _label, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(haystack):
                return slug

    return _GENERAL[0]


def industry_label(slug: str) -> str:
    return INDUSTRY_LABELS.get(slug, slug.replace("-", " ").title())
