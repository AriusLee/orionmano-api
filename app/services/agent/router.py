"""Agent router — orchestrates skill execution via tool-use loop.

Token optimization:
- Phase 1: Lightweight intent classification (no tools, no company context)
- Phase 2: Only if action intent detected, load tools + full context
Simple Q&A never pays the tool schema cost.
"""

from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.client import get_deepseek_client, DEEPSEEK_MODEL
from app.services.agent.context import AgentContext
from app.services.agent.registry import registry
from app.services.agent.memory import retrieve_memories
from app.services.agent.skill import SkillResult, SkillStatus

# Lightweight prompt for intent classification — no tools, no company context
CLASSIFY_SYSTEM_PROMPT = """You are a router. Classify the user's LATEST message intent.

Reply with EXACTLY one word:
- "action" — if the user wants to generate, create, build, export, analyze, extract, research, or perform any task
- "chat" — if the user is asking a question, having a conversation, or requesting information

Examples:
- "Generate a gap analysis report" → action
- "What is the company's revenue?" → chat
- "Create a sales deck" → action
- "Can you explain the financial data?" → chat
- "Run a valuation" → action
- "Hi, how are you?" → chat
- "Analyze the financials" → action
- "What gaps were identified?" → chat
"""

# Full system prompt only used when tools are needed
AGENT_SYSTEM_PROMPT = """You are an expert AI advisory agent at Orionmano Assurance Services, a Hong Kong-based financial advisory firm.

You have access to specialized skills (tools) that you can call to perform actions. You should:
1. Use the appropriate skill for the user's request.
2. You can chain multiple skills if the task requires it.
3. After a skill completes, summarize the result to the user in a helpful way.

Be professional, insightful, and data-driven. When discussing financial data, be specific with numbers and percentages.
"""

# Lightweight chat prompt — no tool schemas injected
CHAT_SYSTEM_PROMPT = """You are an expert financial advisor at Orionmano Assurance Services, a Hong Kong-based financial advisory firm.
You are helping an advisor work on a client engagement. Be professional, insightful, and data-driven.
When discussing financial data, be specific with numbers and percentages.
You can help with: analyzing documents, refining reports, answering questions about the company, and providing advisory insights.

If the user asks you to perform an action (generate report, create deck, etc.), let them know you can do it and ask them to confirm.
"""

MAX_TOOL_ROUNDS = 5

# Keywords that strongly signal action intent (skip classification call)
ACTION_KEYWORDS = {
    "generate", "create", "build", "make", "export", "produce",
    "analyze", "extract", "research", "run", "prepare", "draft",
}


def _quick_intent_check(message: str) -> str | None:
    """Fast keyword-based intent check. Returns 'action' or None (needs LLM classification)."""
    words = set(message.lower().split())
    if words & ACTION_KEYWORDS:
        return "action"
    return None


async def _classify_intent(client, messages: list[dict]) -> str:
    """Use a cheap LLM call to classify intent. No tools, minimal tokens."""
    # Only send the last user message for classification
    last_user_msg = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            last_user_msg = msg["content"]
            break

    if not last_user_msg:
        return "chat"

    # Quick keyword check first
    quick = _quick_intent_check(last_user_msg)
    if quick:
        return quick

    response = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": last_user_msg},
        ],
        max_tokens=10,
        temperature=0,
    )
    result = (response.choices[0].message.content or "").strip().lower()
    return "action" if "action" in result else "chat"


async def route_stream(
    db: AsyncSession,
    company_id: uuid.UUID,
    conversation_id: uuid.UUID,
    messages: list[dict],
    user_id: uuid.UUID | None = None,
) -> AsyncGenerator[str, None]:
    """Stream an agent response. Only loads tools + full context when action intent is detected."""

    client = get_deepseek_client()

    # Phase 1: Classify intent (cheap — no tools, no company context)
    intent = await _classify_intent(client, messages)

    if intent == "chat":
        # Lightweight chat path — no tools, minimal context
        async for chunk in _chat_stream(client, db, company_id, messages):
            yield chunk
    else:
        # Full agent path — tools + company context + memory
        async for chunk in _agent_stream(client, db, company_id, conversation_id, messages, user_id):
            yield chunk


async def _chat_stream(
    client,
    db: AsyncSession,
    company_id: uuid.UUID,
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    """Lightweight chat — no tools, just company context + memory."""
    from app.services.chat.chat_service import build_system_prompt
    from app.services.ai.web_search import web_search, format_search_results

    system_prompt = await build_system_prompt(db, company_id)

    # Inject only global + company memories (no skill-specific)
    memory_rules = await retrieve_memories(db, company_id=company_id)
    if memory_rules:
        rules_text = "\n".join(f"- {r}" for r in memory_rules)
        system_prompt += f"\n\n## Guidelines from past feedback (follow these strictly):\n{rules_text}\n"

    # Web search enrichment for research queries
    last_msg = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            last_msg = msg["content"]
            break

    search_keywords = ["market", "industry", "competitor", "trend", "regulation", "listing", "ipo", "nasdaq", "news", "recent"]
    if any(kw in last_msg.lower() for kw in search_keywords):
        try:
            results = await web_search(last_msg, max_results=3)
            web_context = format_search_results(results)
            if web_context:
                system_prompt += f"\n\n{web_context}"
        except Exception:
            pass

    llm_messages = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]

    stream = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=llm_messages,
        max_tokens=4096,
        stream=True,
    )

    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def _agent_stream(
    client,
    db: AsyncSession,
    company_id: uuid.UUID,
    conversation_id: uuid.UUID,
    messages: list[dict],
    user_id: uuid.UUID | None = None,
) -> AsyncGenerator[str, None]:
    """Full agent path — tools + company context + memory. Only called for action intents."""

    ctx = AgentContext(
        db=db,
        company_id=company_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    await ctx.load_company_data()

    # Retrieve memories
    memory_rules = await retrieve_memories(db, company_id=company_id)
    ctx.memory_rules = memory_rules

    # Build system prompt with full context
    system_prompt = AGENT_SYSTEM_PROMPT
    company_context = ctx.get_company_context_str()
    if company_context:
        system_prompt += f"\n\n## Company Context\n{company_context}"
    memory_prompt = ctx.get_memory_prompt()
    if memory_prompt:
        system_prompt += memory_prompt

    # Get tool schemas from registered skills
    tools = registry.get_tool_schemas()

    llm_messages = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]

    for _round in range(MAX_TOOL_ROUNDS):
        call_kwargs: dict = {
            "model": DEEPSEEK_MODEL,
            "messages": llm_messages,
            "max_tokens": 4096,
            "stream": True,
        }
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"

        stream = await client.chat.completions.create(**call_kwargs)

        full_content = ""
        tool_calls_data: dict[int, dict] = {}

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            delta = choice.delta

            if delta.content:
                full_content += delta.content
                yield delta.content

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_data:
                        tool_calls_data[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function and tc.function.name else "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls_data[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_data[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_data[idx]["arguments"] += tc.function.arguments

            if choice.finish_reason == "stop":
                return
            if choice.finish_reason == "tool_calls":
                break

        if not tool_calls_data:
            return

        # Build assistant message with tool calls
        assistant_msg: dict = {"role": "assistant", "content": full_content or None}
        assistant_msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                },
            }
            for tc in tool_calls_data.values()
        ]
        llm_messages.append(assistant_msg)

        # Execute each tool call
        for tc in tool_calls_data.values():
            skill_name = tc["name"]
            tool_call_id = tc["id"]

            try:
                kwargs = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                kwargs = {}

            skill = registry.get(skill_name)
            if not skill:
                tool_result = f"Error: Unknown skill '{skill_name}'"
            else:
                # Retrieve skill-specific memories
                skill_memories = await retrieve_memories(
                    db, company_id=company_id, skill_name=skill_name,
                )
                ctx.memory_rules = skill_memories

                yield f"\n\n> Executing: **{skill_name}**...\n\n"

                validation_error = skill.validate_params(**kwargs)
                if validation_error:
                    tool_result = f"Error: {validation_error}"
                else:
                    try:
                        result: SkillResult = await skill.execute(ctx, **kwargs)
                        if result.status == SkillStatus.SUCCESS:
                            ctx.artifacts[skill_name] = result.data
                            tool_result = result.message or json.dumps(result.data, default=str)
                        else:
                            tool_result = f"Skill failed: {result.message}"
                    except Exception as e:
                        tool_result = f"Skill execution error: {str(e)}"

            llm_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_result,
            })

    yield "\n\n(Reached maximum tool execution rounds)"
