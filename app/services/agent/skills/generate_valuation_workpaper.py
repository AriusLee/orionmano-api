"""Skill: chain produce_valuation_inputs → export_workpaper to produce the
populated xlsx. Returns a downloadable URL.
"""

from __future__ import annotations

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


REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_SKELETON = REPO_ROOT / "materials" / "templates" / "orionmano-valuation-template-v1.xlsx"

# Make the standalone valuation module importable
_VAL_DIR = REPO_ROOT / "backend" / "valuation"
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
        # 1. Produce inputs JSON via the producer skill
        producer = registry.get("produce_valuation_inputs")
        if producer is None:
            return SkillResult.failed("produce_valuation_inputs skill not registered")

        producer_result = await producer.execute(ctx)
        if producer_result.status != SkillStatus.SUCCESS:
            return SkillResult.failed(
                f"Producer skill failed: {producer_result.message}",
                data=producer_result.data,
            )
        payload = producer_result.data
        if not isinstance(payload, dict):
            return SkillResult.failed("Producer skill returned non-dict payload")

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
                },
                message=(
                    f"Workpaper generated with {len(vr.errors)} validation errors "
                    f"and {len(vr.warnings)} warnings"
                ),
                artifacts={"xlsx_path": str(output_path), "valuation_inputs": payload},
                token_usage=producer_result.token_usage,
            )

        return SkillResult.success(
            data={
                "xlsx_path": str(output_path),
                "xlsx_url": f"/uploads/valuations/{output_path.name}",
                "warnings": vr.warnings,
                "inputs_json": payload,
                "summary": summary,
            },
            message=(
                f"Workpaper generated at {output_path.name} "
                f"({len(vr.warnings)} warnings)"
            ),
            artifacts={"xlsx_path": str(output_path), "valuation_inputs": payload},
        )
