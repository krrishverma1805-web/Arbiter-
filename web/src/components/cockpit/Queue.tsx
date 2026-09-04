"use client";

import { useMemo, useState } from "react";

import { rupees, type ReconException } from "@/lib/api";
import {
  categoryLabel,
  classifiedByLabel,
  plainSummary,
} from "@/lib/vocab";
import { cn } from "@/lib/utils";
import { Select } from "@/components/ui/select";
import { Kbd } from "@/components/ui/kbd";
import { CategoryChip, ConfidenceDot, StatusChip } from "./shared";

type Sort = "impact" | "confidence" | "category";

const OPEN_STATUSES = new Set([
  "open",
  "proposed",
  "escalated",
  "security_review",
  "budget_exceeded",
]);

export function Queue({
  exceptions,
  selectedId,
  onSelect,
  residualById,
}: {
  exceptions: ReconException[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  residualById: Record<string, number | null>;
}) {
  const [filter, setFilter] = useState<"needs-review" | "all" | "resolved">(
    "needs-review",
  );
  const [category, setCategory] = useState<string>("all");
  const [sort, setSort] = useState<Sort>("impact");

  const categories = useMemo(
    () =>
      Array.from(
        new Set(exceptions.map((e) => e.category).filter(Boolean) as string[]),
      ).sort(),
    [exceptions],
  );

  const rows = useMemo(() => {
    let r = exceptions.filter((e) => {
      if (filter === "needs-review") return OPEN_STATUSES.has(e.status);
      if (filter === "resolved") return !OPEN_STATUSES.has(e.status);
      return true;
    });
    if (category !== "all") r = r.filter((e) => e.category === category);
    return [...r].sort((a, b) => {
      if (sort === "impact")
        return (
          Math.abs(b.amount_impact_minor) - Math.abs(a.amount_impact_minor)
        );
      if (sort === "confidence")
        return (a.confidence ?? 1) - (b.confidence ?? 1);
      return categoryLabel(a.category).localeCompare(categoryLabel(b.category));
    });
  }, [exceptions, filter, category, sort]);

  const totalAtStake = rows.reduce(
    (s, e) => s + Math.abs(e.amount_impact_minor),
    0,
  );

  return (
    <div className="flex min-h-0 flex-col">
      {/* controls */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
        <div className="flex rounded-md border border-border p-0.5 text-xs">
          {(
            [
              ["needs-review", "Needs review"],
              ["resolved", "Done"],
              ["all", "All"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={cn(
                "rounded px-2.5 py-1 transition-colors [transition-duration:120ms]",
                filter === k
                  ? "bg-surface-2 font-medium text-text"
                  : "text-text-muted hover:text-text",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="w-40">
          <Select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="h-8 text-xs"
            aria-label="Filter by category"
          >
            <option value="all">All types</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {categoryLabel(c)}
              </option>
            ))}
          </Select>
        </div>

        <div className="w-44">
          <Select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            className="h-8 text-xs"
            aria-label="Sort"
          >
            <option value="impact">Most money first</option>
            <option value="confidence">Least confident first</option>
            <option value="category">By type</option>
          </Select>
        </div>

        <span className="ml-auto whitespace-nowrap text-xs text-text-muted">
          {rows.length} {rows.length === 1 ? "item" : "items"},{" "}
          <span className="font-mono">{rupees(totalAtStake)}</span>
        </span>
      </div>

      {/* header */}
      <div className="grid grid-cols-[1fr_auto] gap-4 px-1 py-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
        <span>Exception</span>
        <span className="text-right">Impact</span>
      </div>

      {/* rows */}
      {rows.length === 0 ? (
        <p className="px-1 py-16 text-center text-sm text-positive">
          Nothing here. Everything in this view is tied or resolved.
        </p>
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {rows.map((e) => {
            const active = e.id === selectedId;
            return (
              <li key={e.id}>
                <button
                  onClick={() => onSelect(e.id)}
                  aria-current={active}
                  className={cn(
                    "relative grid w-full grid-cols-[1fr_auto] items-start gap-4 px-1 py-3 text-left transition-colors [transition-duration:120ms]",
                    active ? "bg-accent/5" : "hover:bg-surface-2",
                  )}
                >
                  {active && (
                    <span className="absolute inset-y-0 left-0 w-0.5 bg-accent" />
                  )}
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <CategoryChip category={e.category} />
                      <StatusChip status={e.status} />
                      <ConfidenceDot value={e.confidence} />
                    </div>
                    <p className="mt-1.5 text-sm leading-snug text-text">
                      {plainSummary(e, residualById[e.id])}
                    </p>
                    <p className="mt-1 text-xs text-text-muted">
                      {e.record_ids?.length ?? 0} record
                      {(e.record_ids?.length ?? 0) === 1 ? "" : "s"} ·{" "}
                      {classifiedByLabel(e.classified_by)}
                    </p>
                  </div>
                  <div className="pt-0.5 text-right">
                    <div
                      className={cn(
                        "font-mono text-sm tabular-nums",
                        e.amount_impact_minor < 0 && "text-attention",
                      )}
                    >
                      {e.impact_display ?? rupees(e.amount_impact_minor)}
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
        <span className="flex items-center gap-1">
          <Kbd>J</Kbd>
          <Kbd>K</Kbd> move
        </span>
        <span className="flex items-center gap-1">
          <Kbd>Enter</Kbd> open evidence
        </span>
        <span className="flex items-center gap-1">
          <Kbd>A</Kbd> accept
        </span>
      </p>
    </div>
  );
}
