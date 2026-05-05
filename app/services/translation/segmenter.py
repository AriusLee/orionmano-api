"""Splits markdown into paragraph-sized segments and produces a stable hash key
for the translation cache. Paragraph is the right unit: sentence is too brittle
(context loss in CJK), whole-section is too coarse (one edit invalidates everything).

Numbers are NOT normalized away — for IPO reports we want different figures to
hash differently so each deal's per-share value, valuation, etc. caches separately."""
import hashlib
import re

CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)


def split_paragraphs(text: str) -> list[str]:
    """Split by blank lines. Code blocks are preserved intact (won't be split mid-block)."""
    placeholders: dict[str, str] = {}

    def stash(match: re.Match) -> str:
        key = f"\0CODEBLOCK{len(placeholders)}\0"
        placeholders[key] = match.group(0)
        return key

    masked = CODE_BLOCK_RE.sub(stash, text)
    parts = [p.strip() for p in re.split(r"\n\s*\n", masked) if p.strip()]
    if placeholders:
        parts = [
            next((v for k, v in placeholders.items() if p == k), p)
            if p in placeholders
            else _restore(p, placeholders)
            for p in parts
        ]
    return parts


def _restore(text: str, placeholders: dict[str, str]) -> str:
    for k, v in placeholders.items():
        text = text.replace(k, v)
    return text


def is_translatable(segment: str) -> bool:
    """Skip code blocks, very short segments, and segments that are mostly digits/symbols."""
    s = segment.strip()
    if len(s) < 3:
        return False
    if s.startswith("```"):
        return False
    letters = sum(1 for ch in s if ch.isalpha())
    if letters / max(len(s), 1) < 0.3:
        return False
    return True


def normalize_for_hash(segment: str) -> str:
    """Whitespace-only normalization. Preserves case, punctuation, numbers."""
    return re.sub(r"\s+", " ", segment.strip())


def segment_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
