"""`arbiter` CLI (docs/06 L, docs/20 §1).

M0 commands: gen (delegates to datagen), run, replay, verify, events.
M1+ adds: bench, explain, memo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from arbiter_engine.bench import score_run
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import ChainBroken, EventStore
from arbiter_engine.replay import replay as do_replay
from arbiter_engine.run import RunInputs, execute

app = typer.Typer(add_completion=False, help="Arbiter — a verification layer for money movement.")

DEFAULT_DB = os.environ.get("ARBITER_DB_URL", "sqlite:///./data/arbiter.db")


def _store(db: str | None = None) -> EventStore:
    url = db or DEFAULT_DB
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return EventStore(url)


@app.command()
def run(
    spec: Path = typer.Option(..., "--spec", help="path to a recon spec YAML"),
    dataset: Path = typer.Option(..., "--dataset", help="directory with the source CSVs"),
    no_ai: bool = typer.Option(False, "--no-ai", help="deterministic core only, zero LLM calls"),
    seed: int | None = typer.Option(None, "--seed"),
    resume: bool = typer.Option(False, "--resume", help="continue a crashed / interrupted run"),
    rerun: bool = typer.Option(False, "--rerun", help="discard and re-run even if completed"),
    db: str | None = typer.Option(None, "--db"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run a reconciliation over a dataset."""
    store = _store(db)
    proj = execute(
        store,
        RunInputs(
            spec_path=spec,
            dataset_dir=dataset,
            no_ai=no_ai,
            seed=seed,
            resume=resume,
            rerun=rerun,
        ),
    )
    verify = store.verify(proj.run_id)
    payload = {
        "run_id": proj.run_id,
        "status": proj.status,
        "records": proj.record_count,
        "by_source": proj.by_source(),
        "matches": len(proj.matches),
        "matched_records": len(proj.matched_record_ids),
        "exceptions": len(proj.exceptions),
        "quarantined": proj.quarantined,
        "pii_dropped": proj.pii_dropped,
        "events": verify["events"],
        "terminal_hash": verify["terminal_hash"],
    }
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(f"run {proj.run_id}  [{proj.status}]")
    typer.echo(f"  records ingested : {proj.record_count}")
    for src, n in sorted(proj.by_source().items()):
        typer.echo(f"    {src:<20} {n}")
    if proj.quarantined:
        typer.echo(f"  quarantined rows : {proj.quarantined}")
    if proj.pii_dropped:
        typer.echo(f"  PII dropped      : {proj.pii_dropped}")
    typer.echo(f"  matches          : {payload['matches']}  ({payload['matched_records']} records)")
    typer.echo(f"  exceptions       : {payload['exceptions']}")
    typer.echo(f"  events           : {verify['events']}")
    typer.echo(f"  terminal hash    : {verify['terminal_hash'][:16]}…")


@app.command()
def bench(
    spec: Path = typer.Option(..., "--spec"),
    dataset: Path = typer.Option(..., "--dataset"),
    no_ai: bool = typer.Option(False, "--no-ai"),
    calibration: bool = typer.Option(False, "--calibration", help="also run the calibration study"),
    db: str | None = typer.Option(None, "--db"),
    out: Path | None = typer.Option(None, "--out", help="write scorecard.json here"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run a reconciliation and score it against the dataset's ground truth."""
    store = _store(db)
    proj = execute(store, RunInputs(spec_path=spec, dataset_dir=dataset, no_ai=no_ai))

    # determinism check: a second run must reproduce the hash chain
    store2 = EventStore("sqlite://")
    proj2 = execute(store2, RunInputs(spec_path=spec, dataset_dir=dataset, no_ai=no_ai))
    replay_ok = (
        store.verify(proj.run_id)["terminal_hash"] == store2.verify(proj2.run_id)["terminal_hash"]
    )

    wallclock = _run_wallclock(store, proj.run_id)
    card = score_run(
        proj, dataset, spec_name=f"{spec.stem}", wallclock_ms=wallclock, replay_hash_match=replay_ok
    )
    payload = card.to_dict()

    if calibration:
        from arbiter_engine.bench.calibration import calibrate

        gt = json.loads((dataset / "ground_truth.json").read_text())
        true_utrs = {m["settlement_utr"] for m in gt["true_matches"]}
        benign = {
            a["settlement_utr"]
            for a in gt["anomalies"]
            if a.get("settlement_utr") and a["true_resolution"].get("action") == "accept_variance"
        }
        preds: list[tuple[float, bool]] = []
        for m in proj.matches:
            key = m.id.removeprefix("m_")
            correct = (key in true_utrs or key in benign) and abs(m.residual_minor) <= 100
            preds.append((m.confidence, correct))
        report = calibrate(preds)
        payload["calibration"] = report.to_dict()

    store.append(proj.run_id, EventType.SCORECARD_COMPUTED, {"scorecard": payload})

    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_scorecard(card)
        if calibration:
            _print_calibration(payload["calibration"])
    if out:
        out.write_text(json.dumps(payload, indent=2))
        typer.echo(f"\n→ {out}")


def _print_calibration(c: dict) -> None:  # type: ignore[type-arg]
    verdict = "well-calibrated" if c["well_calibrated"] else "RECALIBRATED"
    typer.secho("\n  confidence calibration", bold=True)
    typer.echo(f"    ECE              {c['ece']}   ({verdict})")
    typer.echo(f"    predictions      {c['n']}")
    for r in c["reliability"]:
        bar = "█" * int(r["accuracy"] * 20)
        rng = f"{r['range'][0]:.1f}-{r['range'][1]:.1f}"
        typer.echo(
            f"    {rng}  n={r['n']:<3}  conf={r['confidence']:.2f}  acc={r['accuracy']:.2f}  {bar}"
        )


def _run_wallclock(store: EventStore, run_id: str) -> int:
    import json as _json

    for ev in store.events(run_id):
        if ev.type == EventType.RUN_COMPLETED:
            return int(_json.loads(ev.meta).get("wallclock_ms", 0))
    return 0


def _print_scorecard(card) -> None:  # type: ignore[no-untyped-def]
    m, e = card.matching, card.exceptions
    typer.secho(f"\nArbiter scorecard — {card.spec}  ({card.dataset['difficulty']})", bold=True)
    typer.echo(
        f"  dataset            {card.dataset['records']} records · "
        f"{card.dataset['true_matches']} true matches · {card.dataset['anomalies']} anomalies"
    )
    typer.echo("  matching")
    typer.echo(
        f"    auto-match rate  {m.auto_match_rate:.1%}   ({m.correct_matches}/{m.true_matches})"
    )
    typer.echo(f"    precision        {m.precision:.1%}")
    typer.echo(f"    recall           {m.recall:.1%}")
    typer.echo(f"    false-match rate {m.false_match_rate:.1%}")
    typer.echo(f"    $ coverage       {m.dollar_coverage:.1%}")
    typer.echo(f"    $ unexplained    {m.dollar_unexplained:.1%}")
    typer.echo("  exceptions")
    typer.echo(f"    opened           {e.total}   {e.by_type}")
    typer.echo(
        f"    anomalies caught {e.detected_anomalies}/{e.total_anomalies}   "
        f"category accuracy {e.category_accuracy:.1%}"
    )
    typer.echo("  throughput / integrity")
    typer.echo(f"    records/sec      {card.throughput['records_per_sec']}")
    mark = "✓" if card.determinism["replay_hash_match"] else "✗ MISMATCH"
    typer.echo(f"    deterministic    {mark}")
    typer.secho("  AI                 disabled (agent lands in M3)", fg=typer.colors.BRIGHT_BLACK)


@app.command()
def replay(
    run_id: str = typer.Argument(...),
    db: str | None = typer.Option(None, "--db"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Reproduce a completed run from its event log."""
    store = _store(db)
    try:
        res = do_replay(store, run_id)
    except ChainBroken as exc:
        typer.secho(f"CHAIN BROKEN: {exc}", fg=typer.colors.RED)
        raise typer.Exit(2) from exc
    out = {
        "run_id": res.run_id,
        "intact": res.intact,
        "events": res.events,
        "terminal_hash": res.terminal_hash,
        "records": res.projection.record_count,
        "completed": res.projection.completed,
        "ok": res.ok,
    }
    if as_json:
        typer.echo(json.dumps(out, indent=2))
        return
    mark = (
        typer.style("OK", fg=typer.colors.GREEN)
        if res.ok
        else typer.style("INCOMPLETE", fg=typer.colors.YELLOW)
    )
    typer.echo(f"replay {run_id}  [{mark}]")
    typer.echo(f"  chain intact  : {res.intact}  ({res.events} events)")
    typer.echo(f"  records       : {res.projection.record_count}")
    typer.echo(f"  terminal hash : {res.terminal_hash[:16]}…")


@app.command()
def verify(run_id: str = typer.Argument(...), db: str | None = typer.Option(None, "--db")) -> None:
    """Recompute the audit hash chain for a run."""
    store = _store(db)
    try:
        res = store.verify(run_id)
    except ChainBroken as exc:
        typer.secho(f"CHAIN BROKEN: {exc}", fg=typer.colors.RED)
        raise typer.Exit(2) from exc
    typer.secho(
        f"event chain intact — {res['events']} events, terminal hash {res['terminal_hash'][:16]}…",
        fg=typer.colors.GREEN,
    )


@app.command()
def events(run_id: str = typer.Argument(...), db: str | None = typer.Option(None, "--db")) -> None:
    """Dump the raw event log for a run."""
    store = _store(db)
    for ev in store.events(run_id):
        typer.echo(f"{ev.seq:>4}  {ev.type:<18}  {ev.actor:<10}  {ev.hash[:12]}")


@app.command()
def gen(
    scenario: str = typer.Option("d2c", "--scenario"),
    records: int = typer.Option(120, "--records"),
    seed: int = typer.Option(42, "--seed"),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Generate a synthetic reconciliation dataset (delegates to arbiter-datagen)."""
    try:
        from arbiter_datagen.generate import generate_dataset
    except ImportError as exc:  # pragma: no cover
        typer.secho("arbiter-datagen is not installed", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    manifest = generate_dataset(scenario=scenario, records=records, seed=seed, out_dir=out)
    typer.echo(f"generated {manifest['records']} records → {out}")
    for name, n in manifest["file_rows"].items():
        typer.echo(f"  {name:<24} {n} rows")


if __name__ == "__main__":  # pragma: no cover
    app()
