"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

/* A tiny self-contained toast. No external toast library — this app only needs
 * "title + optional description, auto-dismiss", and it must never break. */

export interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone?: "default" | "positive" | "critical";
}

type Listener = (toasts: ToastItem[]) => void;

interface ToastStore {
  toasts: ToastItem[];
  listeners: Set<Listener>;
}

// One store, shared no matter how the bundler splits this module.
const g = globalThis as typeof globalThis & { __arbiterToasts?: ToastStore };
const store: ToastStore = (g.__arbiterToasts ??= {
  toasts: [],
  listeners: new Set(),
});

function emit() {
  for (const l of store.listeners) l(store.toasts);
}
function remove(id: number) {
  store.toasts = store.toasts.filter((x) => x.id !== id);
  emit();
}

export function toast(
  title: string,
  opts?: { description?: string; tone?: ToastItem["tone"] },
) {
  const id = Date.now() + Math.random();
  store.toasts = [
    ...store.toasts,
    { id, title, description: opts?.description, tone: opts?.tone },
  ];
  emit();
  setTimeout(() => remove(id), 5000);
}

export function Toaster() {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
    const l: Listener = (t) => setToasts([...t]);
    store.listeners.add(l);
    l(store.toasts);
    return () => {
      store.listeners.delete(l);
    };
  }, []);

  if (!mounted) return null;

  return createPortal(
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={cn(
            "pointer-events-auto flex items-start gap-3 rounded-lg border bg-surface p-3 shadow",
            "animate-in slide-in-from-bottom-2 fade-in [animation-duration:150ms]",
            t.tone === "positive" && "border-positive/40",
            t.tone === "critical" && "border-critical/40",
            (!t.tone || t.tone === "default") && "border-border",
          )}
        >
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-text">{t.title}</div>
            {t.description && (
              <div className="mt-0.5 text-xs leading-snug text-text-muted">
                {t.description}
              </div>
            )}
          </div>
          <button
            aria-label="Dismiss"
            onClick={() => remove(t.id)}
            className="shrink-0 text-text-muted transition-colors [transition-duration:120ms] hover:text-text"
          >
            <X className="size-4" />
          </button>
        </div>
      ))}
    </div>,
    document.body,
  );
}
