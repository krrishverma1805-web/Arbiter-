"""Review and merge learned rules into a recon spec (docs/02 §5.3).

`pending_rules` reads a run's RULE_DRAFTED events and diffs them against the spec.
`merge_rules` appends the approved rules to the spec YAML with a provenance
comment and bumps the version — a plain text edit a human can review in git.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore


def pending_rules(store: EventStore, run_id: str, spec_path: Path) -> list[dict[str, Any]]:
    spec = yaml.safe_load(spec_path.read_text())
    existing = {r.get("id") for r in spec.get("rules", [])}
    merged = {p["rule_id"] for t, p in store.iter_payloads(run_id) if t == EventType.RULE_MERGED}
    drafts: dict[str, dict[str, Any]] = {}
    for t, p in store.iter_payloads(run_id):
        if t == EventType.RULE_DRAFTED and p["rule_id"] not in existing | merged:
            drafts[p["rule_id"]] = {
                "rule_id": p["rule_id"],
                "when": p["when"],
                "classify": p["classify"],
                "resolve": p["resolve"],
                "provenance_exception_id": p["provenance_exception_id"],
            }
    return list(drafts.values())


def merge_rules(
    store: EventStore,
    run_id: str,
    spec_path: Path,
    rule_ids: list[str] | None,
    *,
    approved_by: str = "human",
) -> dict[str, Any]:
    text = spec_path.read_text()
    spec = yaml.safe_load(text)
    pend = {r["rule_id"]: r for r in pending_rules(store, run_id, spec_path)}
    targets = list(pend.values()) if rule_ids is None else [pend[i] for i in rule_ids if i in pend]
    if not targets:
        return {"merged": [], "version_before": spec["version"], "version_after": spec["version"]}

    before = int(spec["version"])
    after = before + 1

    lines = text.rstrip("\n").splitlines()
    # find the `rules:` block, then the last indented line that belongs to it
    try:
        start = next(i for i, ln in enumerate(lines) if ln.rstrip() == "rules:")
    except StopIteration:
        lines.append("rules:")
        start = len(lines) - 1
    last_rule_line = start
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln.strip() == "":
            continue
        if ln[0].isspace():
            last_rule_line = i
        else:
            break  # a column-0 line (next key or section comment) ends the block

    block: list[str] = []
    for r in targets:
        block.append(
            f"  # learned {r['rule_id']} — from exception {r['provenance_exception_id']} "
            f"(reviewed by {approved_by})"
        )
        block.append(f"  - id: {r['rule_id']}")
        block.append(f"    when: {json.dumps(r['when'])}")
        block.append(f"    classify: {r['classify']}")
        block.append(f"    resolve: {r['resolve']}")
    insert_at = last_rule_line + 1
    new_lines = lines[:insert_at] + block + lines[insert_at:]
    new_text = "\n".join(new_lines) + "\n"
    new_text = new_text.replace(f"version: {before}", f"version: {after}", 1)
    spec_path.write_text(new_text)

    for r in targets:
        store.append(
            run_id,
            EventType.RULE_MERGED,
            {
                "rule_id": r["rule_id"],
                "spec_version_before": before,
                "spec_version_after": after,
                "approved_by": approved_by,
            },
        )
    return {
        "merged": [r["rule_id"] for r in targets],
        "version_before": before,
        "version_after": after,
    }
