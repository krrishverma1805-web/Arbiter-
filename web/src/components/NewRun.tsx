"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export function NewRun({
  specs,
  datasets,
}: {
  specs: { name: string }[];
  datasets: { name: string }[];
}) {
  const router = useRouter();
  const [spec, setSpec] = useState(specs[0]?.name ?? "razorpay-settlement");
  const [dataset, setDataset] = useState(datasets[0]?.name ?? "seed");
  const [noAi, setNoAi] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.startRun(spec, dataset, noAi);
      router.push(`/runs/${r.run_id}`);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 flex flex-wrap items-end gap-3 rounded border border-border bg-surface p-4">
      <label className="text-sm">
        <span className="block text-xs text-muted">spec</span>
        <select
          className="mt-1 rounded border border-border bg-bg px-2 py-1"
          value={spec}
          onChange={(e) => setSpec(e.target.value)}
        >
          {specs.map((s) => (
            <option key={s.name}>{s.name}</option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <span className="block text-xs text-muted">dataset</span>
        <select
          className="mt-1 rounded border border-border bg-bg px-2 py-1"
          value={dataset}
          onChange={(e) => setDataset(e.target.value)}
        >
          {datasets.map((d) => (
            <option key={d.name}>{d.name}</option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1.5 text-sm">
        <input type="checkbox" checked={noAi} onChange={(e) => setNoAi(e.target.checked)} />
        --no-ai
      </label>
      <button
        onClick={go}
        disabled={busy}
        className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        {busy ? "reconciling…" : "reconcile"}
      </button>
      {err && <span className="text-sm text-critical">{err}</span>}
    </div>
  );
}
