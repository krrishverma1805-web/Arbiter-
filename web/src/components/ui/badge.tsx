import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// docs/05 §5 — status is conveyed by chip *label + shape*, never colour alone.
// Every variant carries a border so it reads without colour perception.
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium leading-none",
  {
    variants: {
      variant: {
        neutral: "border-border bg-surface-2 text-text-muted",
        accent: "border-accent/30 bg-accent/10 text-accent",
        positive: "border-positive/30 bg-positive/10 text-positive",
        attention: "border-attention/40 bg-attention/10 text-attention",
        critical: "border-critical/40 bg-critical/10 text-critical",
        outline: "border-border text-text",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
