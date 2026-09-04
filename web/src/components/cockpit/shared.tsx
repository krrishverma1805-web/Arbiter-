import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  categoryLabel,
  categoryTone,
  statusLabel,
  statusTone,
} from "@/lib/vocab";

/** Category chip — plain label, tone by severity, always bordered. */
export function CategoryChip({
  category,
  className,
}: {
  category: string | null | undefined;
  className?: string;
}) {
  return (
    <Badge variant={categoryTone(category)} className={className}>
      {categoryLabel(category)}
    </Badge>
  );
}

/** Status chip — closed vocabulary, plain words. */
export function StatusChip({ status }: { status: string }) {
  return <Badge variant={statusTone(status)}>{statusLabel(status)}</Badge>;
}

/** Confidence as a three-step dot, not number noise. */
export function ConfidenceDot({ value }: { value: number | null }) {
  const level =
    value == null ? "unknown" : value >= 0.85 ? "high" : value >= 0.6 ? "mid" : "low";
  const label =
    level === "unknown"
      ? "Confidence not scored"
      : `Arbiter's confidence: ${level}`;
  return (
    <span
      title={label}
      aria-label={label}
      className="inline-flex items-center gap-0.5"
    >
      {[0, 1, 2].map((i) => {
        const filled =
          (level === "high" && i < 3) ||
          (level === "mid" && i < 2) ||
          (level === "low" && i < 1);
        return (
          <span
            key={i}
            className={cn(
              "size-1.5 rounded-full",
              filled
                ? level === "low"
                  ? "bg-attention"
                  : "bg-positive"
                : "bg-border",
            )}
          />
        );
      })}
    </span>
  );
}

/** A single big number with a plain label. Used across the verdict strip. */
export function Stat({
  value,
  label,
  sub,
  tone,
}: {
  value: string;
  label: string;
  sub?: string;
  tone?: "positive" | "attention" | "critical";
}) {
  return (
    <div>
      <div
        className={cn(
          "text-lg font-semibold tabular-nums sm:text-xl",
          tone === "positive" && "text-positive",
          tone === "attention" && "text-attention",
          tone === "critical" && "text-critical",
        )}
      >
        {value}
      </div>
      <div className="mt-0.5 text-sm text-text">{label}</div>
      {sub && <div className="text-xs text-text-muted">{sub}</div>}
    </div>
  );
}
