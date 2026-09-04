"use client";

import * as React from "react";
import { Monitor, Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";

type Theme = "light" | "dark" | "system";
const ORDER: Theme[] = ["system", "light", "dark"];
const ICON = { system: Monitor, light: Sun, dark: Moon } as const;

function apply(t: Theme) {
  const el = document.documentElement;
  if (t === "system") el.removeAttribute("data-theme");
  else el.setAttribute("data-theme", t);
  try {
    if (t === "system") localStorage.removeItem("arbiter-theme");
    else localStorage.setItem("arbiter-theme", t);
  } catch {
    /* private mode */
  }
}

/** docs/05 §3.5 — both themes are first-class; the control is visible, not
 *  buried. Cycles system → light → dark. */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = React.useState<Theme>("system");
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
    try {
      const stored = localStorage.getItem("arbiter-theme");
      setTheme(stored === "light" || stored === "dark" ? stored : "system");
    } catch {
      /* private mode */
    }
  }, []);

  const Icon = ICON[theme];
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]!;

  return (
    <button
      type="button"
      aria-label={`Theme: ${theme}. Switch to ${next}.`}
      title={`Theme: ${theme}`}
      onClick={() => {
        setTheme(next);
        apply(next);
      }}
      className={cn(
        "inline-grid size-9 place-items-center rounded-md border border-border bg-surface text-text-muted transition-colors [transition-duration:120ms] hover:bg-surface-2 hover:text-text",
        className,
      )}
    >
      {mounted ? <Icon className="size-4" /> : <Monitor className="size-4" />}
    </button>
  );
}
