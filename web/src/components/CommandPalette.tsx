"use client";

import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, apiKey, setApiKey, type RunSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

const OPEN_EVENT = "arbiter:cmdk";

/** Header button that opens the palette — pairs with the ⌘K shortcut. */
export function CommandKButton({ className }: { className?: string }) {
  return (
    <button
      type="button"
      aria-label="Open command menu"
      onClick={() => window.dispatchEvent(new Event(OPEN_EVENT))}
      className={cn(
        "hidden h-9 items-center gap-1 rounded-md border border-border bg-surface px-2 text-text-muted transition-colors [transition-duration:120ms] hover:bg-surface-2 hover:text-text sm:inline-flex",
        className,
      )}
    >
      <span className="font-mono text-[11px]">⌘K</span>
    </button>
  );
}

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
    function onOpen() {
      setOpen(true);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onOpen);
    };
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
      if (t === "system") localStorage.removeItem("arbiter-theme");
      else localStorage.setItem("arbiter-theme", t);
    } catch {
      /* private mode */
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-text/40 pt-[15vh]"
      onClick={() => setOpen(false)}
    >
      <Command
        label="Command menu"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-lg border border-border bg-surface shadow"
      >
        <Command.Input
          autoFocus
          placeholder="Jump to a run, start a reconciliation, switch theme…"
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm outline-none placeholder:text-text-muted"
        />
        <Command.List className="max-h-80 overflow-y-auto p-2">
          <Command.Empty className="px-3 py-6 text-center text-sm text-text-muted">
            No matches.
          </Command.Empty>

          <Command.Group
            heading="Go"
            className="px-1 text-[11px] uppercase tracking-wide text-text-muted"
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
            className="mt-2 px-1 text-[11px] uppercase tracking-wide text-text-muted"
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
              className="mt-2 px-1 text-[11px] uppercase tracking-wide text-text-muted"
            >
              {runs.slice(0, 8).map((r) => (
                <Item
                  key={r.run_id}
                  onSelect={() => run(() => router.push(`/runs/${r.run_id}`))}
                >
                  <span className="font-mono">{r.run_id.slice(0, 8)}</span>
                  <span className="ml-2 text-text-muted">
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
      className="flex cursor-pointer items-center rounded-md px-3 py-2 text-sm aria-selected:bg-surface-2"
    >
      {children}
    </Command.Item>
  );
}
