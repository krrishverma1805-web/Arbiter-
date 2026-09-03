"use client";

import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, apiKey, setApiKey, type RunSummary } from "@/lib/api";

/** ⌘K / Ctrl-K everywhere: navigate, jump to a run, flip the theme. Page-local
 *  shortcuts (j/k/e/a/w in the cockpit) stay where they are. */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open && runs.length === 0)
      api
        .listRuns()
        .then((r) => setRuns(r.runs))
        .catch(() => {});
  }, [open, runs.length]);

  const run = useCallback((fn: () => void) => {
    setOpen(false);
    fn();
  }, []);

  const setTheme = (t: "light" | "dark" | "system") => {
    const el = document.documentElement;
    if (t === "system") el.removeAttribute("data-theme");
    else el.setAttribute("data-theme", t);
    try {
      localStorage.setItem("arbiter-theme", t);
    } catch {
      /* private mode */
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[15vh]"
      onClick={() => setOpen(false)}
    >
      <Command
        label="Command menu"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
      >
        <Command.Input
          autoFocus
          placeholder="Jump to a run, start a reconciliation, switch theme…"
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm outline-none"
        />
        <Command.List className="max-h-80 overflow-y-auto p-2">
          <Command.Empty className="px-3 py-6 text-center text-sm text-muted">
            No matches.
          </Command.Empty>

          <Command.Group
            heading="Go"
            className="px-1 text-[11px] uppercase tracking-wide text-muted"
          >
            <Item onSelect={() => run(() => router.push("/"))}>All runs</Item>
            <Item
              onSelect={() =>
                run(() => {
                  const cur = apiKey() ?? "";
                  const next = window.prompt(
                    "Arbiter API key (blank to clear)",
                    cur,
                  );
                  if (next !== null) {
                    setApiKey(next.trim() || null);
                    location.reload();
                  }
                })
              }
            >
              {apiKey() ? "Change API key" : "Set API key"}
            </Item>
          </Command.Group>

          <Command.Group
            heading="Theme"
            className="mt-2 px-1 text-[11px] uppercase tracking-wide text-muted"
          >
            <Item onSelect={() => run(() => setTheme("light"))}>Light</Item>
            <Item onSelect={() => run(() => setTheme("dark"))}>Dark</Item>
            <Item onSelect={() => run(() => setTheme("system"))}>
              Match system
            </Item>
          </Command.Group>

          {runs.length > 0 && (
            <Command.Group
              heading="Recent runs"
              className="mt-2 px-1 text-[11px] uppercase tracking-wide text-muted"
            >
              {runs.slice(0, 8).map((r) => (
                <Item
                  key={r.run_id}
                  onSelect={() => run(() => router.push(`/runs/${r.run_id}`))}
                >
                  <span className="font-mono">{r.run_id.slice(0, 8)}</span>
                  <span className="ml-2 text-muted">
                    {r.exceptions} exceptions · {r.status ?? "…"}
                  </span>
                </Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  );
}

function Item({
  children,
  onSelect,
}: {
  children: React.ReactNode;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex cursor-pointer items-center rounded-md px-3 py-2 text-sm aria-selected:bg-accent/10"
    >
      {children}
    </Command.Item>
  );
}
