"use client";

import { useState } from "react";
import { toast } from "@/components/ui/toast";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Kbd } from "@/components/ui/kbd";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import CountUp from "@/components/reactbits/CountUp";

/* ── section scaffold ─────────────────────────────────────────────────────── */

const SECTIONS = [
  ["foundations", "Foundations"],
  ["typography", "Typography"],
  ["buttons", "Buttons"],
  ["status", "Status"],
  ["forms", "Forms"],
  ["surfaces", "Surfaces"],
  ["navigation", "Navigation"],
  ["feedback", "Feedback & motion"],
] as const;

function Section({
  id,
  title,
  intro,
  children,
}: {
  id: string;
  title: string;
  intro: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-24 border-b border-border py-10 last:border-b-0"
    >
      <div className="mb-6 max-w-2xl">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-text-muted">{intro}</p>
      </div>
      {children}
    </section>
  );
}

/** A single labelled specimen. */
function Specimen({
  label,
  className = "",
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className={`flex flex-wrap items-center gap-3 px-5 py-6 ${className}`}>
        {children}
      </div>
      <div className="border-t border-border bg-surface-2/50 px-4 py-2 text-xs text-text-muted">
        {label}
      </div>
    </div>
  );
}

/* ── data ─────────────────────────────────────────────────────────────────── */

const SWATCHES: [string, string, string][] = [
  ["Page", "--bg", "bg-bg"],
  ["Surface", "--surface", "bg-surface"],
  ["Surface 2", "--surface-2", "bg-surface-2"],
  ["Border", "--border", "bg-border"],
  ["Text", "--text", "bg-text"],
  ["Muted", "--text-muted", "bg-text-muted"],
  ["Accent", "--accent", "bg-accent"],
  ["Positive", "--positive", "bg-positive"],
  ["Attention", "--attention", "bg-attention"],
  ["Critical", "--critical", "bg-critical"],
];

const TYPE_SPECIMENS: [string, string, string][] = [
  ["text-xl", "Money is right.", "28 · display, scorecard headline only"],
  ["text-lg", "9 exceptions, ₹1.73L held", "20 · section heading"],
  ["text-base", "Bank credit has no settlement line", "16 · emphasis"],
  ["text-sm", "Likely a T+2 settlement into September.", "14 · body, the base size"],
  ["text-xs", "razorpay-settlement · seed · 2m ago", "13 · dense grid rows"],
];

/* ── page ─────────────────────────────────────────────────────────────────── */

export default function DesignSystemPage() {
  const [tab, setTab] = useState("queue");

  return (
    <AppShell width="wide" context="design system">
      <div className="mx-auto max-w-5xl lg:grid lg:grid-cols-[176px_minmax(0,1fr)] lg:gap-14">
        {/* section nav */}
        <nav className="mb-8 hidden lg:sticky lg:top-24 lg:mb-0 lg:block lg:self-start">
          <ul className="space-y-0.5 text-sm">
            {SECTIONS.map(([id, label]) => (
              <li key={id}>
                <a
                  href={`#${id}`}
                  className="block rounded-md px-2.5 py-1.5 text-text-muted transition-colors [transition-duration:120ms] hover:bg-surface-2 hover:text-text"
                >
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0">
          <header className="border-b border-border pb-9">
            <h1 className="text-xl font-semibold tracking-tight">
              Arbiter design system
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-relaxed text-text-muted">
              The primitive kit and shell every screen is built from. One accent,
              a warm neutral ground, amber for unfinished work, and almost no
              motion. Calm, legible, fast.
            </p>
          </header>

          <Section
            id="foundations"
            title="Foundations"
            intro="Ten colour tokens carry the whole system. Every value has a light and a dark form, defined once, so components never hard-code a colour."
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {SWATCHES.map(([name, token, cls]) => (
                <div
                  key={token}
                  className="overflow-hidden rounded-lg border border-border bg-surface"
                >
                  <div className={`h-14 border-b border-border ${cls}`} />
                  <div className="px-3 py-2.5">
                    <div className="text-sm font-medium">{name}</div>
                    <div className="mt-0.5 font-mono text-xs text-text-muted">
                      {token}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <Section
            id="typography"
            title="Typography"
            intro="Inter for the interface, JetBrains Mono for anything you would copy: ids, hashes, the identity equation. Six sizes, nothing between them."
          >
            <div className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
              {TYPE_SPECIMENS.map(([cls, sample, note]) => (
                <div
                  key={cls}
                  className="flex flex-col gap-1 px-6 py-4 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6"
                >
                  <span className={`${cls} font-semibold`}>{sample}</span>
                  <span className="shrink-0 font-mono text-xs text-text-muted">
                    {note}
                  </span>
                </div>
              ))}
              <div className="px-6 py-4">
                <div className="font-mono text-sm">
                  ₹8,240.00 − ₹165.00 − ₹29.70 = ₹8,045.30
                </div>
                <div className="mt-1 text-xs text-text-muted">
                  Money aligns on the decimal. Tabular figures everywhere.
                </div>
              </div>
            </div>
          </Section>

          <Section
            id="buttons"
            title="Buttons"
            intro="One primary action per surface. Everything else is secondary or quieter. Hover and press give a small, immediate response with no glow and no bounce."
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Specimen label="Primary, the one action">
                <Button variant="primary">Accept proposal</Button>
              </Specimen>
              <Specimen label="Secondary, everything else">
                <Button variant="secondary">Edit &amp; accept</Button>
              </Specimen>
              <Specimen label="Ghost, low emphasis">
                <Button variant="ghost">Won&apos;t fix</Button>
                <Button variant="link">View raw row</Button>
              </Specimen>
              <Specimen label="Danger, reject or dispute">
                <Button variant="danger">Raise dispute</Button>
              </Specimen>
              <Specimen label="Sizes">
                <Button size="sm" variant="secondary">
                  Small
                </Button>
                <Button variant="secondary">Default</Button>
                <Button size="lg" variant="primary">
                  Large
                </Button>
              </Specimen>
              <Specimen label="Disabled">
                <Button disabled>Reconcile</Button>
              </Specimen>
            </div>
          </Section>

          <Section
            id="status"
            title="Status"
            intro="A closed vocabulary. Every chip carries a border and a word, so it reads without colour perception. Amber means unfinished, never broken. Red is reserved for a broken identity."
          >
            <Specimen label="The full set">
              <Badge variant="neutral">open</Badge>
              <Badge variant="accent">proposed</Badge>
              <Badge variant="positive">resolved</Badge>
              <Badge variant="attention">low-confidence</Badge>
              <Badge variant="critical">false-match</Badge>
              <Badge variant="outline">won&apos;t-fix</Badge>
            </Specimen>
          </Section>

          <Section
            id="forms"
            title="Forms"
            intro="Label above the control, always. Native selects for short lists, so keyboard and screen-reader behaviour comes for free."
          >
            <Specimen label="spec · dataset · options" className="items-end gap-5">
              <div className="grid w-52 gap-1.5">
                <Label htmlFor="spec">Spec</Label>
                <Select id="spec" defaultValue="razorpay-settlement">
                  <option>razorpay-settlement</option>
                  <option>gst-2b</option>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="key">API key</Label>
                <Input
                  id="key"
                  type="password"
                  placeholder="sk-…"
                  className="w-52"
                />
              </div>
              <label className="flex h-10 items-center gap-2 text-sm">
                <Checkbox defaultChecked /> Investigate with AI
              </label>
            </Specimen>
          </Section>

          <Section
            id="surfaces"
            title="Surfaces"
            intro="A hairline border and a slightly lifted background. No drop shadows in the working views. Keys are shown, not hidden behind a help menu."
          >
            <Card>
              <CardHeader>
                <CardTitle>razorpay-settlement · Aug 2026</CardTitle>
                <CardDescription>
                  1,672 records · reconciled 2 minutes ago
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-text-muted">
                <span className="flex items-center gap-1.5">
                  <Kbd>j</Kbd> <Kbd>k</Kbd> move
                </span>
                <span className="flex items-center gap-1.5">
                  <Kbd>e</Kbd> open evidence
                </span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button className="underline decoration-dotted underline-offset-4">
                      false-match rate
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>
                    Matches Arbiter made that ground truth says are wrong.
                  </TooltipContent>
                </Tooltip>
              </CardContent>
            </Card>
          </Section>

          <Section
            id="navigation"
            title="Navigation"
            intro="Three surfaces in workflow order: the verdict, the work, the proof. On a laptop they sit side by side; on a phone they become tabs. The evidence drawer slides in beside the queue, never over it."
          >
            <div className="grid gap-3">
              <Specimen label="Tabs, the three surfaces">
                <Tabs value={tab} onValueChange={setTab} className="w-full">
                  <TabsList>
                    <TabsTrigger value="score">Scorecard</TabsTrigger>
                    <TabsTrigger value="queue">Queue</TabsTrigger>
                    <TabsTrigger value="evidence">Evidence</TabsTrigger>
                  </TabsList>
                  <TabsContent
                    value="score"
                    className="pt-3 text-sm text-text-muted"
                  >
                    The verdict. Is the money right?
                  </TabsContent>
                  <TabsContent
                    value="queue"
                    className="pt-3 text-sm text-text-muted"
                  >
                    The work. A ranked list of what needs a human.
                  </TabsContent>
                  <TabsContent
                    value="evidence"
                    className="pt-3 text-sm text-text-muted"
                  >
                    The proof. Records, the identity math, the AI reasoning.
                  </TabsContent>
                </Tabs>
              </Specimen>
              <Specimen label="Evidence drawer">
                <Sheet>
                  <SheetTrigger asChild>
                    <Button variant="secondary">Open drawer</Button>
                  </SheetTrigger>
                  <SheetContent>
                    <SheetHeader>
                      <SheetTitle>TIMING · −₹194.70</SheetTitle>
                      <SheetDescription>
                        Bank credit has no settlement line. Likely a T+2 into
                        September, matching three August orders.
                      </SheetDescription>
                    </SheetHeader>
                  </SheetContent>
                </Sheet>
              </Specimen>
            </div>
          </Section>

          <Section
            id="feedback"
            title="Feedback & motion"
            intro="Toasts for what just happened and what it changed. Skeletons shaped like the content they replace. The only celebratory motion is the auto-tied number counting up when a re-run improves it, earned once per run."
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Specimen label="Toast, action plus consequence">
                <Button
                  variant="secondary"
                  onClick={() =>
                    toast("Rule r_timing_sept drafted", {
                      description:
                        "Re-run to apply. Projected auto-tied 93.8% to 94.6%.",
                    })
                  }
                >
                  Resolve &amp; draft rule
                </Button>
              </Specimen>
              <Specimen label="The one earned animation">
                <div>
                  <div className="text-xl font-semibold text-positive">
                    <CountUp to={94.6} from={93.8} duration={0.5} separator="," />%
                  </div>
                  <div className="mt-0.5 text-xs text-text-muted">
                    auto-tied, after the rule re-ran
                  </div>
                </div>
              </Specimen>
            </div>
          </Section>
        </div>
      </div>
    </AppShell>
  );
}
