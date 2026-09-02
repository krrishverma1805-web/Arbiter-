"""Synthetic reconciliation batch generator (docs/18).

Deterministic given (scenario, records, seed, difficulty). Produces:
  razorpay_recon.csv  bank.csv  ledger.csv  ground_truth.json  manifest.json

For a clean batch (difficulty="easy") the settlement identity holds exactly for
every settlement_utr group:
  bank_credit(utr) == sum(credit) - sum(debit) - sum(fee) - sum(tax)

difficulty in {"easy","normal","hard"} layers the labeled adversarial anomaly
catalog (anomalies.py) on top, recording ground truth for `arbiter bench`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from arbiter_datagen import __version__
from arbiter_datagen.anomalies import BatchCtx, inject, plan
from arbiter_datagen.model import SCENARIOS

_HOLIDAYS_2026 = {
    date(2026, 1, 26),
    date(2026, 3, 6),
    date(2026, 3, 25),
    date(2026, 4, 3),
    date(2026, 4, 14),
    date(2026, 5, 1),
    date(2026, 8, 15),
    date(2026, 10, 2),
}
_PERIOD_START = date(2026, 8, 1)


def _is_working_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _HOLIDAYS_2026


def _add_working_days(d: date, n: int) -> date:
    cur, added = d, 0
    while added < n:
        cur += timedelta(days=1)
        if _is_working_day(cur):
            added += 1
    return cur


def _batch_utr(settled: date, salt: str = "") -> str:
    tag = settled.strftime("%Y%m%d")
    h = hashlib.sha1(f"{tag}{salt}".encode()).hexdigest()[:8].upper()  # noqa: S324 - not security
    return f"RZP{tag}{h}"


def _net_minor(items: list[dict[str, Any]]) -> int:
    return sum(
        int(it["credit"]) - int(it["debit"]) - int(it["fee"]) - int(it["tax"]) for it in items
    )


def generate_dataset(
    *,
    scenario: str,
    records: int,
    seed: int,
    out_dir: str | Path,
    difficulty: str = "normal",
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIOS)}")
    if difficulty not in ("easy", "normal", "hard"):
        raise ValueError("difficulty must be easy | normal | hard")
    sc = SCENARIOS[scenario]
    rng = random.Random(seed)  # noqa: S311 - deterministic synthetic data, not crypto
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    period_end = _PERIOD_START + timedelta(days=sc.period_days - 1)

    n_orders = max(1, records)
    orders: list[dict[str, Any]] = []
    recon_rows: list[dict[str, Any]] = []
    batches: dict[str, dict[str, Any]] = {}

    for i in range(n_orders):
        oid, pid = f"ord_{i:05d}", f"pay_{i:05d}"
        order_rupees = max(
            49.0, round(math.exp(rng.gauss(sc.order_value_mu, sc.order_value_sigma)), 2)
        )
        gross = int(round(order_rupees * 100))
        method = _weighted_choice(rng, sc.method_mix.as_pairs())
        capture_day = _PERIOD_START + timedelta(days=rng.randint(0, sc.period_days - 4))
        settled = _add_working_days(capture_day, 2)
        mdr = sc.upi_flat_fee_paise if method == "upi" else int(round(gross * sc.mdr[method]))
        gst = int(round(mdr * sc.gst_rate))
        utr = _batch_utr(settled)
        batch = batches.setdefault(utr, {"utr": utr, "settled": settled, "items": []})

        orders.append(
            {
                "order_id": oid,
                "order_total": f"{order_rupees:.2f}",
                "order_date": capture_day.isoformat(),
                "customer_name": f"Customer {i % 200:03d}",
            }
        )
        row = {
            "entity_id": pid,
            "type": "payment",
            "debit": "0",
            "credit": str(gross),
            "amount": str(gross),
            "fee": str(mdr),
            "tax": str(gst),
            "currency": "INR",
            "settlement_utr": utr,
            "settlement_id": f"setl_{settled.isoformat()}",
            "created_at": str(
                int(datetime(capture_day.year, capture_day.month, capture_day.day, 10).timestamp())
            ),
            "settled_at": str(
                int(datetime(settled.year, settled.month, settled.day, 5).timestamp())
            ),
            "payment_id": pid,
            "order_id": oid,
            "order_receipt": f"rcpt-{i:05d}",
            "method": method,
            "card_network": "VISA" if method == "card" else "",
            "card_type": "credit" if method == "card" else "",
            "dispute_id": "",
            "description": f"Payment for {oid}",
            "notes": "",
        }
        recon_rows.append(row)
        batch["items"].append(row)

        if rng.random() < sc.refund_rate:
            rgross = int(round(gross * rng.choice([0.5, 1.0])))
            r_settled = _add_working_days(settled, rng.randint(1, 3))
            r_utr = _batch_utr(r_settled)
            r_batch = batches.setdefault(r_utr, {"utr": r_utr, "settled": r_settled, "items": []})
            rrow = {
                **{k: "" for k in row},
                "entity_id": f"rfnd_{i:05d}",
                "type": "refund",
                "debit": str(rgross),
                "credit": "0",
                "amount": str(rgross),
                "fee": "0",
                "tax": "0",
                "currency": "INR",
                "settlement_utr": r_utr,
                "settlement_id": f"setl_{r_settled.isoformat()}",
                "created_at": row["settled_at"],
                "settled_at": str(
                    int(datetime(r_settled.year, r_settled.month, r_settled.day, 5).timestamp())
                ),
                "payment_id": pid,
                "order_id": oid,
                "order_receipt": f"rcpt-{i:05d}",
                "method": method,
                "description": f"Refund for {oid}",
                "notes": "",
            }
            recon_rows.append(rrow)
            r_batch["items"].append(rrow)

    # --- anomaly phase ---
    counts = plan(n_orders, difficulty)
    clean_net = {utr: _net_minor(b["items"]) for utr, b in batches.items()}
    ctx = BatchCtx(
        recon_rows=recon_rows,
        orders=orders,
        batches=batches,
        rng=rng,
        gst_rate=sc.gst_rate,
        period_end_iso=period_end.isoformat(),
        clean_net=clean_net,
    )
    anomalies = inject(ctx, counts)
    dropped_batches = {
        a.settlement_utr for a in anomalies if a.kind in ("TIMING_STRADDLE", "WRONG_ACCT")
    }
    masked_utrs = {a.settlement_utr for a in anomalies if a.kind == "MISSING_UTR"}

    # --- bank credits ---
    bank_rows: list[dict[str, Any]] = []
    true_matches: list[dict[str, Any]] = []
    anomaly_utrs = {a.settlement_utr for a in anomalies if a.settlement_utr}

    # robustness stressor (hard only): garble the UTR in a deterministic ~15% of
    # otherwise-clean narrations. These batches must still auto-tie (via the
    # matcher's amount+date blocking pass) — they stay in true_matches.
    clean_utrs = [u for u in sorted(batches) if u not in anomaly_utrs and u not in dropped_batches]
    mangled_utrs: set[str] = set()
    if difficulty == "hard" and clean_utrs:
        k = max(1, round(len(clean_utrs) * 0.15))
        mangled_utrs = set(rng.sample(clean_utrs, min(k, len(clean_utrs))))

    for utr in sorted(batches):
        b = batches[utr]
        if utr in dropped_batches:
            continue  # timing straddle / wrong account: no credit in this statement
        # FEE_DRIFT/GST_ROUND/DUP_EXPORT: the bank paid the pre-anomaly amount
        net = b.get("bank_override", _net_minor(b["items"]))
        vd: date = b["settled"]
        if utr in masked_utrs:
            narration = "NEFT CR RAZORPAY SOFTWARE PVT LTD"
        elif utr in mangled_utrs:
            narration = f"NEFT CR RAZORPAY SOFTWARE PVT LTD REF {utr[:-4]}{utr[-4:][::-1]}"
        else:
            narration = f"NEFT CR RAZORPAY SOFTWARE PVT LTD UTR {utr}"
        bank_rows.append(
            {
                "amount": f"{net / 100:.2f}",
                "value_date": vd.isoformat(),
                "posted_date": vd.isoformat(),
                "narration": narration,
                "account_no": "XXXXXXXX4021",
            }
        )
        if utr not in anomaly_utrs:
            true_matches.append(
                {
                    "group_id": f"gt_{utr}",
                    "settlement_utr": utr,
                    "bank_value_date": vd.isoformat(),
                    "processor_entity_ids": sorted(it["entity_id"] for it in b["items"]),
                    "ledger_order_ids": sorted(
                        {
                            it["order_id"]
                            for it in b["items"]
                            if it["type"] == "payment" and it["order_id"]
                        }
                    ),
                    "expected_net_minor": net,
                    "clean": True,
                }
            )

    for amt in ctx.orphan_credits:
        vd = _PERIOD_START + timedelta(days=rng.randint(2, sc.period_days - 2))
        bank_rows.append(
            {
                "amount": f"{amt / 100:.2f}",
                "value_date": vd.isoformat(),
                "posted_date": vd.isoformat(),
                "narration": "NEFT CR SUNDRY RECEIPTS",
                "account_no": "XXXXXXXX4021",
            }
        )

    bank_rows.sort(key=lambda r: (r["value_date"], r["amount"]))

    _write_csv(out / "razorpay_recon.csv", recon_rows)
    _write_csv(out / "bank.csv", bank_rows)
    _write_csv(out / "ledger.csv", orders)

    ground_truth = {
        "generator_version": __version__,
        "scenario": scenario,
        "seed": seed,
        "difficulty": difficulty,
        "records": n_orders,
        "period": [_PERIOD_START.isoformat(), period_end.isoformat()],
        "true_matches": true_matches,
        "anomalies": [a.as_dict() for a in anomalies],
    }
    (out / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2, sort_keys=True))

    file_rows = {
        "razorpay_recon.csv": len(recon_rows),
        "bank.csv": len(bank_rows),
        "ledger.csv": len(orders),
    }
    manifest = {
        "generator_version": __version__,
        "scenario": scenario,
        "seed": seed,
        "difficulty": difficulty,
        "records": n_orders,
        "file_rows": file_rows,
        "settlement_batches": len(batches),
        "anomalies_injected": {k: v for k, v in sorted(_count_kinds(ground_truth).items())},
        "dataset_hash": _dataset_hash(out),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def _count_kinds(gt: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in gt["anomalies"]:
        out[a["kind"]] = out.get(a["kind"], 0) + 1
    return out


def _weighted_choice(rng: random.Random, pairs: list[tuple[str, float]]) -> str:
    r = rng.random() * sum(w for _, w in pairs)
    upto = 0.0
    for name, w in pairs:
        upto += w
        if r <= upto:
            return name
    return pairs[-1][0]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fields = list({k for r in rows for k in r})
    fields.sort(key=lambda k: (k not in rows[0], list(rows[0]).index(k) if k in rows[0] else 0))
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def _dataset_hash(out: Path) -> str:
    parts = [
        f"{f.name}:{hashlib.sha256(f.read_bytes()).hexdigest()}" for f in sorted(out.glob("*.csv"))
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
