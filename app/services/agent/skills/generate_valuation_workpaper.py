"""Skill: chain produce_valuation_inputs → export_workpaper to produce the
populated xlsx. Returns a downloadable URL.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

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

        company_id = str(ctx.company_id) if ctx.company_id else "anon"
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        output_path = out_dir / f"valuation-{company_id}-{timestamp}.xlsx"

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

        if vr.errors:
            return SkillResult(
                status=SkillStatus.PARTIAL,
                data={
                    "xlsx_path": str(output_path),
                    "xlsx_url": f"/uploads/valuations/{output_path.name}",
                    "errors": vr.errors,
                    "warnings": vr.warnings,
                    "inputs_json": payload,
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
            },
            message=(
                f"Workpaper generated at {output_path.name} "
                f"({len(vr.warnings)} warnings)"
            ),
            artifacts={"xlsx_path": str(output_path), "valuation_inputs": payload},
        )
