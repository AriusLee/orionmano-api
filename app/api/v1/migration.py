"""TEMPORARY uploads-disk migration endpoints (2026-07-23).

Purpose: copy the uploads persistent disk from the old native-runtime Render
service to the new Docker service. Render disks are single-attach block
devices, and Render's SSH auth was rejecting registered keys, so the copy runs
through the app itself: the new service pulls every file from the old
service's public /uploads static mount, using an authenticated manifest.

Remove this module (and its router wiring) once the migration is verified.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.config import settings
from app.models.user import User

router = APIRouter(prefix="/migration", tags=["migration"])


def _uploads_root() -> Path:
    return Path(settings.UPLOAD_DIR).resolve()


@router.get("/uploads-manifest")
async def uploads_manifest(user: User = Depends(get_current_user)):
    """Every file under UPLOAD_DIR with size + md5 (for copy verification)."""
    root = _uploads_root()
    files = []
    total = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        data_size = p.stat().st_size
        total += data_size
        files.append({
            "path": str(p.relative_to(root)),
            "size": data_size,
            "md5": hashlib.md5(p.read_bytes()).hexdigest() if data_size < 50_000_000 else None,
        })
    return {"root": str(root), "count": len(files), "total_bytes": total, "files": files}


class PullRequest(BaseModel):
    source_base: str          # e.g. https://orionmano-api.onrender.com
    source_token: str         # bearer token valid on the source service
    overwrite: bool = False   # skip files that already exist with matching size unless True


@router.post("/uploads-pull")
async def uploads_pull(req: PullRequest, user: User = Depends(get_current_user)):
    """Pull every file in the source service's manifest into this service's
    UPLOAD_DIR via the source's static /uploads mount."""
    base = req.source_base.rstrip("/")
    mreq = urllib.request.Request(
        f"{base}/api/v1/migration/uploads-manifest",
        headers={"Authorization": f"Bearer {req.source_token}"},
    )
    try:
        import json
        with urllib.request.urlopen(mreq, timeout=60) as r:
            manifest = json.load(r)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Manifest fetch failed: {e}")

    root = _uploads_root()
    copied, skipped, errors = 0, 0, []
    for entry in manifest.get("files", []):
        rel = entry["path"]
        # Path-traversal guard: resolved destination must stay inside root.
        dst = (root / rel).resolve()
        if not str(dst).startswith(str(root)):
            errors.append(f"{rel}: path escapes uploads root, skipped")
            continue
        if dst.exists() and dst.stat().st_size == entry["size"] and not req.overwrite:
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        url = f"{base}/uploads/" + urllib.request.quote(rel)
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                dst.write_bytes(r.read())
            if dst.stat().st_size != entry["size"]:
                errors.append(f"{rel}: size mismatch after copy")
            else:
                copied += 1
        except Exception as e:
            errors.append(f"{rel}: {e}")
    return {
        "source_count": manifest.get("count"),
        "copied": copied,
        "skipped": skipped,
        "errors": errors[:20],
        "error_count": len(errors),
    }
