"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, llmConfig, setLlmConfig } from "@/lib/api";

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

  const existing = typeof window !== "undefined" ? llmConfig() : null;
  const [showKey, setShowKey] = useState(false);
  const [provider, setProvider] = useState<"openai" | "anthropic">(
    existing?.provider ?? "openai",
  );
  const [key, setKey] = useState("");
  const [model, setModel] = useState(existing?.model ?? "");
  const [keyMsg, setKeyMsg] = useState(existing?.key ? "key saved in this browser" : "");

  function saveKey() {
    const k = key.trim();
    if (!k) {
      setLlmConfig(null);
      setKeyMsg("cleared");
      return;
    }
    setLlmConfig({
      provider,
      key: k,
      model: model.trim() || (provider === "openai" ? "gpt-4o" : "claude-opus-5"),
    });
    setKey("");
    setKeyMsg(`saved · ${provider} / ${model.trim() || (provider === "openai" ? "gpt-4o" : "claude-opus-5")}`);
  }

  async function go() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.startRun(spec, dataset, noAi);
      // watch the agent think when AI is on; jump straight to the cockpit otherwise
      router.push(noAi ? `/runs/${r.run_id}` : `/runs/${r.run_id}/live`);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 rounded border border-border bg-surface">
      <div className="flex flex-wrap items-end gap-3 p-4">
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

      <button
        onClick={() => setShowKey((s) => !s)}
        className="w-full border-t border-border px-4 py-2 text-left text-xs text-muted hover:text-text"
      >
        {showKey ? "▾" : "▸"} Bring your own API key{" "}
        {existing?.key ? (
          <span className="text-positive">· {existing.provider} / {existing.model}</span>
        ) : (
          <span>· the agent uses the server key otherwise</span>
        )}
      </button>
      {showKey && (
        <div className="border-t border-border p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="block text-xs text-muted">provider</span>
              <select
                className="mt-1 rounded border border-border bg-bg px-2 py-1"
                value={provider}
                onChange={(e) => setProvider(e.target.value as "openai" | "anthropic")}
              >
                <option value="openai">openai</option>
                <option value="anthropic">anthropic</option>
              </select>
            </label>
            <label className="min-w-[200px] flex-1 text-sm">
              <span className="block text-xs text-muted">API key</span>
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={existing?.key ? "•••• saved" : "sk-…"}
                className="mt-1 w-full rounded border border-border bg-bg px-2 py-1 font-mono"
              />
            </label>
            <label className="text-sm">
              <span className="block text-xs text-muted">model</span>
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={provider === "openai" ? "gpt-4o" : "claude-opus-5"}
                className="mt-1 w-36 rounded border border-border bg-bg px-2 py-1 font-mono"
              />
            </label>
            <button
              onClick={saveKey}
              className="rounded border border-border px-3 py-1.5 text-sm hover:border-accent hover:text-accent"
            >
              save
            </button>
            {keyMsg && <span className="text-xs text-muted">{keyMsg}</span>}
          </div>
          <p className="mt-3 text-[11px] text-muted">
            Stored only in this browser. Sent as an{" "}
            <span className="font-mono">X-LLM-Key</span> header on the next run and used for that run
            only — never written to disk or the event log. Needs the API in synchronous mode
            (the default).
          </p>
        </div>
      )}
    </div>
  );
}
