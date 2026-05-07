"""DeepSeek client + usage logging.

Prompt-cache contract (DeepSeek's KV cache fires automatically on prefix match):
- The `system_prompt` argument is the cacheable prefix. Keep it byte-identical
  across calls in the same logical batch (e.g. all sections of one report) and
  cache hit-rate goes way up. Hit tokens cost ~10% of miss tokens.
- Variable per-call content goes in the `user_prompt`.
- Don't interpolate per-call data (timestamps, ids, "section X of Y") into the
  system prompt — that defeats the cache. Anything dynamic belongs in the user
  message at the bottom.
- Cache effectiveness is logged in the `usage_log` table via
  `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` (DeepSeek-extension fields
  on the standard usage object).
"""
import asyncio
import time
import uuid
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.database import async_session
from app.models.usage_log import UsageLog

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"


def get_deepseek_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
        timeout=120.0,
    )


def _extract_usage(usage_obj: Any) -> dict:
    """Pull standard + DeepSeek-extension usage fields off a chat completion.
    DeepSeek adds `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` alongside
    the OpenAI-standard fields."""
    if usage_obj is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "cache_hit": 0, "cache_miss": 0}
    return {
        "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
        "cache_hit": getattr(usage_obj, "prompt_cache_hit_tokens", 0) or 0,
        "cache_miss": getattr(usage_obj, "prompt_cache_miss_tokens", 0) or 0,
    }


async def _log_usage(
    *,
    skill: str | None,
    company_id: uuid.UUID | None,
    report_id: uuid.UUID | None,
    model: str,
    use_reasoner: bool,
    usage: dict,
    latency_ms: int,
    error: str | None,
) -> None:
    """Fire-and-forget DB write. Errors are swallowed — usage logging must never
    take down the caller."""
    try:
        async with async_session() as db:
            db.add(UsageLog(
                skill=skill,
                company_id=company_id,
                report_id=report_id,
                model=model,
                use_reasoner=use_reasoner,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                cache_hit_tokens=usage["cache_hit"],
                cache_miss_tokens=usage["cache_miss"],
                latency_ms=latency_ms,
                error=error,
            ))
            await db.commit()
    except Exception:
        pass


def _spawn_log(coro) -> None:
    """Schedule a usage-log write without awaiting. Holds a reference so the task
    isn't garbage-collected mid-flight."""
    task = asyncio.create_task(coro)
    _LOG_TASKS.add(task)
    task.add_done_callback(_LOG_TASKS.discard)


_LOG_TASKS: set[asyncio.Task] = set()


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    use_reasoner: bool = False,
    *,
    skill: str | None = None,
    company_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
) -> str:
    """Generate text using DeepSeek API.

    Args:
        use_reasoner: If True, uses deepseek-reasoner (R1) for chain-of-thought
                      reasoning. Slower and ~2x cost but much better for complex
                      analysis, financial math, and multi-step logic.
        skill / company_id / report_id: Optional tags written to usage_log so
                      cost can be attributed downstream.
    """
    client = get_deepseek_client()
    model = DEEPSEEK_REASONER_MODEL if use_reasoner else DEEPSEEK_MODEL

    # Reasoner doesn't support system messages — merge into user prompt.
    # NOTE: this loses prompt caching for reasoner calls (system prefix becomes
    # part of a variable user message). Use sparingly; reasoner is only for the
    # ~3 sections that genuinely need it.
    if use_reasoner:
        messages = [
            {"role": "user", "content": f"{system_prompt}\n\n---\n\n{user_prompt}"},
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    started = time.monotonic()
    error: str | None = None
    response = None
    try:
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:300]}"
        raise
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        usage = _extract_usage(getattr(response, "usage", None))
        _spawn_log(_log_usage(
            skill=skill,
            company_id=company_id,
            report_id=report_id,
            model=model,
            use_reasoner=use_reasoner,
            usage=usage,
            latency_ms=latency_ms,
            error=error,
        ))


async def stream_text(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 2048,
    *,
    skill: str | None = None,
    company_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
):
    """Stream text using DeepSeek API. Caching contract same as generate_text."""
    client = get_deepseek_client()
    model = DEEPSEEK_MODEL

    started = time.monotonic()
    error: str | None = None
    final_usage: Any = None
    try:
        # stream_options.include_usage = true makes DeepSeek emit a final chunk
        # with the usage object after the message-content stream completes.
        stream = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                final_usage = chunk.usage
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:300]}"
        raise
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        usage = _extract_usage(final_usage)
        _spawn_log(_log_usage(
            skill=skill,
            company_id=company_id,
            report_id=report_id,
            model=model,
            use_reasoner=False,
            usage=usage,
            latency_ms=latency_ms,
            error=error,
        ))
