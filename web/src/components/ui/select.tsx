import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

/** Styled native <select> — accessible by default, calm, no portal. Use for
 *  short option lists (spec, dataset, provider). */
const Select = React.forwardRef<
  HTMLSelectElement,
  React.ComponentProps<"select">
>(({ className, children, ...props }, ref) => (
  <div className="relative block w-full">
    <select
      ref={ref}
      className={cn(
        "h-10 w-full appearance-none rounded-md border border-border bg-surface pl-3 pr-8 text-sm text-text transition-colors [transition-duration:120ms]",
        "focus-visible:outline-none focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </select>
    <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-text-muted" />
  </div>
));
Select.displayName = "Select";

export { Select };
