"""A pinned snapshot of the public API surface (docs/28 §2 item 8).

`openapi-surface.json` is the committed contract — every path and its methods.
This test fails the build when a route is added, removed, or changes verb, so an
API change is always a deliberate, reviewed diff (regenerate with
`python -m tests.regen_openapi` — see the helper at the bottom).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_SNAPSHOT = Path(__file__).parent / "openapi-surface.json"


def _current_surface() -> dict:
    os.environ.setdefault("ARBITER_DB_URL", "sqlite://")
    from arbiter_api.app import app

    spec = app.openapi()
    paths = {p: sorted(m.upper() for m in methods) for p, methods in sorted(spec["paths"].items())}
    return {"openapi": spec["openapi"], "paths": paths}


def test_api_surface_matches_the_committed_snapshot():
    committed = json.loads(_SNAPSHOT.read_text())
    current = _current_surface()
    assert current == committed, (
        "the API surface changed — if intentional, regenerate "
        "packages/api/tests/openapi-surface.json:\n"
        f"  added:   {sorted(set(current['paths']) - set(committed['paths']))}\n"
        f"  removed: {sorted(set(committed['paths']) - set(current['paths']))}"
    )


if __name__ == "__main__":  # regenerate the snapshot
    _SNAPSHOT.write_text(json.dumps(_current_surface(), indent=2) + "\n")
    print(f"wrote {_SNAPSHOT}")
