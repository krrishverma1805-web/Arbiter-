#!/usr/bin/env bash
# Regenerate the hosted-demo snapshot (web/src/lib/demo/*.json) from a live API.
#   ARBITER_API=http://127.0.0.1:8000 RID=<run-id> scripts/snapshot.sh
# The run should be a completed reconciliation — ideally one that exercised the
# investigation agent (ARBITER_LLM_PROVIDER=openai or an ANTHROPIC_API_KEY).
set -euo pipefail
API="${ARBITER_API:-http://127.0.0.1:8000}"
RID="${RID:?set RID to the run id}"
OUT="$(cd "$(dirname "$0")/.." && pwd)/web/src/lib/demo"
mkdir -p "$OUT"

curl -sf "$API/v1/specs"                > "$OUT/specs.json"
curl -sf "$API/v1/datasets"             > "$OUT/datasets.json"
curl -sf "$API/v1/runs"                 > "$OUT/runs.json"
curl -sf "$API/v1/runs/$RID"            > "$OUT/run.json"
curl -sf "$API/v1/runs/$RID/scorecard"  > "$OUT/scorecard.json"
curl -sf "$API/v1/runs/$RID/exceptions" > "$OUT/exceptions.json"
curl -sf "$API/v1/runs/$RID/verify"     > "$OUT/verify.json"

python3 - "$API" "$RID" "$OUT" <<'PY'
import json, sys, urllib.request
api, rid, out = sys.argv[1:4]
ex = json.load(open(f"{out}/exceptions.json"))
KEEP = {"id","source","kind","amount_minor","amount_display","currency","reference",
        "counterparty","value_date","posted_date","settled_at"}
drawers = {}
for e in ex["exceptions"]:
    d = json.load(urllib.request.urlopen(f"{api}/v1/exceptions/{rid}/{e['id']}"))
    recs = d.get("records", [])
    d["records"] = [
        {**{k: r[k] for k in KEEP if k in r},
         "external_ids": {k: (r.get("external_ids") or {}).get(k)
                          for k in ("settlement_utr","order_id","payment_id")
                          if (r.get("external_ids") or {}).get(k)}}
        for r in recs[:10]
    ]
    d["_record_total"] = len(recs)
    drawers[e["id"]] = d
json.dump(drawers, open(f"{out}/drawers.json", "w"))

# SSE stream → keep the meaningful frames, collapse RECORD_INGESTED to a count
import subprocess
raw = subprocess.run(["curl","-sN","--max-time","25",f"{api}/v1/runs/{rid}/stream"],
                     capture_output=True, text=True).stdout
frames, buf = [], []
for line in raw.splitlines():
    if line.startswith("data:"):
        buf.append(line[5:].lstrip())
    elif not line and buf:
        try: frames.append(json.loads("".join(buf)))
        except Exception: pass
        buf = []
records = sum(1 for f in frames if f.get("type") == "RECORD_INGESTED")
keep = [f for f in frames if f.get("type") and f["type"] != "RECORD_INGESTED"]
json.dump({"records": records, "frames": keep}, open(f"{out}/stream.json", "w"))
print(f"snapshot: {ex['total']} exceptions, {len(keep)} stream frames, {records} records")
PY
