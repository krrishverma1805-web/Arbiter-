"""`arbiter` CLI (docs/06 L, docs/20 §1).

M0 commands: gen (delegates to datagen), run, replay, verify, events.
M1+ adds: bench, explain, memo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

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
    db: str | None = typer.Option(None, "--db"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run a reconciliation over a dataset."""
    store = _store(db)
    proj = execute(store, RunInputs(spec_path=spec, dataset_dir=dataset, no_ai=no_ai, seed=seed))
    verify = store.verify(proj.run_id)
    payload = {
        "run_id": proj.run_id,
        "status": proj.status,
        "records": proj.record_count,
        "by_source": proj.by_source(),
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
    typer.echo(f"  events           : {verify['events']}")
    typer.echo(f"  terminal hash    : {verify['terminal_hash'][:16]}…")


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
