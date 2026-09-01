"""Clean-batch generator (docs/18 §3).

Deterministic given (scenario, records, seed). Produces:
  razorpay_recon.csv  bank.csv  ledger.csv  ground_truth.json  manifest.json

The settlement identity holds exactly for every batch:
  bank_credit(utr) == sum(credit) - sum(debit) - sum(fee) - sum(tax)

M1 layers the labeled adversarial anomalies on top of this.
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
from arbiter_datagen.model import SCENARIOS

# fixed 2026 India bank-holiday set (weekends handled separately)
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
    cur = d
    added = 0
    while added < n:
        cur += timedelta(days=1)
        if _is_working_day(cur):
            added += 1
    return cur


def _rupees_to_paise(rupees: float) -> int:
    return int(round(rupees * 100))


def generate_dataset(
    *, scenario: str, records: int, seed: int, out_dir: str | Path
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIOS)}")
    sc = SCENARIOS[scenario]
    rng = random.Random(seed)  # noqa: S311 - deterministic synthetic data, not crypto
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    n_orders = max(1, records)
    orders: list[dict[str, Any]] = []
    recon_rows: list[dict[str, Any]] = []
    batches: dict[str, dict[str, Any]] = {}

    for i in range(n_orders):
        oid = f"ord_{i:05d}"
        pid = f"pay_{i:05d}"
        eid = f"pay_{i:05d}"
        order_rupees = math.exp(rng.gauss(sc.order_value_mu, sc.order_value_sigma))
        order_rupees = max(49.0, round(order_rupees, 2))
        gross = _rupees_to_paise(order_rupees)
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
            "entity_id": eid,
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

        # refunds
        if rng.random() < sc.refund_rate:
            rgross = int(round(gross * rng.choice([0.5, 1.0])))
            r_settled = _add_working_days(settled, rng.randint(1, 3))
            r_utr = _batch_utr(r_settled)
            r_batch = batches.setdefault(r_utr, {"utr": r_utr, "settled": r_settled, "items": []})
            rrow = {
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
                "card_network": row["card_network"],
                "card_type": row["card_type"],
                "dispute_id": "",
                "description": f"Refund for {oid}",
                "notes": "",
            }
            recon_rows.append(rrow)
            r_batch["items"].append(rrow)

    # bank credits: one net line per settlement batch
    bank_rows: list[dict[str, Any]] = []
    true_matches: list[dict[str, Any]] = []
    for utr in sorted(batches):
        b = batches[utr]
        net = sum(
            int(it["credit"]) - int(it["debit"]) - int(it["fee"]) - int(it["tax"])
            for it in b["items"]
        )
        value_date: date = b["settled"]
        bank_rows.append(
            {
                "amount": f"{net / 100:.2f}",  # bank statements are in rupees
                "value_date": value_date.isoformat(),
                "posted_date": value_date.isoformat(),
                "narration": f"NEFT CR RAZORPAY SOFTWARE PVT LTD UTR {utr}",
                "account_no": "XXXXXXXX4021",
            }
        )
        true_matches.append(
            {
                "group_id": f"gt_{utr}",
                "settlement_utr": utr,
                "bank_value_date": value_date.isoformat(),
                "processor_entity_ids": [it["entity_id"] for it in b["items"]],
                "ledger_order_ids": sorted(
                    {it["order_id"] for it in b["items"] if it["type"] == "payment"}
                ),
                "expected_net_minor": net,
                "clean": True,
            }
        )

    _write_csv(out / "razorpay_recon.csv", recon_rows)
    _write_csv(out / "bank.csv", bank_rows)
    _write_csv(out / "ledger.csv", orders)

    ground_truth = {
        "generator_version": __version__,
        "scenario": scenario,
        "seed": seed,
        "records": n_orders,
        "period": [
            _PERIOD_START.isoformat(),
            (_PERIOD_START + timedelta(days=sc.period_days - 1)).isoformat(),
        ],
        "true_matches": true_matches,
        "anomalies": [],  # M1
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
        "records": n_orders,
        "file_rows": file_rows,
        "settlement_batches": len(batches),
        "dataset_hash": _dataset_hash(out),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def _weighted_choice(rng: random.Random, pairs: list[tuple[str, float]]) -> str:
    r = rng.random() * sum(w for _, w in pairs)
    upto = 0.0
    for name, w in pairs:
        upto += w
        if r <= upto:
            return name
    return pairs[-1][0]


def _batch_utr(settled: date) -> str:
    tag = settled.strftime("%Y%m%d")
    return f"RZP{tag}{hashlib.sha1(tag.encode()).hexdigest()[:8].upper()}"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _dataset_hash(out: Path) -> str:
    parts = []
    for f in sorted(out.glob("*.csv")):
        parts.append(f"{f.name}:{hashlib.sha256(f.read_bytes()).hexdigest()}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
