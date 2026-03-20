from groq import AsyncGroq
import anthropic
from app.config import settings

GROQ_MODEL = "llama-3.3-70b-versatile"


def get_groq_client() -> AsyncGroq:
    return AsyncGroq(api_key=settings.GROQ_API_KEY)


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
) -> str:
    """Generate text using Groq (free). Falls back to Anthropic if Groq fails."""
    try:
        client = get_groq_client()
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
    except Exception:
        # Fallback to Anthropic
        client = get_anthropic_client()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text


async def stream_text(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 2048,
):
    """Stream text using Groq. Falls back to Anthropic."""
    try:
        client = get_groq_client()
        stream = await client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception:
        # Fallback to Anthropic
        client = get_anthropic_client()
        async with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
