"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "@/components/ui/toast";

import {
  api,
  type EvidenceDrawer,
  type ReconException,
  type RunSummary,
  type Scorecard,
} from "@/lib/api";
import { actionLabel } from "@/lib/vocab";
import { useMediaQuery } from "@/lib/use-media-query";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Verdict } from "@/components/cockpit/Verdict";
import { Queue } from "@/components/cockpit/Queue";
import { Evidence } from "@/components/cockpit/Evidence";

const OPEN_STATUSES = new Set([
  "open",
  "proposed",
  "escalated",
  "security_review",
  "budget_exceeded",
]);

export function Cockpit({
  runId,
  run,
  scorecard,
  initialExceptions,
}: {
  runId: string;
  run: RunSummary;
  scorecard: Scorecard | null;
  initialExceptions: ReconException[];
}) {
  const [exceptions, setExceptions] = useState(initialExceptions);
  // start on the biggest open item so the evidence panel is never empty;
  // a ?exc=<id> deep link is applied after mount (below) to avoid an SSR mismatch
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    const open = initialExceptions.filter((e) => OPEN_STATUSES.has(e.status));
    return (
      [...open].sort(
        (a, b) =>
          Math.abs(b.amount_impact_minor) - Math.abs(a.amount_impact_minor),
      )[0]?.id ?? null
    );
  });
  const [sheetOpen, setSheetOpen] = useState(false);
  const [drawer, setDrawer] = useState<EvidenceDrawer | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  const select = useCallback((id: string) => {
    setSelectedId(id);
    setSheetOpen(true);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("exc", id);
      window.history.replaceState(null, "", url);
    }
  }, []);

  // residual from the loaded drawer sharpens that row's plain summary
  const residualById = useMemo(() => {
    const m: Record<string, number | null> = {};
    if (drawer) {
      m[drawer.exception.id] = drawer.decompositions[0]?.residual_minor ?? null;
    }
    return m;
  }, [drawer]);

  // apply a ?exc=<id> deep link once, after hydration
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("exc");
    if (q && exceptions.some((e) => e.id === q)) setSelectedId(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = useCallback(async () => {
    try {
      const r = await api.exceptions(runId);
      setExceptions(r.exceptions);
    } catch {
      /* keep what we have */
    }
  }, [runId]);

  useEffect(() => {
    if (!selectedId) {
      setDrawer(null);
      return;
    }
    let live = true;
    setDrawerLoading(true);
    api
      .drawer(runId, selectedId)
      .then((d) => live && setDrawer(d))
      .catch(() => live && setDrawer(null))
      .finally(() => live && setDrawerLoading(false));
    return () => {
      live = false;
    };
  }, [runId, selectedId]);

  const openIds = useMemo(
    () => exceptions.filter((e) => OPEN_STATUSES.has(e.status)).map((e) => e.id),
    [exceptions],
  );

  const resolve = useCallback(
    async (action: string) => {
      if (!selectedId) return;
      const id = selectedId;
      setBusy(true);
      try {
        const res = await api.resolve(runId, id, action, "");
        // optimistically move the item to "done" so the queue reacts at once
        setExceptions((prev) =>
          prev.map((e) =>
            e.id === id
              ? { ...e, status: "resolved", resolution: { action } }
              : e,
          ),
        );
        // advance to the next open item
        const nextOpen = openIds.filter((x) => x !== id);
        const i = openIds.indexOf(id);
        setSelectedId(nextOpen[Math.min(i, nextOpen.length - 1)] ?? null);

        if (res?.demo) {
          toast(`${actionLabel(action)} — marked resolved`, {
            description:
              "The demo is read-only. A live run would close this and draft a matching rule for next cycle.",
          });
        } else {
          toast(`${actionLabel(action)}`, {
            description: "Closed and kept in the audit trail.",
          });
          await refresh();
        }
      } catch {
        toast("Couldn't save that", {
          description:
            "The reconciliation service didn't accept the change. Try again.",
        });
      } finally {
        setBusy(false);
      }
    },
    [runId, selectedId, openIds, refresh],
  );

  const exportRun = useCallback(() => {
    const blob = new Blob(
      [JSON.stringify({ run, scorecard, exceptions }, null, 2)],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `arbiter-run-${runId.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast("Downloaded the run", {
      description: "Scorecard, exceptions, and the run summary as JSON.",
    });
  }, [run, scorecard, exceptions, runId]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLSelectElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;
      const idx = selectedId ? openIds.indexOf(selectedId) : -1;
      if (e.key === "j") {
        e.preventDefault();
        const next =
          openIds[Math.min(idx + 1, openIds.length - 1)] ?? openIds[0];
        if (next) setSelectedId(next);
      } else if (e.key === "k") {
        e.preventDefault();
        const prev = openIds[Math.max(idx - 1, 0)];
        if (prev) setSelectedId(prev);
      } else if (e.key === "a" && selectedId) {
        resolve("accept_variance");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openIds, selectedId, resolve]);

  const evidenceNode = (
    <Evidence
      drawer={drawerLoading ? null : drawer}
      onResolve={resolve}
      busy={busy}
    />
  );

  return (
    <AppShell
      width="wide"
      context={
        <span className="flex items-center gap-x-2">
          <span className="text-text">Reconciliation run</span>
          <span className="hidden font-mono text-text-muted sm:inline">
            {runId.slice(0, 8)}
          </span>
          <span className="hidden text-text-muted sm:inline">
            {run.records.toLocaleString("en-IN")} records
          </span>
        </span>
      }
      actions={
        <div className="hidden items-center gap-2 sm:flex">
          <Button variant="secondary" size="sm" onClick={exportRun}>
            Export
          </Button>
        </div>
      }
    >
      {scorecard && (
        <Verdict
          scorecard={scorecard}
          exceptions={exceptions}
          onPick={setSelectedId}
        />
      )}

      <div className="mt-6 lg:grid lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-8">
        <Queue
          exceptions={exceptions}
          selectedId={selectedId}
          onSelect={select}
          residualById={residualById}
        />

        {isDesktop && (
          <aside className="sticky top-20 hidden max-h-[calc(100vh-6rem)] min-h-[420px] flex-col self-start overflow-hidden rounded-lg border border-border bg-surface lg:flex">
            {evidenceNode}
          </aside>
        )}
      </div>

      {!isDesktop && (
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent
            side="right"
            className="flex w-full flex-col overflow-hidden p-0 sm:max-w-md"
          >
            <SheetTitle className="sr-only">Evidence</SheetTitle>
            {evidenceNode}
          </SheetContent>
        </Sheet>
      )}
    </AppShell>
  );
}
