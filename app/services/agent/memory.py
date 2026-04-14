"""Memory service — store, retrieve, compress, and manage AI memories."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.services.ai.client import generate_text

# Token budget limits per layer
TOKEN_BUDGET = {
    "global": 300,
    "skill": 500,
    "company": 500,
    "recent": 200,
}
MAX_MEMORIES_PER_SCOPE = 20

# Rough estimate: 1 token ≈ 4 chars
CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _trim_to_budget(rules: list[str], max_tokens: int) -> list[str]:
    """Keep as many rules as fit within the token budget."""
    result = []
    used = 0
    for rule in rules:
        cost = _estimate_tokens(rule)
        if used + cost > max_tokens:
            break
        result.append(rule)
        used += cost
    return result


async def compress_feedback(raw_feedback: str, skill_name: str | None = None, scope: str | None = None) -> str:
    """Use AI to distill raw user feedback into a concise, actionable rule."""
    context_parts = []
    if skill_name:
        context_parts.append(f"Skill: {skill_name}")
    if scope:
        context_parts.append(f"Scope: {scope}")
    context = ", ".join(context_parts) if context_parts else "general"

    system_prompt = (
        "You are a memory compression engine. Your job is to distill user feedback "
        "into a single concise, actionable rule (1-2 sentences max). "
        "The rule should be written as a direct instruction that can be injected into "
        "a future AI prompt. Remove all conversational fluff. Keep specific details "
        "(names, numbers, standards) but remove narrative.\n\n"
        "Examples:\n"
        "Input: 'The gap analysis report you generated was really lacking in regulatory detail. "
        "For Malaysian companies going to Nasdaq, there's a whole set of SEC cross-listing "
        "requirements that you completely missed.'\n"
        "Output: 'For MY→Nasdaq gap analysis: must include SEC cross-listing requirements "
        "and dual regulatory compliance (SC Malaysia + SEC).'\n\n"
        "Input: 'I don't like how the valuation report doesn't show what happens if we "
        "change the discount rate. Can you always include that?'\n"
        "Output: 'Valuation reports must include sensitivity analysis table showing impact "
        "of discount rate changes.'"
    )

    user_prompt = f"Context: {context}\n\nRaw feedback:\n{raw_feedback}\n\nDistilled rule:"
    return await generate_text(system_prompt, user_prompt, max_tokens=200)


async def store_memory(
    db: AsyncSession,
    rule: str,
    company_id: uuid.UUID | None = None,
    skill_name: str | None = None,
    scope: str | None = None,
    source: str = "explicit_feedback",
    raw_feedback: str | None = None,
) -> Memory:
    """Store a new memory, compressing raw feedback if provided."""
    if raw_feedback:
        rule = await compress_feedback(raw_feedback, skill_name, scope)

    # Check for near-duplicate before inserting
    existing = await _find_similar(db, rule, company_id, skill_name)
    if existing:
        # Update the existing memory with the newer rule
        existing.rule = rule
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return existing

    # Enforce cap per scope
    await _enforce_cap(db, company_id, skill_name, scope)

    memory = Memory(
        company_id=company_id,
        skill_name=skill_name,
        scope=scope,
        rule=rule,
        source=source,
        status="active",
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return memory


async def retrieve_memories(
    db: AsyncSession,
    company_id: uuid.UUID | None = None,
    skill_name: str | None = None,
    scope: str | None = None,
) -> list[str]:
    """Retrieve relevant memories within token budget. Returns list of rule strings."""
    now = datetime.now(timezone.utc)

    # Layer 1: Global rules (no company, no skill)
    global_rules = await _fetch_rules(db, company_id=None, skill_name=None)
    global_rules = _trim_to_budget(global_rules, TOKEN_BUDGET["global"])

    # Layer 2: Skill-specific rules (no company, matching skill)
    skill_rules = []
    if skill_name:
        skill_rules = await _fetch_rules(db, company_id=None, skill_name=skill_name, scope=scope)
        skill_rules = _trim_to_budget(skill_rules, TOKEN_BUDGET["skill"])

    # Layer 3: Company-specific rules
    company_rules = []
    if company_id:
        company_rules = await _fetch_rules(db, company_id=company_id, skill_name=skill_name, scope=scope)
        company_rules = _trim_to_budget(company_rules, TOKEN_BUDGET["company"])

    # Layer 4: Recent feedback (last 3, any scope for this company+skill)
    recent_rules = []
    if company_id or skill_name:
        recent_rules = await _fetch_recent(db, company_id=company_id, skill_name=skill_name, limit=3)
        recent_rules = _trim_to_budget(recent_rules, TOKEN_BUDGET["recent"])

    # Deduplicate while preserving order
    all_rules: list[str] = []
    seen: set[str] = set()
    for rule in global_rules + skill_rules + company_rules + recent_rules:
        if rule not in seen:
            all_rules.append(rule)
            seen.add(rule)

    # Update retrieval stats for matched memories
    if all_rules:
        await _update_retrieval_stats(db, all_rules, now)

    return all_rules


async def _fetch_rules(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    skill_name: str | None,
    scope: str | None = None,
) -> list[str]:
    """Fetch active rules matching the given filters."""
    conditions = [Memory.status == "active"]

    if company_id is None:
        conditions.append(Memory.company_id.is_(None))
    else:
        conditions.append(Memory.company_id == company_id)

    if skill_name is None:
        conditions.append(Memory.skill_name.is_(None))
    else:
        conditions.append(
            or_(Memory.skill_name == skill_name, Memory.skill_name.is_(None))
        )

    if scope:
        conditions.append(
            or_(Memory.scope == scope, Memory.scope.is_(None))
        )

    query = (
        select(Memory.rule)
        .where(and_(*conditions))
        .order_by(desc(Memory.retrieval_count), desc(Memory.created_at))
        .limit(MAX_MEMORIES_PER_SCOPE)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def _fetch_recent(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    skill_name: str | None,
    limit: int = 3,
) -> list[str]:
    """Fetch the most recently created memories."""
    conditions = [Memory.status == "active"]
    if company_id:
        conditions.append(
            or_(Memory.company_id == company_id, Memory.company_id.is_(None))
        )
    if skill_name:
        conditions.append(
            or_(Memory.skill_name == skill_name, Memory.skill_name.is_(None))
        )

    query = (
        select(Memory.rule)
        .where(and_(*conditions))
        .order_by(desc(Memory.created_at))
        .limit(limit)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def _find_similar(
    db: AsyncSession,
    rule: str,
    company_id: uuid.UUID | None,
    skill_name: str | None,
) -> Memory | None:
    """Find an existing memory with very similar rule text (simple keyword overlap)."""
    conditions = [Memory.status == "active"]
    if company_id:
        conditions.append(Memory.company_id == company_id)
    else:
        conditions.append(Memory.company_id.is_(None))
    if skill_name:
        conditions.append(Memory.skill_name == skill_name)

    query = select(Memory).where(and_(*conditions))
    result = await db.execute(query)
    existing_memories = result.scalars().all()

    # Simple keyword overlap check (>60% word overlap = duplicate)
    rule_words = set(rule.lower().split())
    for mem in existing_memories:
        mem_words = set(mem.rule.lower().split())
        if not rule_words or not mem_words:
            continue
        overlap = len(rule_words & mem_words) / max(len(rule_words), len(mem_words))
        if overlap > 0.6:
            return mem
    return None


async def _enforce_cap(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    skill_name: str | None,
    scope: str | None,
) -> None:
    """Archive oldest memories if we exceed the cap for this scope."""
    conditions = [Memory.status == "active"]
    if company_id:
        conditions.append(Memory.company_id == company_id)
    if skill_name:
        conditions.append(Memory.skill_name == skill_name)
    if scope:
        conditions.append(Memory.scope == scope)

    count_query = select(func.count(Memory.id)).where(and_(*conditions))
    result = await db.execute(count_query)
    count = result.scalar() or 0

    if count >= MAX_MEMORIES_PER_SCOPE:
        # Archive the oldest, least-retrieved ones
        excess = count - MAX_MEMORIES_PER_SCOPE + 1
        oldest_query = (
            select(Memory.id)
            .where(and_(*conditions))
            .order_by(Memory.retrieval_count.asc(), Memory.created_at.asc())
            .limit(excess)
        )
        result = await db.execute(oldest_query)
        ids_to_archive = list(result.scalars().all())

        if ids_to_archive:
            await db.execute(
                update(Memory)
                .where(Memory.id.in_(ids_to_archive))
                .values(status="archived")
            )
            await db.commit()


async def _update_retrieval_stats(
    db: AsyncSession,
    rules: list[str],
    now: datetime,
) -> None:
    """Bump retrieval count and timestamp for matched memories."""
    await db.execute(
        update(Memory)
        .where(and_(Memory.rule.in_(rules), Memory.status == "active"))
        .values(
            retrieval_count=Memory.retrieval_count + 1,
            last_retrieved_at=now,
        )
    )
    await db.commit()


async def mark_superseded(
    db: AsyncSession,
    skill_name: str,
    scope: str | None = None,
    pattern: str | None = None,
    reason: str = "",
) -> int:
    """Mark memories as superseded by code. Returns count of affected memories."""
    conditions = [
        Memory.status == "active",
        Memory.skill_name == skill_name,
    ]
    if scope:
        conditions.append(Memory.scope == scope)
    if pattern:
        conditions.append(Memory.rule.ilike(f"%{pattern}%"))

    result = await db.execute(
        update(Memory)
        .where(and_(*conditions))
        .values(status="superseded_by_code", superseded_reason=reason)
    )
    await db.commit()
    return result.rowcount  # type: ignore[return-value]


async def export_memories(db: AsyncSession) -> dict:
    """Export memory analytics for developer review."""
    # All active memories
    query = select(Memory).where(Memory.status == "active").order_by(desc(Memory.retrieval_count))
    result = await db.execute(query)
    memories = result.scalars().all()

    # Group by skill
    by_skill: dict[str, list[dict]] = {}
    for mem in memories:
        key = mem.skill_name or "global"
        if key not in by_skill:
            by_skill[key] = []
        by_skill[key].append({
            "id": str(mem.id),
            "rule": mem.rule,
            "scope": mem.scope,
            "company_id": str(mem.company_id) if mem.company_id else None,
            "source": mem.source,
            "retrieval_count": mem.retrieval_count,
            "created_at": mem.created_at.isoformat() if mem.created_at else None,
        })

    # Find frequent patterns (rules that appear across multiple companies)
    rule_counts: dict[str, int] = {}
    for mem in memories:
        # Normalize for grouping
        normalized = mem.rule.lower().strip()
        rule_counts[normalized] = rule_counts.get(normalized, 0) + 1

    top_patterns = sorted(
        [
            {"rule": rule, "frequency": count}
            for rule, count in rule_counts.items()
            if count > 1
        ],
        key=lambda x: x["frequency"],
        reverse=True,
    )[:20]

    return {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "total_active": len(memories),
        "by_skill": by_skill,
        "top_patterns": top_patterns,
        "recommendations": [
            {
                **p,
                "recommendation": "HARD_CODE" if p["frequency"] >= 5 else "REVIEW",
            }
            for p in top_patterns
        ],
    }
