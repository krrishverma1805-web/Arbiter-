"""Resolve a run request's `spec` / `dataset` strings to on-disk paths.

`dataset` may be a path, a name under `ARBITER_DATASETS_DIR`, or
`"upload:<upload_id>"` referring to a tenant's uploaded files (docs/28 §2).
Shared by the `POST /v1/runs` validation and the worker.
"""

from __future__ import annotations

from pathlib import Path

from arbiter_api.deps import DATASETS_DIR, SPECS_DIR
from arbiter_api.storage import storage


def resolve_spec(spec: str) -> Path | None:
    p = SPECS_DIR / f"{spec}.yaml"
    if p.exists():
        return p
    q = Path(spec)
    return q if q.exists() else None


def resolve_dataset(org_id: str, dataset: str) -> Path | None:
    if dataset.startswith("upload:"):
        return storage.path(org_id, dataset.split(":", 1)[1])
    p = Path(dataset)
    if p.is_dir():
        return p
    q = DATASETS_DIR / dataset
    return q if q.is_dir() else None
