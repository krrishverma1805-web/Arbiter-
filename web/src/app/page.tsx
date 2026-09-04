import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { api, rupees, type Scorecard } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { NewRun } from "@/components/NewRun";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { demo } from "@/lib/demo";

export const dynamic = "force-dynamic";

export default async function Home() {
  let runs: Awaited<ReturnType<typeof api.listRuns>>["runs"] = [];
  let specs: { name: string; path: string }[] = [];
  let datasets: { name: string; path: string }[] = [];
  let apiUp = true;
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
    <AppShell width="read">
      <header className="max-w-xl">
        <h1 className="text-xl font-semibold tracking-tight">Arbiter</h1>
        <p className="mt-2 text-base leading-relaxed text-text-muted">
          A verification layer for money movement. Point it at a settlement
          file and your ledger; it ties what it can, explains the rest, and
          hands you a short list of what needs a person.
        </p>
      </header>

      {isDemo && (
        <DemoCard sc={demo.scorecard as unknown as Scorecard} runId={demo.run.run_id} />
      )}

      {!apiUp && !isDemo && (
        <Card className="mt-8 border-attention/30 bg-attention/5 p-4 text-sm">
          The reconciliation service isn&apos;t reachable. Start it, then reload
          this page.
        </Card>
      )}

      {(apiUp || isDemo) && (
        <div className="mt-10">
          <h2 className="text-sm font-semibold">Start a reconciliation</h2>
          <p className="mt-1 text-sm text-text-muted">
            Pick a spec and a dataset. The run opens as you watch it.
          </p>
          <NewRun specs={specs} datasets={datasets} />
        </div>
      )}

      <div className="mt-12">
        <h2 className="text-sm font-semibold">Recent runs</h2>
        <ul className="mt-3 divide-y divide-border overflow-hidden rounded-lg border border-border">
          {runs.length === 0 && (
            <li className="px-4 py-8 text-center text-sm text-text-muted">
              No runs yet.
            </li>
          )}
          {runs.map((r) => (
            <li key={r.run_id}>
              <Link
                href={`/runs/${r.run_id}`}
                className="flex items-center gap-4 px-4 py-3 transition-colors [transition-duration:120ms] hover:bg-surface-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-text-muted">
                      {r.run_id.slice(0, 8)}
                    </span>
                    {r.status && (
                      <Badge
                        variant={
                          r.status === "completed" ? "positive" : "neutral"
                        }
                      >
                        {r.status}
                      </Badge>
                    )}
                  </div>
                  <div className="mt-1 text-sm">
                    {r.records.toLocaleString("en-IN")} records ·{" "}
                    {r.matches} settlement groups tied
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-sm font-medium text-attention">
                    {r.exceptions}
                  </div>
                  <div className="text-xs text-text-muted">
                    to review
                  </div>
                </div>
                <ArrowRight className="size-4 shrink-0 text-text-muted" />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </AppShell>
  );
}

function DemoCard({ sc, runId }: { sc: Scorecard; runId: string }) {
  const m = sc.matching;
  const s = sc.safety;
  return (
    <Card className="mt-8 p-5">
      <div className="flex items-center gap-2">
        <Badge variant="accent">Live demo</Badge>
        <span className="text-xs text-text-muted">
          A frozen run of 1,672 real records, the AI pointed at gpt-4o
        </span>
      </div>

      <div className="mt-4 flex flex-col gap-5 sm:flex-row sm:flex-wrap sm:gap-x-12">
        <Figure
          value={`${(m.auto_match_rate * 100).toFixed(1)}%`}
          label="verified automatically"
          tone="positive"
        />
        <Figure
          value={s ? rupees(s.rupees_at_risk_minor) : "n/a"}
          label="held for a person"
          tone="attention"
        />
        <Figure value={`${sc.exceptions.total}`} label="open exceptions" />
      </div>

      <p className="mt-4 border-t border-border pt-4 text-sm text-text-muted">
        Arbiter never closes an item on its own. Every proposal waits for a
        person to confirm it. Re-running the same inputs produced an{" "}
        {s?.replay_divergence ? "different" : "identical"} result, and{" "}
        {m.false_match_rate === 0
          ? "no matches were wrong"
          : `${(m.false_match_rate * 100).toFixed(1)}% of matches were wrong`}
        .
      </p>

      <Link
        href={`/runs/${runId}`}
        className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-accent-ink transition-colors [transition-duration:120ms] hover:bg-accent/90"
      >
        Open the cockpit <ArrowRight className="size-4" />
      </Link>
    </Card>
  );
}

function Figure({
  value,
  label,
  tone,
}: {
  value: string;
  label: string;
  tone?: "positive" | "attention";
}) {
  return (
    <div>
      <div
        className={`text-lg font-semibold tabular-nums sm:text-xl ${
          tone === "positive"
            ? "text-positive"
            : tone === "attention"
              ? "text-attention"
              : ""
        }`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-sm text-text-muted">{label}</div>
    </div>
  );
}
