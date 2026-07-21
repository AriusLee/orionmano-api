"""Cross-section lint pass for multi-section reports.

After all sections of a gap / DD / industry report are generated, this runs ONE
LLM call against the full content and surfaces contradictions for the analyst.
Findings are stored on the report row as JSON, NOT auto-applied — finance
deliverables are too high-stakes to silently rewrite numbers post-hoc.

Why this is needed: parallel-generation passes only inject a 1500-char snippet
of foundation sections (`generator.py::_generate_gap_parallel`). It's easy for
parallel sections to disagree on revenue figures, FPI status, listing tier,
valuation date, currency. The LLM owning each section has limited cross-context.
A single end-of-run scan catches what the parallel-batch scan missed.

Cost: 1 LLM call per report. With prompt caching, the system instruction is
stable across all reports; only the section content varies, so total cost ≈
$0.05-0.15 per gap report.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.services.ai.client import generate_text


_LINT_SYSTEM_PROMPT = """You are an editorial reviewer for IPO advisory reports. Your task is to find CONTRADICTIONS across sections of a single report — places where two sections state different facts about the same underlying thing.

WHAT TO FLAG:
- Numeric contradictions: same metric (revenue, EBITDA, share count, valuation, headcount, etc.) cited as different values in different sections, for the same period
- Status contradictions: e.g. company described as Foreign Private Issuer in one section, US domestic issuer in another
- Listing tier contradictions: e.g. recommended Nasdaq Capital Market vs. Nasdaq Global Market in different sections
- Date contradictions: valuation date, fiscal year end, or transaction date stated differently
- Currency / unit contradictions: figures in USD'000 in one section, USD millions in another, without conversion
- Recommendation conflicts: section A advises action X; section B advises against action X

WHAT NOT TO FLAG:
- Sections discussing different aspects of the same thing (a quantitative section and a qualitative section can both cover revenue without contradicting)
- Forward-looking estimates that legitimately differ from historicals
- Different scenarios (base / upside / downside) by design
- Stylistic/wording differences that don't change meaning
- Anything you're not >80% confident is an actual contradiction

OUTPUT: A single JSON object with this exact shape, nothing else:

{
  "findings": [
    {
      "severity": "critical" | "high" | "medium" | "low",
      "kind": "numeric" | "status" | "tier" | "date" | "currency" | "recommendation" | "other",
      "section_a": "<title of first section>",
      "section_b": "<title of second section>",
      "claim_a": "<verbatim short quote from section A — max 200 chars>",
      "claim_b": "<verbatim short quote from section B — max 200 chars>",
      "issue": "<one sentence explaining the contradiction>",
      "suggested_fix": "<one sentence — which section to change and how>"
    }
  ]
}

If you find no contradictions, return {"findings": []}. Output JSON only — no prose, no markdown fences, no preamble."""


def _build_user_prompt(sections_md: str) -> str:
    return (
        "# Report sections\n\n"
        f"{sections_md}\n\n"
        "# Task\n\n"
        "Scan all sections above for contradictions per the rules. Return JSON only."
    )


def _parse_findings(raw: str) -> list[dict[str, Any]]:
    """Parse the model's response into a list of finding dicts.
    Liberal: accepts JSON with or without code fences, recovers from prose preamble."""
    text = raw.strip()
    # Strip code fences if present
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Find first { and last } if there's surrounding noise
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    findings = obj.get("findings") if isinstance(obj, dict) else None
    if not isinstance(findings, list):
        return []
    # Normalize each entry — keep only known keys, coerce strings
    out: list[dict[str, Any]] = []
    allowed = {"severity", "kind", "section_a", "section_b", "claim_a", "claim_b", "issue", "suggested_fix"}
    for f in findings:
        if not isinstance(f, dict):
            continue
        clean = {k: (v if isinstance(v, str) else str(v)) for k, v in f.items() if k in allowed}
        if "issue" in clean and "section_a" in clean:
            out.append(clean)
    return out


_AUTOFIX_SYSTEM_PROMPT = """You are an editor patching a financial advisory report. Two sections of the same report contradict each other. Produce minimal-change replacements so they no longer contradict.

RULES:
1. Output ONLY a JSON object of the exact shape: {"section_a_content": "<full markdown>", "section_b_content": "<full markdown>"}. No prose, no markdown fences, nothing else.
2. Both replacements must be COMPLETE markdown for that section — preserve everything that was not part of the contradiction. Headings, lists, tables, ordering, wording all stay the same except for the contradicting claim.
3. Change ONLY the words that constitute the contradiction. Do not rewrite, restructure, or reword unaffected paragraphs.
4. If a "Ground truth" block is provided below, both sections must align to those canonical figures. Otherwise pick the more substantiated value (the one citing a specific document, the more conservative figure for IPO contexts) and use it in both.
5. Numbers, dates, currencies, percentages, ticker symbols, proper nouns — preserve verbatim except for the specific values being corrected."""


async def apply_lint_fix(
    *,
    report_id: uuid.UUID,
    company_id: uuid.UUID | None,
    finding: dict[str, Any],
    section_a: Any,
    section_b: Any,
    ground_truth: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Ask the LLM to patch two sections so they no longer contradict.

    Returns (new_a_content, new_b_content, error). On any failure (LLM error,
    invalid JSON, suspicious length drift) returns (None, None, error_msg) —
    the caller MUST NOT update the sections in that case.
    """
    a_content = (section_a.content or "").strip()
    b_content = (section_b.content or "").strip()
    if not a_content or not b_content:
        return None, None, "one or both sections have no content to patch"

    user_prompt = (
        "# The contradiction\n"
        f"- Severity: {finding.get('severity', 'unknown')}\n"
        f"- Kind: {finding.get('kind', 'unknown')}\n"
        f"- Issue: {finding.get('issue', '')}\n"
        f"- Section A name: {finding.get('section_a', section_a.section_title)}\n"
        f"- Claim A (verbatim): \"{finding.get('claim_a', '')}\"\n"
        f"- Section B name: {finding.get('section_b', section_b.section_title)}\n"
        f"- Claim B (verbatim): \"{finding.get('claim_b', '')}\"\n"
        f"- Suggested fix: {finding.get('suggested_fix', '')}\n"
    )
    if ground_truth:
        user_prompt += f"\n# Ground truth (canonical — both sections must align to this)\n\n{ground_truth}\n"

    user_prompt += (
        f"\n# Section A — \"{section_a.section_title}\" — current content\n\n{a_content}\n"
        f"\n# Section B — \"{section_b.section_title}\" — current content\n\n{b_content}\n"
    )

    try:
        raw = await generate_text(
            system_prompt=_AUTOFIX_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=8192,
            skill="lint_autofix",
            company_id=company_id,
            report_id=report_id,
        )
    except Exception as e:
        return None, None, f"LLM error: {type(e).__name__}: {str(e)[:200]}"

    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return None, None, f"could not parse LLM response as JSON: {e}"

    new_a = obj.get("section_a_content")
    new_b = obj.get("section_b_content")
    if not isinstance(new_a, str) or not isinstance(new_b, str) or not new_a.strip() or not new_b.strip():
        return None, None, "LLM response missing section_a_content or section_b_content"

    # Sanity: reject suspiciously large length changes (over-rewrite signal).
    # Allow ±60% drift — fixing a number can legitimately add or drop a sentence.
    for orig, new, label in ((a_content, new_a, "A"), (b_content, new_b, "B")):
        ratio = len(new) / max(len(orig), 1)
        if ratio < 0.4 or ratio > 1.6:
            return None, None, (
                f"section {label} length drift {ratio:.2f}× (orig {len(orig)} → new {len(new)}); "
                "rejecting to avoid over-rewrite. Edit manually instead."
            )

    return new_a.strip(), new_b.strip(), None


# ─── Deterministic internal-reference scan (valuation reports) ───────────────
# Client requirement (2026-07 feedback, item 9c): the client-facing valuation
# report must never reference internal process/worksheet artifacts. The prompt
# forbids them; this scan is the deterministic backstop. Pure string matching —
# no LLM call, cannot fail the report.

_INTERNAL_REFERENCE_PATTERNS: list[tuple[str, str]] = [
    (r"goal[\s-]?seek", "goal-seek mechanics"),
    (r"back[\s-]?solv", "back-solving language"),
    (r"target\s+valuation", "client target valuation"),
    # Negative lookahead: comps like Transcat legitimately sell "calibration services"
    (r"calibrat(?!ion[\s-]serv|ed instrument)", "calibration mechanics"),
    (r"Value_Summary", "internal worksheet name"),
    (r"segments_table|Inputs\s+sheet|named\s+range", "internal worksheet reference"),
    (r"\bpinned\b", "pinned-parameter mechanics"),
    # Lowercase-only: machine IDs are snake_case (revenue_growth_y1); uppercase
    # finance notation like FCFF_Y5 in a Gordon Growth formula is legitimate.
    (r"(?-i:\b[a-z][a-z0-9_]*_y[0-9]\b)", "machine parameter ID"),
    (r"Eric\s+item|Eric\s+20\d\d", "internal process note"),
]


def internal_reference_findings(sections: list[Any]) -> list[dict[str, Any]]:
    """Scan section content for internal references that must not appear in a
    client-facing valuation report. Returns findings in the same shape as the
    LLM lint pass so they render in the same UI."""
    out: list[dict[str, Any]] = []
    for s in sections:
        title = getattr(s, "section_title", None) or ""
        content = getattr(s, "content", None) or ""
        if not content.strip():
            continue
        for pattern, label in _INTERNAL_REFERENCE_PATTERNS:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                start = max(0, m.start() - 80)
                snippet = content[start:m.end() + 80].replace("\n", " ").strip()
                out.append({
                    "severity": "high",
                    "kind": "other",
                    "section_a": title,
                    "section_b": title,
                    "claim_a": snippet[:200],
                    "claim_b": "",
                    "issue": f"Internal reference leaked into client-facing report: {label} ('{m.group(0)}').",
                    "suggested_fix": "Remove or rephrase into natural client-facing valuation language before delivery.",
                })
                break  # one finding per pattern per section is enough
    return out


async def lint_report(
    report_id: uuid.UUID,
    company_id: uuid.UUID | None,
    sections: list[Any],
    max_chars_per_section: int = 8000,
) -> list[dict[str, Any]]:
    """Run the lint pass and return the findings list. Caller stores it.

    `sections` is the list of ReportSection ORM objects. Skips empty sections,
    truncates very long ones to bound input cost.
    """
    blocks: list[str] = []
    for s in sections:
        title = getattr(s, "section_title", None) or ""
        content = getattr(s, "content", None) or ""
        if not content.strip():
            continue
        if len(content) > max_chars_per_section:
            content = content[:max_chars_per_section] + "\n\n…[truncated for lint]"
        blocks.append(f"## {title}\n\n{content}")

    if len(blocks) < 2:
        return []  # Nothing to compare

    sections_md = "\n\n---\n\n".join(blocks)
    user_prompt = _build_user_prompt(sections_md)

    try:
        raw = await generate_text(
            system_prompt=_LINT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=4096,
            skill="lint_report",
            company_id=company_id,
            report_id=report_id,
        )
    except Exception:
        # Lint failures must never fail the report; log and return empty.
        return []

    return _parse_findings(raw)
