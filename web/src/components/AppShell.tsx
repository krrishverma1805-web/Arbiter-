import Link from "next/link";

import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/ThemeToggle";
import { CommandKButton } from "@/components/CommandPalette";

/** The one shell every screen sits in. docs/05 §2 — a run is the atomic unit;
 *  the header always says which run you're in and offers re-run / export. */
export function AppShell({
  children,
  context,
  actions,
  width = "wide",
}: {
  children: React.ReactNode;
  /** Run context line, shown in the header (spec · cycle · records · age). */
  context?: React.ReactNode;
  /** Right-aligned actions for the current screen (re-run, export…). */
  actions?: React.ReactNode;
  /** `wide` for the cockpit grid, `read` for forms and lists, `full` bleeds. */
  width?: "wide" | "read" | "full";
}) {
  const inner = cn(
    width === "read" && "max-w-4xl",
    width === "wide" && "max-w-[1280px]",
  );
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-bg/95 backdrop-blur supports-[backdrop-filter]:bg-bg/80">
        <div className={cn("mx-auto flex h-16 items-center gap-4 px-5 sm:px-8", inner)}>
          <Link
            href="/"
            className="flex flex-none items-center gap-2 text-[15px] font-semibold tracking-tight"
          >
            <span className="size-2 rounded-full bg-accent" />
            Arbiter
          </Link>

          {context ? (
            <div className="flex min-w-0 flex-1 items-center gap-3">
              <span className="text-border">/</span>
              <div className="min-w-0 flex-1 truncate text-sm text-text-muted">
                {context}
              </div>
            </div>
          ) : (
            <div className="flex-1" />
          )}

          <div className="flex flex-none items-center gap-2">
            {actions}
            <CommandKButton />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main
        className={cn(
          "mx-auto w-full flex-1 overflow-x-clip px-5 py-12 sm:px-8",
          inner,
          width === "full" && "max-w-none px-0 py-0 sm:px-0",
        )}
      >
        {children}
      </main>
    </div>
  );
}
