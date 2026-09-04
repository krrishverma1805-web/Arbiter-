import * as React from "react";

import { cn } from "@/lib/utils";

/** A keyboard key. docs/05 §2.2 — the queue is keyboard-first, so keys are
 *  shown, not hidden. */
const Kbd = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLElement>
>(({ className, ...props }, ref) => (
  <kbd
    ref={ref}
    className={cn(
      "inline-flex h-[22px] min-w-[22px] items-center justify-center rounded border border-border border-b-2 bg-surface-2 px-1.5 font-mono text-xs font-medium text-text-muted",
      className,
    )}
    {...props}
  />
));
Kbd.displayName = "Kbd";

export { Kbd };
