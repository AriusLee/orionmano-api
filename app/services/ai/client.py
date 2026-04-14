from openai import AsyncOpenAI
from app.config import settings

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"


def get_deepseek_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
        timeout=120.0,
    )


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    use_reasoner: bool = False,
) -> str:
    """Generate text using DeepSeek API.

    Args:
        use_reasoner: If True, uses deepseek-reasoner (R1) for chain-of-thought
                      reasoning. Slower and ~2x cost but much better for complex
                      analysis, financial math, and multi-step logic.
    """
    client = get_deepseek_client()
    model = DEEPSEEK_REASONER_MODEL if use_reasoner else DEEPSEEK_MODEL

    # Reasoner doesn't support system messages — merge into user prompt
    if use_reasoner:
        messages = [
            {"role": "user", "content": f"{system_prompt}\n\n---\n\n{user_prompt}"},
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content or ""


async def stream_text(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 2048,
):
    """Stream text using DeepSeek API."""
    client = get_deepseek_client()
    stream = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
