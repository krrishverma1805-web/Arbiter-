from __future__ import annotations

from pathlib import Path

import typer

from arbiter_datagen.generate import generate_dataset

app = typer.Typer(add_completion=False, help="Arbiter synthetic reconciliation data generator.")


@app.callback()
def _main() -> None:
    """Arbiter synthetic reconciliation data generator."""


@app.command()
def gen(
    scenario: str = typer.Option("d2c", "--scenario", help="d2c | marketplace | saas"),
    records: int = typer.Option(120, "--records"),
    seed: int = typer.Option(42, "--seed"),
    difficulty: str = typer.Option("normal", "--difficulty", help="easy | normal | hard"),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Generate a seeded reconciliation dataset with labeled ground truth."""
    manifest = generate_dataset(
        scenario=scenario, records=records, seed=seed, out_dir=out, difficulty=difficulty
    )
    typer.echo(
        f"scenario={manifest['scenario']} seed={manifest['seed']} "
        f"difficulty={manifest['difficulty']} records={manifest['records']} "
        f"batches={manifest['settlement_batches']}"
    )
    for name, n in manifest["file_rows"].items():
        typer.echo(f"  {name:<24} {n} rows")
    if manifest["anomalies_injected"]:
        anomalies = ", ".join(f"{k}×{v}" for k, v in manifest["anomalies_injected"].items())
        typer.echo(f"  anomalies                {anomalies}")
    typer.echo(f"  dataset_hash             {manifest['dataset_hash']}")
    typer.echo(f"→ {out}")


if __name__ == "__main__":  # pragma: no cover
    app()
