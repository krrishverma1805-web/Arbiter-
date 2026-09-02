"""Tenant-scoped upload storage for source files (docs/28 §2).

`POST /v1/uploads` writes a customer's CSV / XLSX files under
`{ARBITER_UPLOADS_DIR}/{org_id}/{upload_id}/`; a run then references them as
`dataset: "upload:{upload_id}"`. The `Storage` interface is filesystem-backed by
default — an S3/R2 implementation slots in behind the same three methods without
touching the routes.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
from pathlib import Path

UPLOADS_DIR = Path(os.environ.get("ARBITER_UPLOADS_DIR", "data/uploads"))
MAX_FILE_BYTES = int(os.environ.get("ARBITER_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024)))
MAX_FILES = 12
_ALLOWED_SUFFIX = (".csv", ".xlsx", ".xlsm")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class UploadError(ValueError):
    pass


def _safe_name(name: str) -> str:
    base = _SAFE_NAME.sub("_", Path(name).name).strip("._") or "file"
    if not base.lower().endswith(_ALLOWED_SUFFIX):
        raise UploadError(f"{name}: only {', '.join(_ALLOWED_SUFFIX)} files are accepted")
    return base


class Storage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or UPLOADS_DIR

    def save(self, org_id: str, files: list[tuple[str, bytes]]) -> str:
        if not files:
            raise UploadError("no files")
        if len(files) > MAX_FILES:
            raise UploadError(f"at most {MAX_FILES} files per upload")
        upload_id = secrets.token_urlsafe(12)
        dest = self.root / org_id / upload_id
        dest.mkdir(parents=True, exist_ok=True)
        for name, data in files:
            if len(data) > MAX_FILE_BYTES:
                shutil.rmtree(dest, ignore_errors=True)
                raise UploadError(f"{name} exceeds {MAX_FILE_BYTES // 1024 // 1024} MB")
            (dest / _safe_name(name)).write_bytes(data)
        return upload_id

    def path(self, org_id: str, upload_id: str) -> Path | None:
        p = self.root / org_id / _SAFE_NAME.sub("", upload_id)
        return p if p.is_dir() and any(p.iterdir()) else None

    def list_ids(self, org_id: str) -> list[str]:
        base = self.root / org_id
        if not base.is_dir():
            return []
        return sorted(d.name for d in base.iterdir() if d.is_dir())


storage = Storage()
