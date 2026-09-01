from __future__ import annotations

from pathlib import Path

import yaml

from arbiter_engine.hashing import canonical_json, sha256_hex
from arbiter_engine.specs.model import ReconSpec


class SpecError(ValueError):
    """A recon spec failed to load or validate."""


def load_spec(path: str | Path) -> ReconSpec:
    p = Path(path)
    if not p.exists():
        raise SpecError(f"spec not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise SpecError(f"spec is not valid YAML ({p}): {exc}") from exc
    try:
        return ReconSpec.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        raise SpecError(f"spec {p} is invalid: {exc}") from exc


def spec_hash(spec: ReconSpec) -> str:
    """Stable hash of the spec's semantic content (docs/17 §7)."""
    return sha256_hex(canonical_json(spec.model_dump(mode="json")))[:16]
