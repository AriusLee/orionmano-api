import httpx
from app.config import settings


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using Tavily API and return results."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
                "search_depth": "advanced",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

    results = []
    if data.get("answer"):
        results.append({
            "title": "AI Summary",
            "content": data["answer"],
            "url": "",
        })
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "content": r.get("content", ""),
            "url": r.get("url", ""),
        })
    return results


def format_search_results(results: list[dict]) -> str:
    """Format search results as context string for LLM prompts."""
    if not results:
        return ""
    parts = ["## Web Research Results\n"]
    for i, r in enumerate(results, 1):
        parts.append(f"### Source {i}: {r['title']}")
        if r["url"]:
            parts.append(f"URL: {r['url']}")
        parts.append(r["content"])
        parts.append("")
    return "\n".join(parts)
