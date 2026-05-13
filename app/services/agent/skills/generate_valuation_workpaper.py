"""Skill: chain produce_valuation_inputs → export_workpaper to produce the
populated xlsx. Returns a downloadable URL.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def _slugify(name: str) -> str:
    """Make a filename-safe slug from a company name. Lowercase, kebab-case,
    ASCII-only. Empty input falls back to 'company'."""
    if not name:
        return "company"
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "company"

from app.config import settings
from app.services.agent.context import AgentContext
from app.services.agent.registry import registry
from app.services.agent.skill import Skill, SkillResult, SkillStatus


# Resolve from backend/ root (parents[4]) so paths hold in deploys that ship
# only the backend tree. materials/templates/ and the valuation/ module both
# live inside backend/ now — see also produce_valuation_inputs.py.
BACKEND_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SKELETON = BACKEND_ROOT / "materials" / "templates" / "orionmano-valuation-template-v1.xlsx"

# Make the standalone valuation module importable
_VAL_DIR = BACKEND_ROOT / "valuation"
if str(_VAL_DIR) not in sys.path:
    sys.path.insert(0, str(_VAL_DIR))


class GenerateValuationWorkpaperSkill(Skill):
    name = "generate_valuation_workpaper"
    description = (
        "Generate a populated valuation workpaper (xlsx) for the company. "
        "Chains produce_valuation_inputs → export_workpaper. Returns a downloadable URL."
    )
    parameters = []

    async def execute(self, ctx: AgentContext, **kwargs: Any) -> SkillResult:
        # 1a. If the caller passed an explicit `inputs` payload (user-edited JSON
        # re-uploaded after a prior run — Eric 2026-05-08 item 8), skip the LLM
        # producer entirely and use the uploaded inputs verbatim. The endpoint
        # should have validated against the schema before passing them in.
        inputs_override = kwargs.get("inputs")
        producer_token_usage = 0
        if inputs_override is not None:
            if not isinstance(inputs_override, dict):
                return SkillResult.failed("Override inputs must be a JSON object")
            payload = inputs_override
        else:
            # 1b. Standard path: produce inputs JSON via the producer skill.
            producer = registry.get("produce_valuation_inputs")
            if producer is None:
                return SkillResult.failed("produce_valuation_inputs skill not registered")

            # Forward per-valuation run-config kwargs (e.g. target_valuation from
            # the UI run-config box) so the producer can inject them into the LLM
            # context and authoritatively override the payload after validation.
            producer_result = await producer.execute(ctx, **kwargs)
            if producer_result.status != SkillStatus.SUCCESS:
                return SkillResult.failed(
                    f"Producer skill failed: {producer_result.message}",
                    data=producer_result.data,
                )
            payload = producer_result.data
            if not isinstance(payload, dict):
                return SkillResult.failed("Producer skill returned non-dict payload")
            producer_token_usage = producer_result.token_usage

        # 2. Resolve output path under the configured upload dir, exposed at /uploads/...
        upload_root = Path(settings.UPLOAD_DIR).resolve()
        out_dir = upload_root / "valuations"
        out_dir.mkdir(parents=True, exist_ok=True)

        company_name = getattr(ctx.company, "name", None) if ctx.company else None
        slug = _slugify(company_name or "")
        date_str = datetime.utcnow().strftime("%d%m%Y")
        # If multiple workpapers in one day, suffix with -2, -3, etc. so we
        # never overwrite earlier runs.
        base = f"valuation-{slug}-{date_str}"
        output_path = out_dir / f"{base}.xlsx"
        n = 2
        while output_path.exists():
            output_path = out_dir / f"{base}-{n}.xlsx"
            n += 1

        # 3. Run the export pipeline
        # Skeleton may not exist yet — build_skeleton.py auto-builds when missing
        if not DEFAULT_SKELETON.exists():
            try:
                from build_skeleton import build as build_skeleton  # type: ignore
                build_skeleton()
            except Exception as e:
                return SkillResult.failed(f"Failed to build skeleton: {e}")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(payload, f)
            json_path = Path(f.name)

        try:
            from export_workpaper import export  # type: ignore
            vr = export(json_path, DEFAULT_SKELETON, output_path)
        except FileNotFoundError as e:
            return SkillResult.failed(f"Export pipeline missing file: {e}")
        except Exception as e:
            return SkillResult.failed(f"Export failed: {type(e).__name__}: {e}")
        finally:
            json_path.unlink(missing_ok=True)

        # Compute summary + persist alongside the xlsx so the dashboard endpoint
        # can fetch the latest run without rerunning Claude.
        summary: dict[str, Any] | None = None
        summary_path: Path | None = None
        summary_payload: dict[str, Any] | None = None
        try:
            from compute import compute_summary  # type: ignore
            summary = compute_summary(payload)
            summary_payload = {
                "company_id": str(ctx.company_id) if ctx.company_id else None,
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "xlsx_url": f"/uploads/valuations/{output_path.name}",
                "xlsx_filename": output_path.name,
                "warnings": vr.warnings,
                "errors": vr.errors,
                "summary": summary,
                "inputs": payload,
            }
            summary_path = output_path.with_suffix(".summary.json")
            summary_path.write_text(json.dumps(summary_payload, default=str))
        except Exception as e:
            # Summary failure shouldn't block the workpaper download
            summary = {"error": f"Summary computation failed: {type(e).__name__}: {e}"}

        # Eric 2026-05-13 — every workpaper deliverable must be accompanied by a
        # written report explaining its assumptions and inputs. Create the
        # Report row + schedule background generation; the report reads the
        # .summary.json we just wrote for its authoritative context. Wrapped in
        # try/except so a Report-creation failure doesn't fail the workpaper.
        report_id: str | None = None
        if (
            getattr(ctx, "db", None) is not None
            and getattr(ctx, "company_id", None) is not None
            and getattr(ctx, "user_id", None) is not None
            and summary is not None
            and not (isinstance(summary, dict) and "error" in summary)
        ):
            try:
                from app.models.report import Report
                tier = getattr(ctx.company, "report_tier", None) or "standard"
                company_name = getattr(ctx.company, "name", None) or "Valuation"
                report = Report(
                    company_id=ctx.company_id,
                    report_type="valuation_report",
                    tier=tier,
                    title=f"{company_name} — Valuation Report",
                    status="pending",
                    created_by=ctx.user_id,
                )
                ctx.db.add(report)
                await ctx.db.commit()
                await ctx.db.refresh(report)
                report_id = str(report.id)

                # Surface the linked report in the .summary.json so the dashboard
                # can render a 'View Report' link bound to this workpaper run.
                if summary_payload is not None and summary_path is not None:
                    summary_payload["report_id"] = report_id
                    summary_path.write_text(json.dumps(summary_payload, default=str))

                # Schedule generation on a fresh DB session so the bg task isn't
                # tied to the request-scoped session lifetime.
                rid_uuid = report.id
                cid_uuid = ctx.company_id
                async def _kickoff_report() -> None:
                    from app.database import async_session
                    from app.services.report.generator import generate_report_bg
                    try:
                        async with async_session() as session:
                            await generate_report_bg(
                                session, cid_uuid, "valuation_report", rid_uuid,
                            )
                    except Exception:
                        # Bg task failures shouldn't crash the worker; the Report
                        # row's status will reflect the failure if the generator
                        # got far enough to set it.
                        pass
                asyncio.create_task(_kickoff_report())
            except Exception:
                # Reset the session state if the Report-row write failed mid-flight
                try:
                    await ctx.db.rollback()
                except Exception:
                    pass
                report_id = None

        if vr.errors:
            return SkillResult(
                status=SkillStatus.PARTIAL,
                data={
                    "xlsx_path": str(output_path),
                    "xlsx_url": f"/uploads/valuations/{output_path.name}",
                    "errors": vr.errors,
                    "warnings": vr.warnings,
                    "inputs_json": payload,
                    "summary": summary,
                    "report_id": report_id,
                },
                message=(
                    f"Workpaper generated with {len(vr.errors)} validation errors "
                    f"and {len(vr.warnings)} warnings"
                ),
                artifacts={"xlsx_path": str(output_path), "valuation_inputs": payload},
                token_usage=producer_token_usage,
            )

        return SkillResult.success(
            data={
                "xlsx_path": str(output_path),
                "xlsx_url": f"/uploads/valuations/{output_path.name}",
                "warnings": vr.warnings,
                "inputs_json": payload,
                "summary": summary,
                "report_id": report_id,
            },
            message=(
                f"Workpaper generated at {output_path.name} "
                f"({len(vr.warnings)} warnings)"
                + (f"; written report {report_id} kicked off" if report_id else "")
            ),
            artifacts={"xlsx_path": str(output_path), "valuation_inputs": payload},
        )
