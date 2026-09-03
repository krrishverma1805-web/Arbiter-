import Link from "next/link";
import { api, rupees, type Scorecard } from "@/lib/api";
import { NewRun } from "@/components/NewRun";
import { demo } from "@/lib/demo";

export const dynamic = "force-dynamic";

export default async function Home() {
  let runs: Awaited<ReturnType<typeof api.listRuns>>["runs"] = [];
  let specs: { name: string; path: string }[] = [];
  let datasets: { name: string; path: string }[] = [];
  let apiUp = true;
  // No configured backend → this is the hosted demo serving a frozen snapshot
  // of a real run (the investigation agent was pointed at gpt-4o).
  const isDemo = !process.env.ARBITER_API_URL;
  if (isDemo) {
    runs = demo.runs.runs;
    specs = demo.specs.specs;
    datasets = demo.datasets.datasets;
  } else {
    try {
      [runs, specs, datasets] = await Promise.all([
        api.listRuns().then((r) => r.runs),
        api.listSpecs().then((r) => r.specs),
        api.listDatasets().then((r) => r.datasets),
      ]);
    } catch {
      apiUp = false;
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Arbiter</h1>
          <p className="mt-1 text-muted">
            A verification layer for money movement.
          </p>
        </div>
        <kbd className="mt-1 rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted">
          ⌘K
        </kbd>
      </div>

      {isDemo && <DemoOverview sc={demo.scorecard as unknown as Scorecard} runId={demo.run.run_id} />}

      {!apiUp && !isDemo && (
        <div className="mt-6 rounded border border-attention/40 bg-attention/10 p-3 text-sm">
          The API isn&apos;t reachable. Start it with{" "}
          <code className="font-mono">uv run arbiter-api</code>.
        </div>
      )}

      {(apiUp || isDemo) && <NewRun specs={specs} datasets={datasets} />}

      <h2 className="mt-10 text-sm font-semibold uppercase tracking-wide text-muted">
        Runs
      </h2>
      <ul className="mt-3 divide-y divide-border rounded border border-border bg-surface">
        {runs.length === 0 && (
          <li className="p-4 text-sm text-muted">No runs yet.</li>
        )}
        {runs.map((r) => (
          <li key={r.run_id}>
            <Link
              href={`/runs/${r.run_id}`}
              className="flex items-center justify-between p-4 hover:bg-accent/5"
            >
              <span className="font-mono text-xs text-muted">
                {r.run_id.slice(0, 8)}
              </span>
              <span className="text-sm">
                {r.records} records · {r.matches} matches ·{" "}
                <span className="text-attention">
                  {r.exceptions} exceptions
                </span>
              </span>
              <span className="text-xs text-muted">{r.status}</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}

function DemoOverview({ sc, runId }: { sc: Scorecard; runId: string }) {
  const m = sc.matching;
  const s = sc.safety;
  return (
    <div className="mt-6 space-y-4">
      <div className="rounded border border-accent/30 bg-accent/5 p-3 text-sm">
        <strong>Hosted demo.</strong> The real cockpit serving a frozen{" "}
        <code className="font-mono">arbiter run</code> — 1,672 records, the
        investigation agent pointed at{" "}
        <code className="font-mono">gpt-4o</code>. Everything below is that run.
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat
          big={`${(m.auto_match_rate * 100).toFixed(1)}%`}
          label="auto-verified"
          tone="positive"
        />
        <Stat
          big={s ? rupees(s.rupees_at_risk_minor) : "—"}
          label="held for a human"
          tone="attention"
        />
        <Stat big={`${sc.exceptions.total}`} label="open exceptions" />
      </div>

      <div className="rounded border border-border bg-surface p-3 text-xs">
        <div className="font-semibold uppercase tracking-wide text-muted">
          assurance
        </div>
        <ul className="mt-1.5 space-y-1">
          <li>
            false-match rate{" "}
            <span className="font-mono text-positive">
              {(m.false_match_rate * 100).toFixed(1)}%
            </span>{" "}
            · ₹ coverage{" "}
            <span className="font-mono text-positive">
              {(m.dollar_coverage * 100).toFixed(0)}%
            </span>
          </li>
          {s && (
            <li>
              unsafe auto-resolutions{" "}
              <span className="font-mono text-positive">
                {s.unsafe_auto_resolutions}
              </span>{" "}
              · ₹ protected{" "}
              <span className="font-mono text-positive">
                {rupees(s.rupees_protected_minor)}
              </span>{" "}
              · replay{" "}
              <span className="font-mono text-positive">
                {s.replay_divergence ? "diverged" : "identical"}
              </span>
            </li>
          )}
          <li className="text-muted">
            Arbiter never auto-resolves — a human confirms every proposal.
          </li>
        </ul>
      </div>

      <Link
        href={`/runs/${runId}`}
        className="inline-block rounded border border-accent bg-accent/10 px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent/20"
      >
        Open the cockpit →
      </Link>
    </div>
  );
}

function Stat({
  big,
  label,
  tone,
}: {
  big: string;
  label: string;
  tone?: "positive" | "attention";
}) {
  return (
    <div className="rounded border border-border bg-surface p-3">
      <div
        className={`text-xl font-semibold ${
          tone === "positive"
            ? "text-positive"
            : tone === "attention"
              ? "text-attention"
              : ""
        }`}
      >
        {big}
      </div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}
