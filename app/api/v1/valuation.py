"""Valuation workpaper generation endpoint."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.agent.context import AgentContext
from app.services.agent.registry import registry
from app.services.agent.skill import SkillStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/companies/{company_id}/valuation",
    tags=["valuation"],
)


def _valuations_dir() -> Path:
    return (Path(settings.UPLOAD_DIR).resolve() / "valuations")


def _latest_summary_for(company_id: UUID) -> dict | None:
    """Find the most recent ACTIVE .summary.json belonging to this company.

    Files are named `valuation-{slug}-{DDMMYYYY}.summary.json` (no UUID in
    the filename), so we glob all summaries and filter by the `company_id`
    field stored inside each one. Eric 2026-05-19 — only summaries with
    `status: "active"` are returned (or summaries without a status field,
    for backward compat with pre-status runs). Superseded runs are filtered
    out so a mid-regenerate user can't download stale data thinking it's
    the new run.
    """
    d = _valuations_dir()
    if not d.exists():
        return None
    cid = str(company_id)
    candidates: list[tuple[float, dict]] = []
    for p in d.glob("valuation-*.summary.json"):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("company_id") != cid:
            continue
        # Eric 2026-05-19 — status filter. Default to "active" for legacy
        # summaries without the field so pre-existing runs still surface.
        status = data.get("status", "active")
        if status != "active":
            continue
        candidates.append((p.stat().st_mtime, data))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _active_summary_path_for(company_id: UUID) -> Path | None:
    """Return the on-disk path of the current active summary for a company,
    or None if none exist. Used by /generate-workpaper to flip the previous
    run to "superseded" before kicking off a new run."""
    d = _valuations_dir()
    if not d.exists():
        return None
    cid = str(company_id)
    candidates: list[tuple[float, Path]] = []
    for p in d.glob("valuation-*.summary.json"):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("company_id") != cid:
            continue
        status = data.get("status", "active")
        if status != "active":
            continue
        candidates.append((p.stat().st_mtime, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _set_summary_status(path: Path, status: str) -> None:
    """In-place edit a summary.json's status field. Used to flip active ↔
    superseded around /generate-workpaper invocations. Silently no-ops on
    read/write errors so a corrupted summary file doesn't block a regen."""
    try:
        data = json.loads(path.read_text())
        data["status"] = status
        path.write_text(json.dumps(data, default=str))
    except (OSError, json.JSONDecodeError):
        pass


class GenerateWorkpaperRequest(BaseModel):
    """Per-valuation run-config knobs supplied by the user at Generate/Regenerate time."""
    target_valuation: float | None = None  # Eric 2026-05-08 item 1; actual currency units
    valuation_date: str | None = None  # Eric 2026-05-08 item 6; ISO date string (YYYY-MM-DD)


@router.post("/generate-workpaper")
async def generate_workpaper(
    company_id: UUID,
    body: GenerateWorkpaperRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate the populated Excel valuation workpaper for a company.

    Pipeline:
      1. produce_valuation_inputs — Claude reads extracted documents and produces
         JSON conforming to the inputs-sheet schema.
      2. export_workpaper — fills the v1 skeleton xlsx from the JSON, validates,
         writes to {UPLOAD_DIR}/valuations/.

    Returns the download URL plus any validation warnings.
    """
    skill = registry.get("generate_valuation_workpaper")
    if skill is None:
        raise HTTPException(
            status_code=500,
            detail="generate_valuation_workpaper skill not registered",
        )

    ctx = AgentContext(db=db, company_id=company_id, user_id=user.id)
    target_valuation = body.target_valuation if body else None
    valuation_date = body.valuation_date if body else None

    # Eric 2026-05-19 — flip the previous active summary to "superseded"
    # BEFORE invoking the skill. While the producer is running, /latest
    # returns 404 → frontend can't render the stale workpaper or surface a
    # Download button pointing at the old xlsx. If the skill fails, we
    # restore the previous summary to active so the user retains access to
    # the last good run.
    prev_active_path = _active_summary_path_for(company_id)
    if prev_active_path is not None:
        _set_summary_status(prev_active_path, "superseded")

    try:
        result = await skill.execute(
            ctx,
            target_valuation=target_valuation,
            valuation_date=valuation_date,
        )
    except Exception:
        if prev_active_path is not None:
            _set_summary_status(prev_active_path, "active")
        raise

    if result.status == SkillStatus.FAILED:
        if prev_active_path is not None:
            _set_summary_status(prev_active_path, "active")
        logger.error(
            "generate-workpaper FAILED for company=%s target_valuation=%s valuation_date=%s: %s | artifacts=%s",
            company_id, target_valuation, valuation_date, result.message,
            {k: type(v).__name__ for k, v in (result.artifacts or {}).items()},
        )
        raise HTTPException(status_code=500, detail=result.message)

    payload = result.data or {}
    return {
        "status": result.status.value,
        "message": result.message,
        "xlsx_url": payload.get("xlsx_url"),
        "warnings": payload.get("warnings", []),
        "errors": payload.get("errors", []),
        "summary": payload.get("summary"),
    }


@router.get("/latest")
async def latest_workpaper(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the most-recent generated workpaper summary for this company.

    Reads the .summary.json file written alongside each xlsx in
    {UPLOAD_DIR}/valuations/. Returns 404 if no workpaper has been generated.
    """
    summary = _latest_summary_for(company_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="No valuation workpaper generated yet")
    return summary


@router.post("/values-only")
async def generate_values_only(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a values-only copy of the active workpaper for external
    circulation: all formulas converted to hard-coded values, formatting and
    layout preserved, and model internals (hidden inputs sheet, helper sheets,
    named ranges) stripped so recipients see only static numbers.

    Requires computed cell values — LibreOffice headless recalc when available,
    else the workbook's cached values (present after an analyst opens+saves the
    file in Excel and re-uploads it). 409 when neither source exists."""
    summary = _latest_summary_for(company_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="No valuation workpaper generated yet")
    xlsx_name = summary.get("xlsx_filename")
    if not xlsx_name:
        raise HTTPException(status_code=404, detail="Active workpaper has no xlsx file")
    src = _valuations_dir() / xlsx_name
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Workpaper file missing: {xlsx_name}")

    dst = src.with_name(src.stem + "-values-only.xlsx")
    # valuation module is importable via the path bootstrap in the workpaper
    # skill; reuse it so this endpoint works in slim deploys too.
    import sys as _sys
    from app.services.agent.skills.generate_valuation_workpaper import _VAL_DIR
    if str(_VAL_DIR) not in _sys.path:
        _sys.path.insert(0, str(_VAL_DIR))
    from export_workpaper import export_values_only  # type: ignore

    ok, message = export_values_only(src, dst)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {
        "status": "success",
        "message": message,
        "xlsx_url": f"/uploads/valuations/{dst.name}",
        "xlsx_filename": dst.name,
    }


@router.post("/regenerate-from-inputs")
async def regenerate_from_inputs(
    company_id: UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Regenerate the workpaper from a user-edited Inputs JSON payload.

    Eric 2026-05-08 item 8: round-trip support. After downloading the inputs
    JSON, hand-adjusting it offline (e.g. tweaking growth rates, swapping
    comps, overriding WACC), the user POSTs the edited JSON here. The pipeline
    skips the LLM producer step and runs the rest of the export pipeline on
    the supplied inputs.

    Body: the raw inputs JSON object (same shape as inputs-sheet-schema.md).
    """
    # Validate before doing any expensive work — fail fast with the Pydantic
    # error list so the analyst can fix the file and retry.
    from app.services.agent.skills.valuation_inputs_schema import (
        validate as validate_inputs,
    )
    model, error = validate_inputs(payload)
    if model is None:
        raise HTTPException(
            status_code=400,
            detail=f"Uploaded inputs failed schema validation:\n{error}",
        )

    skill = registry.get("generate_valuation_workpaper")
    if skill is None:
        raise HTTPException(
            status_code=500,
            detail="generate_valuation_workpaper skill not registered",
        )

    ctx = AgentContext(db=db, company_id=company_id, user_id=user.id)

    prev_active_path = _active_summary_path_for(company_id)
    if prev_active_path is not None:
        _set_summary_status(prev_active_path, "superseded")

    try:
        result = await skill.execute(ctx, inputs=payload)
    except Exception:
        if prev_active_path is not None:
            _set_summary_status(prev_active_path, "active")
        raise

    if result.status == SkillStatus.FAILED:
        if prev_active_path is not None:
            _set_summary_status(prev_active_path, "active")
        logger.error(
            "regenerate-from-inputs FAILED for company=%s: %s",
            company_id, result.message,
        )
        raise HTTPException(status_code=500, detail=result.message)

    out = result.data or {}
    return {
        "status": result.status.value,
        "message": result.message,
        "xlsx_url": out.get("xlsx_url"),
        "warnings": out.get("warnings", []),
        "errors": out.get("errors", []),
        "summary": out.get("summary"),
    }


@router.post("/regenerate-from-xlsx")
async def regenerate_from_xlsx(
    company_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Regenerate the workpaper from a user-edited xlsx workpaper.

    Eric 2026-05-08 item 8 — high-fidelity xlsx round-trip. The pipeline parses
    the visible Inputs sheet cell-by-cell back into the inputs JSON (overlaying
    a baseline copy stashed in the hidden `_meta` sheet so fields not rendered
    in the visible UI — rationales, sources, comp-row metadata — survive the
    round-trip). Then validates against the Pydantic schema and runs the
    standard export pipeline.

    The uploaded file should be an xlsx originally produced by this platform.
    """
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload must be an .xlsx file")

    # Persist the upload to a tmp path because openpyxl reads from disk.
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        # Parse via the standalone module that lives alongside compute.py +
        # export_workpaper.py. The skills package puts that dir on sys.path on
        # import; this endpoint is reached after the app has started so the
        # path is already in place.
        try:
            from parse_workpaper import parse as parse_xlsx  # type: ignore
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"Parser unavailable: {e}")
        try:
            payload = parse_xlsx(tmp_path)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not parse the uploaded xlsx: {type(e).__name__}: {e}",
            )
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    # Validate the reconstructed payload before doing any expensive work.
    from app.services.agent.skills.valuation_inputs_schema import (
        validate as validate_inputs,
    )
    model, error = validate_inputs(payload)
    if model is None:
        raise HTTPException(
            status_code=400,
            detail=f"Parsed inputs failed schema validation:\n{error}",
        )

    skill = registry.get("generate_valuation_workpaper")
    if skill is None:
        raise HTTPException(
            status_code=500,
            detail="generate_valuation_workpaper skill not registered",
        )

    ctx = AgentContext(db=db, company_id=company_id, user_id=user.id)

    prev_active_path = _active_summary_path_for(company_id)
    if prev_active_path is not None:
        _set_summary_status(prev_active_path, "superseded")

    try:
        result = await skill.execute(ctx, inputs=payload)
    except Exception:
        if prev_active_path is not None:
            _set_summary_status(prev_active_path, "active")
        raise

    if result.status == SkillStatus.FAILED:
        if prev_active_path is not None:
            _set_summary_status(prev_active_path, "active")
        logger.error(
            "regenerate-from-xlsx FAILED for company=%s: %s",
            company_id, result.message,
        )
        raise HTTPException(status_code=500, detail=result.message)

    out = result.data or {}
    return {
        "status": result.status.value,
        "message": result.message,
        "xlsx_url": out.get("xlsx_url"),
        "warnings": out.get("warnings", []),
        "errors": out.get("errors", []),
        "summary": out.get("summary"),
        "parsed_inputs": payload,
    }


@router.post("/produce-inputs")
async def produce_inputs(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Produce the valuation inputs JSON without writing an xlsx.

    Useful for previewing what the AI extracted before committing to a workpaper.
    """
    skill = registry.get("produce_valuation_inputs")
    if skill is None:
        raise HTTPException(
            status_code=500,
            detail="produce_valuation_inputs skill not registered",
        )

    ctx = AgentContext(db=db, company_id=company_id, user_id=user.id)
    result = await skill.execute(ctx)

    if result.status == SkillStatus.FAILED:
        raise HTTPException(status_code=500, detail=result.message)

    return {
        "status": result.status.value,
        "message": result.message,
        "inputs_json": result.data,
        "usage": result.artifacts.get("usage", {}),
    }
