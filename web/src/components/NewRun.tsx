"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api, llmConfig, setLlmConfig } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

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
  const [useAi, setUseAi] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);

  async function go() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.startRun(spec, dataset, !useAi);
      router.push(useAi ? `/runs/${r.run_id}/live` : `/runs/${r.run_id}`);
    } catch {
      setErr(
        "The reconciliation service didn't accept the run. Check it's running and try again.",
      );
      setBusy(false);
    }
  }

  return (
    <Card className="mt-4 p-5">
      <div className="flex flex-wrap items-end gap-5">
        <div className="grid w-44 gap-1.5">
          <Label htmlFor="spec">Spec</Label>
          <Select id="spec" value={spec} onChange={(e) => setSpec(e.target.value)}>
            {specs.map((s) => (
              <option key={s.name}>{s.name}</option>
            ))}
          </Select>
        </div>
        <div className="grid w-44 gap-1.5">
          <Label htmlFor="dataset">Dataset</Label>
          <Select
            id="dataset"
            value={dataset}
            onChange={(e) => setDataset(e.target.value)}
          >
            {datasets.map((d) => (
              <option key={d.name}>{d.name}</option>
            ))}
          </Select>
        </div>
        <label className="flex h-10 items-center gap-2 text-sm">
          <Checkbox
            checked={useAi}
            onCheckedChange={(v) => setUseAi(v === true)}
          />
          Investigate exceptions with AI
        </label>
        <Button variant="primary" onClick={go} disabled={busy}>
          {busy ? "Starting…" : "Reconcile"}
        </Button>
      </div>

      {err && <p className="mt-3 text-sm text-critical">{err}</p>}

      <div className="mt-4 border-t border-border pt-3">
        <button
          onClick={() => setShowKey((s) => !s)}
          className="text-xs text-text-muted transition-colors [transition-duration:120ms] hover:text-text"
        >
          {showKey ? "Hide the AI key field" : "Use your own AI key"}
        </button>
      </div>
      {showKey && <KeyForm />}
    </Card>
  );
}

function KeyForm() {
  const existing = typeof window !== "undefined" ? llmConfig() : null;
  const [provider, setProvider] = useState<"openai" | "anthropic">(
    existing?.provider ?? "openai",
  );
  const [key, setKey] = useState("");
  const [model, setModel] = useState(existing?.model ?? "");
  const [msg, setMsg] = useState(
    existing?.key ? `Saved: ${existing.provider} / ${existing.model}` : "",
  );

  function save() {
    const k = key.trim();
    if (!k) {
      setLlmConfig(null);
      setMsg("Cleared. The server key will be used.");
      return;
    }
    const m =
      model.trim() || (provider === "openai" ? "gpt-4o" : "claude-opus-5");
    setLlmConfig({ provider, key: k, model: m });
    setKey("");
    setMsg(`Saved: ${provider} / ${m}`);
  }

  return (
    <div className="mt-3 rounded-md border border-border bg-surface-2/40 p-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="grid w-44 gap-1.5">
          <Label htmlFor="provider">Provider</Label>
          <Select
            id="provider"
            value={provider}
            onChange={(e) =>
              setProvider(e.target.value as "openai" | "anthropic")
            }
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </Select>
        </div>
        <div className="grid min-w-[200px] flex-1 gap-1.5">
          <Label htmlFor="apikey">API key</Label>
          <Input
            id="apikey"
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={existing?.key ? "•••• saved" : "sk-…"}
            className="font-mono"
          />
        </div>
        <div className="grid w-40 gap-1.5">
          <Label htmlFor="model">Model</Label>
          <Input
            id="model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={provider === "openai" ? "gpt-4o" : "claude-opus-5"}
            className="w-36 font-mono"
          />
        </div>
        <Button variant="secondary" onClick={save}>
          Save
        </Button>
      </div>
      {msg && <p className="mt-2 text-xs text-text-muted">{msg}</p>}
      <p className="mt-3 text-xs text-text-muted">
        Stored only in this browser. Sent as a header on the next run and used
        for that run only. Never written to disk or the event log.
      </p>
    </div>
  );
}
