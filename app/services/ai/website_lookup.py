"""Guess a company's primary website domain using the LLM.

Used when the user creates a company without providing a website, so we can
still feed a domain to the logo_fetcher pipeline (Clearbit → Google favicon → og:image).
"""

import json

from app.services.ai.client import generate_text


async def guess_website(
    name: str,
    legal_name: str | None = None,
    industry: str | None = None,
    country: str | None = None,
) -> str | None:
    """Ask the LLM for the most likely primary domain. Returns a bare domain
    like "example.com" or None when unclear."""
    if not name or not name.strip():
        return None

    hints = []
    if legal_name and legal_name != name:
        hints.append(f"Legal name: {legal_name}")
    if industry:
        hints.append(f"Industry: {industry}")
    if country:
        hints.append(f"Country: {country}")
    hint_block = "\n".join(hints) if hints else ""

    user_prompt = f"""Identify the primary website domain for this company.

Company: {name}
{hint_block}

Respond with ONLY a JSON object:
  {{"domain": "example.com"}}   — if you are confident
  {{"domain": null}}             — if the company is obscure or the name is ambiguous

Rules:
- Bare domain only (no https:// and no www. prefix)
- Use the company's own corporate website, not an aggregator or directory
- If multiple brands share the name, prefer the one matching the hints above
- If unsure, return null rather than guessing"""

    try:
        result = await generate_text(
            system_prompt="You are a business knowledge assistant that returns concise JSON.",
            user_prompt=user_prompt,
            max_tokens=80,
        )
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            cleaned = cleaned.rsplit("```", 1)[0]
        data = json.loads(cleaned)
    except Exception:
        return None

    domain = data.get("domain") if isinstance(data, dict) else None
    if not isinstance(domain, str):
        return None
    domain = domain.strip().lower()
    if not domain or "." not in domain or " " in domain:
        return None
    # Strip common prefixes in case the model included them despite instructions
    for p in ("https://", "http://", "www."):
        if domain.startswith(p):
            domain = domain[len(p):]
    return domain or None
