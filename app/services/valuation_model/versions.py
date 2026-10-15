"""Valuation versions (Eric 2026-10, step 0 of the valuation-model request).

Every workpaper run is recorded as a `ValuationVersion`. One version per
company is `active` — that is what the valuation page, the report generator
and the next run's comp-set lock read. The others stay as history and can be
restored.

The xlsx + `.summary.json` files are still written by the export pipeline.
Companies that only have files (runs from before versions existed) are
imported once, lazily, the first time anything asks for their versions.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.valuation_version import ValuationVersion

logger = logging.getLogger(__name__)

TRIGGER_LABELS = {
    "generate": "Generated",
    "regenerate_inputs": "Re-uploaded inputs (JSON)",
    "regenerate_xlsx": "Re-uploaded workpaper (xlsx)",
    "qa_change": "Counterparty Q&A change",
    "restore": "Restored",
    "legacy_import": "Imported (earlier run)",
}


def _valuations_dir() -> Path:
    return Path(settings.UPLOAD_DIR).resolve() / "valuations"


def headline(summary: dict | None) -> tuple[float | None, float | None]:
    """(EV, equity value) of a computed summary, both per-management and in
    workpaper units. EV is the concluded DCF EV; equity is after DLOM/DLOC."""
    if not isinstance(summary, dict):
        return None, None

    def num(v: Any) -> float | None:
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    ev = num((summary.get("concluded") or {}).get("ev"))
    if ev is None:
        ev = num(((summary.get("dcf") or {}).get("per_management") or {}).get("ev"))
    equity = num(((summary.get("bridge") or {}).get("per_management") or {}).get("after_dloc"))
    return ev, equity


async def _next_version_no(db: AsyncSession, company_id: uuid.UUID) -> int:
    current = (await db.execute(
        select(func.max(ValuationVersion.version_no)).where(ValuationVersion.company_id == company_id)
    )).scalar_one_or_none()
    return (current or 0) + 1


async def import_legacy(db: AsyncSession, company_id: uuid.UUID) -> int:
    """Import a company's pre-versioning runs from their summary.json files,
    oldest first. No-op once the company has any version. Returns how many
    were imported."""
    has_any = (await db.execute(
        select(ValuationVersion.id).where(ValuationVersion.company_id == company_id).limit(1)
    )).scalar_one_or_none()
    if has_any is not None:
        return 0
    d = _valuations_dir()
    if not d.exists():
        return 0
    cid = str(company_id)
    found: list[tuple[float, dict]] = []
    for p in d.glob("valuation-*.summary.json"):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("company_id") != cid or not isinstance(data.get("inputs"), dict):
            continue
        found.append((p.stat().st_mtime, data))
    if not found:
        return 0
    found.sort(key=lambda x: x[0])
    # The newest file that the legacy reader treated as active stays active.
    active_idx = max(
        (i for i, (_, data) in enumerate(found) if data.get("status", "active") == "active"),
        default=len(found) - 1,
    )
    parent: ValuationVersion | None = None
    for i, (mtime, data) in enumerate(found):
        ev, equity = headline(data.get("summary"))
        cu = (data.get("inputs") or {}).get("currency") or {}
        report_id = data.get("report_id")
        version = ValuationVersion(
            id=uuid.uuid4(),
            company_id=company_id,
            version_no=i + 1,
            parent_id=parent.id if parent is not None else None,
            status="active" if i == active_idx else "superseded",
            trigger="legacy_import",
            note=f"Run of {str(data.get('generated_at') or '')[:10]}".strip(),
            inputs=data.get("inputs") or {},
            summary=data.get("summary"),
            warnings=data.get("warnings") or [],
            errors=data.get("errors") or [],
            xlsx_filename=data.get("xlsx_filename"),
            xlsx_url=data.get("xlsx_url"),
            report_id=uuid.UUID(report_id) if _is_uuid(report_id) else None,
            ev=ev,
            equity_value=equity,
            currency=cu.get("primary"),
            unit=cu.get("unit"),
            created_at=_run_time(data.get("generated_at"), mtime),
        )
        db.add(version)
        parent = version
    await db.flush()
    # Older reports made from these runs predate the link; attach each report
    # to the version that created it.
    from app.models.report import Report
    versions = (await db.execute(
        select(ValuationVersion).where(ValuationVersion.company_id == company_id, ValuationVersion.report_id.is_not(None))
    )).scalars().all()
    for v in versions:
        await db.execute(
            update(Report).where(Report.id == v.report_id, Report.valuation_version_id.is_(None)).values(valuation_version_id=v.id)
        )
    await db.commit()
    logger.info("imported %d legacy valuation runs for company %s", len(found), company_id)
    return len(found)


def _run_time(generated_at: Any, mtime: float) -> datetime:
    """When a legacy run happened: its recorded generated_at, else the file's mtime."""
    if isinstance(generated_at, str) and generated_at:
        try:
            dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def _is_uuid(v: Any) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except (TypeError, ValueError):
        return False


async def active_version(db: AsyncSession, company_id: uuid.UUID) -> ValuationVersion | None:
    await import_legacy(db, company_id)
    return (await db.execute(
        select(ValuationVersion)
        .where(ValuationVersion.company_id == company_id, ValuationVersion.status == "active")
        .order_by(ValuationVersion.version_no.desc())
        .limit(1)
    )).scalar_one_or_none()


async def latest_version(db: AsyncSession, company_id: uuid.UUID) -> ValuationVersion | None:
    """Newest version regardless of status — the comp-set lock reads this,
    because a regenerate suspends the active one while it runs."""
    await import_legacy(db, company_id)
    return (await db.execute(
        select(ValuationVersion)
        .where(ValuationVersion.company_id == company_id)
        .order_by(ValuationVersion.version_no.desc())
        .limit(1)
    )).scalar_one_or_none()


async def get_version(db: AsyncSession, company_id: uuid.UUID, version_id: uuid.UUID) -> ValuationVersion | None:
    return (await db.execute(
        select(ValuationVersion).where(ValuationVersion.id == version_id, ValuationVersion.company_id == company_id)
    )).scalar_one_or_none()


async def list_versions(db: AsyncSession, company_id: uuid.UUID) -> list[ValuationVersion]:
    await import_legacy(db, company_id)
    return list((await db.execute(
        select(ValuationVersion)
        .where(ValuationVersion.company_id == company_id)
        .order_by(ValuationVersion.version_no.desc())
    )).scalars().all())


async def suspend_active(db: AsyncSession, company_id: uuid.UUID) -> uuid.UUID | None:
    """Mark the active version superseded while a new run is in flight, so the
    page never offers the stale workpaper mid-regenerate. Returns its id so a
    failed run can reinstate it."""
    current = await active_version(db, company_id)
    if current is None:
        return None
    current.status = "superseded"
    await db.commit()
    return current.id


async def reinstate(db: AsyncSession, company_id: uuid.UUID, version_id: uuid.UUID | None) -> None:
    """Undo suspend_active after a failed run — only if nothing else became active."""
    if version_id is None:
        return
    try:
        await db.rollback()
    except Exception:
        pass
    other = (await db.execute(
        select(ValuationVersion.id).where(
            ValuationVersion.company_id == company_id, ValuationVersion.status == "active"
        ).limit(1)
    )).scalar_one_or_none()
    if other is not None:
        return
    await db.execute(update(ValuationVersion).where(ValuationVersion.id == version_id).values(status="active"))
    await db.commit()


async def record(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    run: dict[str, Any],
    trigger: str,
    note: str | None = None,
    qa_item_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
) -> ValuationVersion:
    """Store a finished run as the new active version. `run` has the shape of
    a summary.json: inputs, summary, warnings, errors, xlsx_filename, xlsx_url,
    report_id. Every other version of the company becomes superseded."""
    await import_legacy(db, company_id)
    if parent_id is None:
        prev = (await db.execute(
            select(ValuationVersion.id)
            .where(ValuationVersion.company_id == company_id)
            .order_by(ValuationVersion.version_no.desc())
            .limit(1)
        )).scalar_one_or_none()
        parent_id = prev
    await db.execute(
        update(ValuationVersion)
        .where(ValuationVersion.company_id == company_id, ValuationVersion.status == "active")
        .values(status="superseded")
    )
    ev, equity = headline(run.get("summary"))
    cu = (run.get("inputs") or {}).get("currency") or {}
    report_id = run.get("report_id")
    version = ValuationVersion(
        company_id=company_id,
        version_no=await _next_version_no(db, company_id),
        parent_id=parent_id,
        status="active",
        trigger=trigger,
        note=note,
        qa_item_id=qa_item_id,
        inputs=run.get("inputs") or {},
        summary=run.get("summary"),
        warnings=run.get("warnings") or [],
        errors=run.get("errors") or [],
        xlsx_filename=run.get("xlsx_filename"),
        xlsx_url=run.get("xlsx_url"),
        report_id=uuid.UUID(str(report_id)) if _is_uuid(report_id) else None,
        ev=ev,
        equity_value=equity,
        currency=cu.get("primary"),
        unit=cu.get("unit"),
        created_by=created_by,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def restore(db: AsyncSession, company_id: uuid.UUID, version_id: uuid.UUID, user_id: uuid.UUID | None) -> ValuationVersion | None:
    """Make an earlier version current again. History is append-only: this
    writes a NEW version (same inputs, summary and workpaper file) rather than
    flipping the old row back, so the list always reads in order."""
    source = await get_version(db, company_id, version_id)
    if source is None:
        return None
    return await record(
        db,
        company_id=company_id,
        run={
            "inputs": source.inputs,
            "summary": source.summary,
            "warnings": source.warnings,
            "errors": source.errors,
            "xlsx_filename": source.xlsx_filename,
            "xlsx_url": source.xlsx_url,
            "report_id": source.report_id,
        },
        trigger="restore",
        note=f"Restored from v{source.version_no}",
        parent_id=source.id,
        created_by=user_id,
    )


def to_payload(v: ValuationVersion) -> dict[str, Any]:
    """The /latest response shape (a summary.json) plus version metadata."""
    return {
        "company_id": str(v.company_id),
        "generated_at": v.created_at.isoformat() if v.created_at else None,
        "xlsx_url": v.xlsx_url,
        "xlsx_filename": v.xlsx_filename,
        "warnings": v.warnings or [],
        "errors": v.errors or [],
        "summary": v.summary,
        "inputs": v.inputs,
        "status": v.status,
        "report_id": str(v.report_id) if v.report_id else None,
        "version_id": str(v.id),
        "version_no": v.version_no,
        "trigger": v.trigger,
        "note": v.note,
    }


def to_list_item(v: ValuationVersion) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "version_no": v.version_no,
        "status": v.status,
        "trigger": v.trigger,
        "trigger_label": TRIGGER_LABELS.get(v.trigger, v.trigger),
        "note": v.note,
        "qa_item_id": str(v.qa_item_id) if v.qa_item_id else None,
        "parent_id": str(v.parent_id) if v.parent_id else None,
        "xlsx_url": v.xlsx_url,
        "xlsx_filename": v.xlsx_filename,
        "report_id": str(v.report_id) if v.report_id else None,
        "ev": v.ev,
        "equity_value": v.equity_value,
        "currency": v.currency,
        "unit": v.unit,
        "error_count": len(v.errors or []),
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }
