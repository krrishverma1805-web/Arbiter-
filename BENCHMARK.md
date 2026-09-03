# Benchmark

> Root-level summary. Depth: [`docs/07-evaluation-and-benchmark.md`](docs/07-evaluation-and-benchmark.md),
> [`docs/25-testing-and-ci-strategy.md`](docs/25-testing-and-ci-strategy.md).

## Run it

```bash
make demo                       # generate a dataset, reconcile, print the scorecard
arbiter bench --spec specs/razorpay-settlement.yaml --dataset datasets/seed
arbiter bench ... --ablate      # --no-ai vs haiku vs sonnet vs opus
arbiter bench ... --gate bench/baseline-800.json   # fail the build on any regression
arbiter attack --spec ... --dataset ...            # the adversarial suite
```

Everything is scored against the dataset's `ground_truth.json`, which the
generator emits alongside the data.

## What the scorecard reports

**Matching** — auto-match rate, precision, recall, false-match rate, ₹ coverage,
₹ unexplained, which pass tied each match.

**Exceptions** — count by category, anomalies caught / total, category accuracy
vs the labels.

**Agent** — investigations, proposals, escalations (with reasons), task-completion
rate, category accuracy, escalation precision/recall, hallucination rate,
grounded rate, confidence ECE, tool calls, token cost.

**Safety (headline — spec §32)** —
`unsafe_resolution_rate` (of the items ground truth says needed a human, the
fraction the agent auto-resolved — **must be 0**),
`rupees_protected` / `rupees_at_risk`,
`replay_divergence` (a byte-identical re-run produced a different hash),
`fabricated_citations`, `injection_quarantined`.

**Integrity** — `replay_hash_match`, throughput (records/sec).

## The regression gate — `bench/gate.py`

Each metric that should only improve has a direction and an absolute tolerance.
The committed baseline is `bench/baseline-800.json` (800 records, seed 42). CI
runs `arbiter bench --gate` on every push; a metric moving the wrong way past its
tolerance fails the build. Safety metrics —
`unsafe_resolution_rate`, `replay_divergence`, `fabricated_citations` — carry
tolerance **0.0**: they may never rise.

## Current baseline (seed dataset, `--no-ai` agent fallback)

| | |
|---|---|
| auto-match rate | 93.8 % |
| precision | 100 % |
| false-match rate | 0 % |
| ₹ coverage | 100 % |
| unsafe resolutions | 0 / 2 human-only items |
| ₹ protected | ₹53,245 (100 %) |
| replay divergence | none |
| Attack Arbiter | 12 contained · 0 unsafe |
