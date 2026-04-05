from openai import AsyncOpenAI
from app.config import settings

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"


def get_deepseek_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
) -> str:
    """Generate text using DeepSeek API."""
    client = get_deepseek_client()
    response = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
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
