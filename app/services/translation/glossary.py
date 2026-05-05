"""Loads the YAML glossary files (backend/glossary/*.yaml) once per process,
exposes lookup + version helpers used by the translator and the report renderer.

The glossary version is a short hash of all yaml file bytes. Editing any file
bumps the version, which invalidates cached translations on the next read."""
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

GLOSSARY_DIR = Path(__file__).resolve().parents[3] / "glossary"
GLOSSARY_FILES = ["_shared.yaml", "gap.yaml", "ie.yaml", "dd.yaml", "valuation.yaml"]


@lru_cache(maxsize=1)
def _load_all() -> tuple[list[dict], str]:
    entries: list[dict] = []
    hasher = hashlib.sha256()
    for fname in GLOSSARY_FILES:
        path = GLOSSARY_DIR / fname
        raw = path.read_bytes()
        hasher.update(raw)
        loaded = yaml.safe_load(raw) or []
        entries.extend(loaded)
    return entries, hasher.hexdigest()[:12]


def all_entries() -> list[dict]:
    return _load_all()[0]


def glossary_version() -> str:
    return _load_all()[1]


def review_status() -> dict:
    """Counts of approved / draft / TBD / do-not-translate entries across all langs.

    Used by the PDF export step to decide whether to add an "unreviewed glossary"
    watermark to zh-CN / ja outputs."""
    counts = {"total_entries": 0, "do_not_translate": 0, "approved": 0, "draft": 0, "tbd": 0}
    for e in all_entries():
        counts["total_entries"] += 1
        if e.get("do_not_translate"):
            counts["do_not_translate"] += 1
            continue
        for lang_key in ("zh_CN", "ja"):
            block = e.get(lang_key) or {}
            term = (block.get("term") or "").strip()
            if term.upper() == "TBD":
                counts["tbd"] += 1
            elif block.get("status") == "approved":
                counts["approved"] += 1
            else:
                counts["draft"] += 1
    return counts


def relevant_terms(text: str) -> list[dict]:
    """Return glossary entries whose `en` form appears as a substring of `text`
    (case-insensitive). Sorted longest-first so multi-word terms appear before
    single-word substrings in the prompt — helps the model prioritize correctly."""
    text_l = text.lower()
    hits = [e for e in all_entries() if e.get("en", "").lower() in text_l]
    hits.sort(key=lambda e: -len(e["en"]))
    return hits


def render_glossary_for_prompt(entries: Iterable[dict], target_lang: str) -> str:
    """Compact 'EN → translation' lines for the LLM prompt. Skips entries with
    no usable translation (TBD / missing) so the model is free to handle them."""
    lang_key = "zh_CN" if target_lang == "zh-CN" else "ja"
    lines: list[str] = []
    for e in entries:
        en = e["en"]
        if e.get("do_not_translate"):
            lines.append(f'- "{en}" → keep as the English literal "{en}"')
            continue
        block = e.get(lang_key) or {}
        term = (block.get("term") or "").strip()
        if not term or term.upper() == "TBD":
            continue
        lines.append(f'- "{en}" → "{term}"')
    return "\n".join(lines)
