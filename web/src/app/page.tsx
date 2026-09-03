import Link from "next/link";
import { api } from "@/lib/api";
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

      {isDemo && (
        <div className="mt-6 rounded border border-accent/30 bg-accent/5 p-3 text-sm">
          <strong>Hosted demo.</strong> This is the real cockpit serving a frozen
          snapshot of one <code className="font-mono">arbiter run</code> — 1,672
          records, the investigation agent pointed at <code className="font-mono">gpt-4o</code>.
          Open the run below to see the full agent investigation; “reconcile”
          replays it live. Run the whole stack yourself with{" "}
          <code className="font-mono">make up</code>.
        </div>
      )}

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
