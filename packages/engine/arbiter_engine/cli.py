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


def _bench_once(spec: Path, dataset: Path, *, no_ai: bool, model: str | None, db: str | None):  # type: ignore[no-untyped-def]
    store = _store(db) if db else EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec, dataset_dir=dataset, no_ai=no_ai, model=model))
    store2 = EventStore("sqlite://")
    proj2 = execute(
        store2, RunInputs(spec_path=spec, dataset_dir=dataset, no_ai=no_ai, model=model)
    )
    replay_ok = (
        store.verify(proj.run_id)["terminal_hash"] == store2.verify(proj2.run_id)["terminal_hash"]
    )
    agent_events = [(t, p) for t, p in store.iter_payloads(proj.run_id) if t.startswith("AGENT_")]
    card = score_run(
        proj,
        dataset,
        spec_name=spec.stem,
        wallclock_ms=_run_wallclock(store, proj.run_id),
        replay_hash_match=replay_ok,
        agent_events=agent_events,
    )
    return store, proj, card


@app.command()
def bench(
    spec: Path = typer.Option(..., "--spec"),
    dataset: Path = typer.Option(..., "--dataset"),
    no_ai: bool = typer.Option(False, "--no-ai"),
    calibration: bool = typer.Option(False, "--calibration", help="also run the calibration study"),
    ablate: bool = typer.Option(False, "--ablate", help="--no-ai vs haiku vs sonnet vs opus"),
    model: str | None = typer.Option(None, "--model", help="override the agent model"),
    db: str | None = typer.Option(None, "--db"),
    out: Path | None = typer.Option(None, "--out", help="write scorecard.json here"),
    gate: Path | None = typer.Option(
        None, "--gate", help="fail if any metric regresses vs this baseline scorecard"
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run a reconciliation and score it against the dataset's ground truth."""
    if ablate:
        _run_ablation(spec, dataset)
        return

    store, proj, card = _bench_once(spec, dataset, no_ai=no_ai, model=model, db=db)
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
        if db and report.recalibration:
            from arbiter_engine.match.fs_store import persist_calibration
            from arbiter_engine.specs import load_spec as _ls
            from arbiter_engine.specs import spec_hash

            saved = persist_calibration(
                _store(db),
                proj.run_id,
                spec_hash(_ls(spec)),
                list(report.recalibration),
                n_samples=report.n,
                ece_before=report.ece,
            )
            if saved:
                typer.secho(
                    f"\nfitted calibration persisted ({report.n} samples) — "
                    "the next run over this spec loads it",
                    fg=typer.colors.CYAN,
                )

    store.append(proj.run_id, EventType.SCORECARD_COMPUTED, {"scorecard": payload})

    if as_json:
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_scorecard(card)
        _print_agent(payload["agent"])
        _print_safety(payload["safety"])
        if calibration:
            _print_calibration(payload["calibration"])
    if out:
        out.write_text(json.dumps(payload, indent=2))
        typer.echo(f"\n→ {out}")

    if gate:
        from arbiter_engine.bench.gate import check_regression

        base = json.loads(gate.read_text())
        failures = check_regression(base, payload)
        if failures:
            typer.secho("\nregression gate FAILED:", fg=typer.colors.RED, bold=True)
            for f in failures:
                typer.secho(f"  {f}", fg=typer.colors.RED)
            raise typer.Exit(1)
        typer.secho("\nregression gate passed", fg=typer.colors.GREEN)


def _run_ablation(spec: Path, dataset: Path) -> None:
    """Compare --no-ai vs the model tiers on the same dataset (docs/12 §5)."""
    import os as _os

    configs: list[tuple[str, bool, str | None]] = [("--no-ai", True, None)]
    if _os.environ.get("ARBITER_LLM_PROVIDER", "").lower() == "openai" and _os.environ.get(
        "OPENAI_API_KEY"
    ):
        configs += [(_os.environ.get("ARBITER_OPENAI_MODEL", "gpt-4o"), False, None)]
    elif _os.environ.get("ANTHROPIC_API_KEY"):
        configs += [
            ("haiku", False, "claude-haiku-4-5"),
            ("sonnet", False, "claude-sonnet-5"),
            ("opus", False, "claude-opus-5"),
        ]
    typer.secho("\nAblation — accuracy × cost × latency", bold=True)
    typer.echo(
        f"  {'config':<10} {'cat.acc':>8} {'task.compl':>10} {'esc.recall':>10} {'cost$':>8}"
    )
    baseline_cat = None
    for name, na, mdl in configs:
        _s, _p, card = _bench_once(spec, dataset, no_ai=na, model=mdl, db=None)
        a = card.agent
        cat = card.exceptions.category_accuracy
        if baseline_cat is None:
            baseline_cat = cat
        lift = (
            f"  (lift {cat - baseline_cat:+.1%})"
            if baseline_cat is not None and name != "--no-ai"
            else ""
        )
        typer.echo(
            f"  {name:<10} {cat:>7.1%} {a.task_completion_rate:>9.1%} "
            f"{a.escalation_recall:>9.1%} {a.est_cost_usd:>7.2f}{lift}"
        )
    if len(configs) == 1:
        typer.secho(
            "  (set ANTHROPIC_API_KEY to include the model tiers)", fg=typer.colors.BRIGHT_BLACK
        )


def _print_agent(a: dict) -> None:  # type: ignore[type-arg]
    if not a.get("enabled"):
        typer.secho("  agent              disabled (--no-ai)", fg=typer.colors.BRIGHT_BLACK)
        return
    typer.secho(f"\n  agent — {a['model']}", bold=True)
    typer.echo(
        f"    investigations   {a['investigations']}  "
        f"({a['proposals']} proposals, {a['escalations']} escalations {a['escalation_reasons']})"
    )
    typer.echo(f"    task-completion  {a['task_completion_rate']:.1%}")
    typer.echo(f"    category acc.    {a['category_accuracy']:.1%}   (of proposals)")
    typer.echo(
        f"    escalation P/R   {a['escalation_precision']:.1%} / {a['escalation_recall']:.1%}"
    )
    typer.echo(f"    hallucination    {a['hallucination_rate']:.1%}")
    typer.echo(f"    grounded         {a.get('grounded_rate', 0):.1%}")
    if a.get("confidence_n"):
        typer.echo(f"    confidence ECE   {a['confidence_ece']:.3f}  (n={a['confidence_n']})")
    typer.echo(
        f"    cost             ${a['est_cost_usd']:.3f}  "
        f"({a['tool_calls']} tool calls, {a['tokens_in']}+{a['tokens_out']} tok)"
    )


def _print_safety(s: dict) -> None:  # type: ignore[type-arg]
    typer.secho("\n  safety (headline)", bold=True)
    rate = s["unsafe_resolution_rate"]
    n_unsafe = s["unsafe_auto_resolutions"]
    mark = (
        typer.style("✓ 0", fg=typer.colors.GREEN)
        if not n_unsafe
        else typer.style(f"✗ {n_unsafe}", fg=typer.colors.RED)
    )
    typer.echo(
        f"    unsafe auto-res  {mark}  ({rate:.1%} of {s['items_needing_human']} human-only items)"
    )
    typer.echo(
        f"    ₹ protected      ₹{s['rupees_protected_minor'] / 100:,.0f} / "
        f"₹{s['rupees_at_risk_minor'] / 100:,.0f}  ({s['rupees_protected_rate']:.1%})"
    )
    div = "✗ DIVERGED" if s["replay_divergence"] else "✓ identical"
    typer.echo(f"    replay           {div}")
    typer.echo(
        f"    fabricated cites {s['fabricated_citations']}   ·   "
        f"injection quarantined {s['injection_quarantined']}"
    )


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
    if m.by_pass:
        typer.echo(f"    by pass          {m.by_pass}")
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
def attack(
    spec: Path = typer.Option(..., "--spec"),
    dataset: Path = typer.Option(..., "--dataset"),
    scenario: str | None = typer.Option(None, "--scenario", help="one attack; omit for all"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Attack Arbiter — mutate a clean dataset with a known tampering, reconcile,
    and report whether Arbiter detected it, kept the money accounted for, and
    refused any unsafe auto-resolution (spec §29 / §70 / §88)."""
    import tempfile

    from arbiter_engine.attack import ATTACKS, run_all, run_attack

    if scenario and scenario not in ATTACKS:
        typer.secho(f"unknown scenario '{scenario}'. Available:", fg=typer.colors.RED)
        for n, a in ATTACKS.items():
            typer.echo(f"  {n:28} {a.description}")
        raise typer.Exit(2)

    with tempfile.TemporaryDirectory(prefix="arbiter-attack-") as tmp:
        work = Path(tmp)
        results = (
            [run_attack(spec, dataset, scenario, work)]
            if scenario
            else run_all(spec, dataset, work)
        )

    if as_json:
        typer.echo(json.dumps([r.as_dict() for r in results], indent=2))
        return

    _COLOUR = {
        "CONTAINED": typer.colors.GREEN,
        "PARTIAL": typer.colors.YELLOW,
        "MISSED": typer.colors.YELLOW,
        "UNSAFE": typer.colors.RED,
    }
    typer.secho("\nAttack Arbiter — the system tries to be fooled\n", bold=True)
    for r in results:
        typer.secho(f"  {r.verdict:10}", fg=_COLOUR.get(r.verdict), nl=False)
        typer.echo(f" {r.scenario}")
        typer.secho(f"             {r.description}", fg=typer.colors.BRIGHT_BLACK)
        typer.secho(f"             → {r.what_arbiter_did}", fg=typer.colors.BRIGHT_BLACK)
    contained = sum(1 for r in results if r.verdict == "CONTAINED")
    partial = sum(1 for r in results if r.verdict == "PARTIAL")
    missed = sum(1 for r in results if r.verdict == "MISSED")
    unsafe = sum(1 for r in results if r.verdict == "UNSAFE")
    typer.secho(
        f"\n  {contained} contained · {partial} partial · {missed} missed · {unsafe} UNSAFE",
        bold=True,
        fg=typer.colors.RED if unsafe else typer.colors.GREEN,
    )
    typer.secho(
        "  UNSAFE = the matcher asserted a false confident clean tie. "
        "MISSED = no signal, but no false assertion either.",
        fg=typer.colors.BRIGHT_BLACK,
    )
    if unsafe:
        raise typer.Exit(1)


@app.command()
def verify(
    run_id: str = typer.Argument(...),
    db: str | None = typer.Option(None, "--db"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Recompute the audit hash chain for a run."""
    store = _store(db)
    try:
        res = store.verify(run_id)
    except ChainBroken as exc:
        if as_json:
            typer.echo(json.dumps({"intact": False, "error": str(exc)}))
        else:
            typer.secho(f"CHAIN BROKEN: {exc}", fg=typer.colors.RED)
        raise typer.Exit(2) from exc
    if as_json:
        typer.echo(json.dumps(res))
        return
    typer.secho(
        f"event chain intact — {res['events']} events, terminal hash {res['terminal_hash'][:16]}…",
        fg=typer.colors.GREEN,
    )


@app.command()
def events(run_id: str = typer.Argument(...), db: str | None = typer.Option(None, "--db")) -> None:
    """Dump the raw event log for a run."""
    store = _store(db)
    for ev in store.events(run_id):
        typer.echo(f"{ev.seq:>4}  {ev.type:<26}  {ev.actor:<28}  {ev.hash[:12]}")


@app.command()
def explain(
    run_id: str = typer.Argument(..., help="run id (or 'last')"),
    exception_id: str | None = typer.Argument(None),
    db: str | None = typer.Option(None, "--db"),
) -> None:
    """Print the evidence for a run's exceptions, as text (docs/05 §6)."""
    from arbiter_engine.events.fold import fold_run
    from arbiter_engine.money import format_minor

    store = _store(db)
    rid = store.runs()[-1] if run_id == "last" else run_id
    proj = fold_run(store, rid)
    targets = [e for e in proj.exceptions if exception_id in (None, e.id)]
    if not targets:
        typer.secho("no matching exception", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    recs = {r.id: r for r in proj.records}
    for e in targets:
        typer.secho(f"\n{e.id}  {e.category or 'UNCLASSIFIED'}  [{e.status}]", bold=True)
        typer.echo(f"  impact       {format_minor(e.amount_impact_minor)}")
        typer.echo(f"  classified   {e.classified_by}")
        for rid_ in e.record_ids:
            r = recs.get(rid_)
            if r:
                typer.echo(
                    f"  · {r.source:<15} {r.kind:<10} {format_minor(r.amount_minor):>14}  "
                    f"{r.reference or ''}"
                )
        d = next(
            (
                d
                for d in proj.decompositions
                if any(
                    recs.get(x) and recs[x].external_ids.get("settlement_utr") == d.settlement_utr
                    for x in e.record_ids
                )
            ),
            None,
        )
        if d:
            typer.echo(
                f"  identity     expected {format_minor(d.expected_minor)}  "
                f"actual {format_minor(d.actual_minor)}  residual {format_minor(d.residual_minor)}"
            )
        if e.agent_proposal:
            p = e.agent_proposal
            typer.secho("  proposed by Arbiter:", fg=typer.colors.CYAN)
            typer.echo(f"    {p.get('category')} (confidence {p.get('confidence')})")
            typer.echo(f"    {p.get('explanation')}")
            typer.echo(f"    action: {p.get('suggested_action')}")
        if e.agent_escalation:
            esc = e.agent_escalation
            typer.secho("  escalated by Arbiter:", fg=typer.colors.CYAN)
            typer.echo(f"    knows:   {esc.get('what_i_know')}")
            typer.echo(f"    missing: {esc.get('what_is_missing')}")
            typer.echo(f"    ASK:     {esc.get('question')}")


@app.command()
def resolve(
    run_id: str = typer.Argument(...),
    exception_id: str = typer.Argument(...),
    action: str = typer.Option(..., "--action"),
    detail: str = typer.Option("", "--detail"),
    actor: str = typer.Option("human:cli", "--actor"),
    category: str | None = typer.Option(
        None, "--category", help="correct the classifier's category (seeds the learned rule)"
    ),
    db: str | None = typer.Option(None, "--db"),
) -> None:
    """Apply a resolution to an exception; drafts a learned rule if the shape allows."""
    from arbiter_engine.events.fold import fold_run
    from arbiter_engine.learn import draft_rule_from_resolution

    store = _store(db)
    proj = fold_run(store, run_id)
    exc = next((e for e in proj.exceptions if e.id == exception_id), None)
    if exc is None:
        typer.secho("exception not found", fg=typer.colors.RED)
        raise typer.Exit(1)
    store.append(
        run_id,
        EventType.RESOLUTION_APPLIED,
        {
            "exception_id": exception_id,
            "action": action,
            "detail": detail,
            "actor": actor,
            "prior_status": exc.status,
            "category": category,
        },
    )
    draft = draft_rule_from_resolution(exc, action, category=category)
    if draft is not None:
        store.append(run_id, EventType.RULE_DRAFTED, draft)
        typer.secho(f"resolved · drafted rule {draft['rule_id']}", fg=typer.colors.GREEN)
        typer.echo(f"  when: {draft['when']}")
    else:
        typer.secho("resolved", fg=typer.colors.GREEN)

    try:  # opt-in global pattern library (docs/28 §3 item 15)
        from arbiter_engine.learn.global_patterns import contribute

        recs = [r for r in proj.records if r.id in exc.record_ids]
        if contribute(getattr(store, "org_id", "local"), exc, recs, action):
            typer.echo("  contributed the (anonymised) shape to the global library")
    except Exception:  # noqa: BLE001
        pass


rules_app = typer.Typer(help="Review and merge learned classification rules.")
app.add_typer(rules_app, name="rules")


@rules_app.command("pending")
def rules_pending(
    run_id: str = typer.Argument(...),
    spec: Path = typer.Option(..., "--spec"),
    db: str | None = typer.Option(None, "--db"),
) -> None:
    """Show learned rules drafted during this run, not yet merged into the spec."""
    from arbiter_engine.learn import pending_rules

    pend = pending_rules(_store(db), run_id, spec)
    if not pend:
        typer.echo("no pending rules")
        return
    for r in pend:
        typer.secho(f"{r['rule_id']}", bold=True)
        typer.echo(f"  when:     {r['when']}")
        typer.echo(f"  classify: {r['classify']}   resolve: {r['resolve']}")
        typer.echo(f"  from:     {r['provenance_exception_id']}")


@rules_app.command("merge")
def rules_merge(
    run_id: str = typer.Argument(...),
    spec: Path = typer.Option(..., "--spec"),
    rule_id: list[str] = typer.Option(None, "--rule", help="specific rule id(s); omit for all"),
    db: str | None = typer.Option(None, "--db"),
) -> None:
    """Append the approved learned rules to the spec YAML and bump its version."""
    from arbiter_engine.learn import merge_rules

    res = merge_rules(_store(db), run_id, spec, rule_id or None, approved_by="human:cli")
    if not res["merged"]:
        typer.echo("nothing to merge")
        return
    typer.secho(
        f"merged {res['merged']} → {spec} "
        f"(version {res['version_before']} → {res['version_after']})",
        fg=typer.colors.GREEN,
    )


@app.command("cash-position")
def cash_position_cmd(
    run_id: str = typer.Argument(...),
    db: str | None = typer.Option(None, "--db"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Where the money is, off the reconciled ledger — confirmed in bank, in
    transit, held, or unexplained. Pure arithmetic, no LLM."""
    from arbiter_engine.cash import cash_position
    from arbiter_engine.events.fold import fold_run
    from arbiter_engine.money import format_minor

    store = _store(db)
    proj = fold_run(store, run_id)
    if not proj.completed:
        typer.secho("run is not complete", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    cp = cash_position(proj)

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "run_id": cp.run_id,
                    "gross_minor": cp.gross_minor,
                    "mdr_minor": cp.mdr_minor,
                    "gst_minor": cp.gst_minor,
                    "refunds_minor": cp.refunds_minor,
                    "net_expected_minor": cp.net_expected_minor,
                    "confirmed_minor": cp.confirmed_minor,
                    "confirmed_count": cp.confirmed_count,
                    "in_transit_minor": cp.in_transit_minor,
                    "held_minor": cp.held_minor,
                    "money_found_minor": cp.money_found_minor,
                    "unexplained_minor": cp.unexplained_minor,
                    "accounted_minor": cp.accounted_minor,
                    "reconciling_delta_minor": cp.reconciling_delta_minor,
                    "by_bucket": cp.by_bucket,
                },
                indent=2,
            )
        )
        return

    def row(label: str, minor: int, note: str = "") -> None:
        typer.echo(f"  {label:<32}{format_minor(minor):>16}   {note}")

    typer.secho(f"\ncash position — run {cp.run_id}", bold=True)
    row("gross payments processed", cp.gross_minor)
    row("− MDR", -cp.mdr_minor)
    row("− GST on MDR", -cp.gst_minor)
    row("− refunds", -cp.refunds_minor)
    typer.echo("  " + "─" * 48)
    row("net expected from settlements", cp.net_expected_minor)
    typer.echo("")
    row("✓ confirmed in bank", cp.confirmed_minor, f"{cp.confirmed_count} settlements tied")
    row("⧗ in transit", cp.in_transit_minor, "settles next period (TIMING)")
    row("⚠ held — disputes / review", cp.held_minor, "")
    row("? unexplained", cp.unexplained_minor, "")
    typer.echo("  " + "─" * 48)
    row("accounted for", cp.accounted_minor)
    delta = cp.reconciling_delta_minor
    tag = "every rupee placed" if delta == 0 else "still reconciling"
    typer.secho(
        f"  {'Δ vs net expected':<32}{format_minor(delta):>16}   {tag}",
        fg=typer.colors.GREEN if delta == 0 else typer.colors.YELLOW,
    )
    if cp.money_found_minor:
        typer.secho(
            f"\n  + ₹ {cp.money_found_minor / 100:,.2f} over-charged by the processor — claw back "
            f"(FEE_DEDUCTION)",
            fg=typer.colors.CYAN,
        )


@app.command()
def retrain(
    spec: Path = typer.Option(..., "--spec", help="path to the recon spec YAML"),
    actor: str = typer.Option("cli", "--actor"),
    db: str | None = typer.Option(None, "--db"),
) -> None:
    """Retrain this tenant's learned artifacts (docs/28 §3 item 14): the
    Fellegi–Sunter m/u table from confirmed matches (behind a held-out ROC-AUC
    eval gate) and the agent's escalation threshold from human accept/override
    history. Both decisions are written to the event log; the next run loads
    them."""
    from arbiter_engine.learn.agent_tune import tune_escalation_threshold
    from arbiter_engine.learn.retrain import retrain as _retrain
    from arbiter_engine.specs import load_spec

    store = _store(db)
    parsed = load_spec(spec)
    res = _retrain(store, parsed, trained_by=actor)
    colour = typer.colors.GREEN if res.promoted else typer.colors.YELLOW
    typer.secho(
        f"fs-model: {res.reason} — AUC {res.auc_before:.3f} -> {res.auc_after:.3f} "
        f"over {res.n_pairs} labelled pairs",
        fg=colour,
    )
    tr = tune_escalation_threshold(store, parsed, trained_by=actor)
    if tr.tuned:
        typer.secho(
            f"threshold: theta_escalate -> {tr.theta_escalate} "
            f"({tr.accepted} accepted / {tr.overridden} overridden)",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            f"threshold: unchanged ({tr.accepted}+{tr.overridden} feedback pairs, need 20)",
            fg=typer.colors.YELLOW,
        )


@app.command()
def models(
    spec: Path = typer.Option(..., "--spec", help="path to the recon spec YAML"),
    db: str | None = typer.Option(None, "--db"),
) -> None:
    """The learned-artifact registry for this spec (docs/28 §3 item 16): every
    promoted / rejected Fellegi–Sunter model, every fitted calibration map, and
    the input-drift timeline — all folded from the append-only event log."""
    from arbiter_engine.specs import load_spec, spec_hash

    store = _store(db)
    sh = spec_hash(load_spec(spec))
    rows: list[tuple[str, str]] = []
    for rid in store.runs(include_internal=True):
        for t, p in store.iter_payloads(rid):
            if p.get("spec_hash") != sh:
                continue
            ab, aa = p.get("auc_before"), p.get("auc_after")
            if t == "FS_MODEL_PROMOTED":
                rows.append((t, f"AUC {ab:.3f}->{aa:.3f}  n={p['n_pairs']}"))
            elif t == "FS_MODEL_REJECTED":
                rows.append((t, f"AUC {ab:.3f}->{aa:.3f}  ({p['reason']})"))
            elif t == "FS_CALIBRATION_FITTED":
                rows.append((t, f"{len(p['points'])} points from {p['n_samples']} samples"))
            elif t == "INPUT_DRIFT_DETECTED" and p.get("baseline_runs", 0) >= 3:
                mark = "! " if p.get("drifted") else "  "
                feats = ", ".join(p.get("drifted", [])) or "ok"
                rows.append((t, f"{mark}PSI {p['psi']:.3f}  {feats}"))
    if not rows:
        typer.echo("no learned artifacts for this spec yet")
        return
    for kind, detail in rows:
        typer.echo(f"  {kind:<24} {detail}")


@app.command()
def memo(
    run_id: str = typer.Argument(...),
    out: Path | None = typer.Option(None, "--out", help="write the HTML here (default: stdout)"),
    db: str | None = typer.Option(None, "--db"),
) -> None:
    """Render the auditor-ready Close Memo for a run (docs/20 §2.6).

    One self-contained HTML file — it opens offline and is print-styled (`@page`
    margins, no row splits), so a browser's "Save as PDF" produces the PDF copy.
    """
    from arbiter_engine.events.fold import fold_run
    from arbiter_engine.memo import render_memo

    store = _store(db)
    proj = fold_run(store, run_id)
    if not proj.completed:
        typer.secho("run is not complete", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    spec_name = "razorpay-settlement"
    period = None
    for t, p in store.iter_payloads(run_id):
        if t == EventType.RUN_STARTED:
            spec_name = p.get("spec_name", spec_name)
    v = store.verify(run_id)
    scpayload = proj.scorecard if isinstance(proj.scorecard, dict) else None
    doc = render_memo(
        proj,
        spec_name=spec_name,
        period=period,
        terminal_hash=v["terminal_hash"],
        scorecard=scpayload,
    )
    if out:
        out.write_text(doc)
        typer.echo(f"→ {out}")
    else:
        typer.echo(doc)


@app.command("cycle-demo")
def cycle_demo(
    out: Path = typer.Option(Path("data/cycle"), "--out", help="working directory"),
    spec: Path = typer.Option(
        Path("specs/razorpay-settlement.yaml"), "--spec", help="the starting spec"
    ),
    records: int = typer.Option(300, "--records"),
    cycles: int = typer.Option(3, "--cycles", min=2),
    difficulty: str = typer.Option("hard", "--difficulty"),
) -> None:
    """Three monthly closes: cycle 1 leaves a settlement residual UNEXPLAINED, a
    controller resolves it, the drafted rule is merged, and cycles 2+ classify the
    same shape automatically. Shows the unexplained-money line falling."""
    from arbiter_datagen.generate import generate_dataset

    from arbiter_engine.learn.cycle import run_cycle_demo

    out.mkdir(parents=True, exist_ok=True)
    datasets: list[Path] = []
    for i in range(1, cycles + 1):
        d = out / f"batch{i}"
        generate_dataset(scenario="d2c", records=records, seed=i, out_dir=d, difficulty=difficulty)
        datasets.append(d)

    result = run_cycle_demo(spec, datasets, out)

    typer.echo("")
    typer.secho(f"{'':6}{'':10}{'base spec':>26}{'with learned rule':>28}", bold=True)
    typer.secho(
        f"{'cycle':<6}{'batch':<10}"
        f"{'UNEXPLAINED':>13}{'unexplained ₹':>13}"
        f"{'UNEXPLAINED':>14}{'unexplained ₹':>14}{'₹ recovered':>14}",
        bold=True,
    )
    for r in result.rows:
        typer.echo(
            f"{r.cycle:<6}{r.dataset:<10}"
            f"{r.base_unexplained_count:>13}{r.base_unexplained_minor / 100:>13,.0f}"
            f"{r.learned_unexplained_count:>14}{r.learned_unexplained_minor / 100:>14,.0f}"
            f"{r.money_recovered_minor / 100:>14,.0f}"
        )
    if result.drafted_rule is not None:
        rule = result.drafted_rule
        typer.echo("")
        typer.secho(
            f"cycle 1: controller resolved a split-settlement residual → drafted & merged "
            f"{rule['rule_id']} "
            f"(spec v{result.spec_version_before} → v{result.spec_version_after})",
            fg=typer.colors.GREEN,
        )
        typer.echo(f"  when:     {rule['when']}")
        typer.echo(f"  classify: {rule['classify']}   resolve: {rule['resolve']}")
        later = result.rows[1:]
        if later and all(r.money_recovered_minor >= 0 for r in later):
            recovered = result.total_recovered_minor / 100
            typer.secho(
                f"\nthe learned rule cleared ₹{recovered:,.0f} of settlement residual across "
                f"{len(later)} later close(s) that the base spec left UNEXPLAINED",
                fg=typer.colors.GREEN,
            )


@app.command("audit-pack")
def audit_pack(
    run_id: str = typer.Argument(...),
    out: Path = typer.Option(..., "--out", help="write the .zip here"),
    db: str | None = typer.Option(None, "--db"),
) -> None:
    """Bundle everything an auditor needs for one run into a single zip:
    the full hash-chained event log, the Close Memo, and a manifest with the
    verify result so the log can be re-checked offline."""
    import zipfile

    from arbiter_engine.events.fold import fold_run
    from arbiter_engine.memo import render_memo

    store = _store(db)
    proj = fold_run(store, run_id)
    if not proj.completed:
        typer.secho("run is not complete", fg=typer.colors.YELLOW)
        raise typer.Exit(1)

    v = store.verify(run_id)
    spec_name = "razorpay-settlement"
    for t, p in store.iter_payloads(run_id):
        if t == EventType.RUN_STARTED:
            spec_name = p.get("spec_name", spec_name)

    log_lines = [
        json.dumps(
            {
                "seq": e.seq,
                "ts": e.ts,
                "type": e.type,
                "actor": e.actor,
                "payload": json.loads(e.payload),
                "prev_hash": e.prev_hash,
                "hash": e.hash,
            },
            sort_keys=True,
        )
        for e in store.events(run_id)
    ]
    scpayload = proj.scorecard if isinstance(proj.scorecard, dict) else None
    memo_html = render_memo(
        proj,
        spec_name=spec_name,
        period=None,
        terminal_hash=v["terminal_hash"],
        scorecard=scpayload,
    )
    manifest = {
        "run_id": run_id,
        "spec_name": spec_name,
        "events": v["events"],
        "terminal_hash": v["terminal_hash"],
        "chain_intact": v["intact"],
        "verify_command": f"arbiter verify {run_id}",
        "contents": ["event-log.jsonl", "close-memo.html", "manifest.json"],
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("event-log.jsonl", "\n".join(log_lines) + "\n")
        z.writestr("close-memo.html", memo_html)
        z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    typer.secho(
        f"→ {out}  ({v['events']} events · terminal {v['terminal_hash'][:12]})",
        fg=typer.colors.GREEN,
    )


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
