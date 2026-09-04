# Arbiter cockpit — design system

Rebuilt foundation (Pass 1). Live reference: **`/design`** (`pnpm dev` → http://localhost:3000/design).

## Stack

| Layer | Choice | Why |
|---|---|---|
| Primitives | **shadcn/ui** (Radix, `style: new-york`) in `src/components/ui/` | Legible, accessible, owned source — adapted to Arbiter tokens |
| Motion / effects | **React Bits** via its shadcn registry, in `src/components/reactbits/` | The few earned animated moments (count-up, live feed) |
| Icons | `lucide-react` |
| Tokens | RGB-channel CSS vars in `globals.css`, surfaced as Tailwind colours | one source of truth, light/dark parity, `/opacity` works |

### Adding components

```bash
# shadcn primitive (then adapt tokens: bg-background→bg-surface, text-muted-foreground→text-text-muted, etc.)
npx shadcn@latest add <name>

# React Bits (namespaced registry in components.json)
npx shadcn@latest add @reactbits/<Name>-TS-TW
```

Both the `shadcn` MCP server (`web/.mcp.json`) and the `@reactbits` registry are wired — restart Claude Code to pick up the MCP.

## Tokens (docs/05 §3.1)

`--bg --surface --surface-2 --border --text --text-muted --accent --accent-ink --positive --attention --critical`
plus `--radius` (0.5rem), `--shadow-sm`, `--shadow`.

Tailwind: `bg-bg bg-surface bg-surface-2 border-border text-text text-text-muted text-accent text-positive text-attention text-critical`.
shadcn semantic aliases (`primary`, `secondary`, `muted`, `card`, `popover`, `destructive`, `input`, `ring`, `background`, `foreground`) all map onto these.

## Type scale (docs/05 §3.2) — nothing off this scale

`text-xl` 28 (display, scorecard headline only) · `text-lg` 20 · `text-base` 16 · `text-sm` 14 (base) · `text-xs` 13 (grid) · `text-2xs` 12 (labels/chips). `font-sans` = Inter, `font-mono` = JetBrains Mono (loaded via `next/font`).

## Motion (docs/05 §3.4)

One duration: **120ms**. No springs, no shimmer. The single earned animation is the count-up when auto-tied % rises (`reactbits/CountUp`). `prefers-reduced-motion` kills all of it.

## Kit so far

`ui/`: button · badge (status chips, border always) · card · input · select (native, styled) · label · checkbox · separator · sheet (evidence drawer) · tooltip · dropdown-menu · tabs · scroll-area · skeleton · sonner (toasts) · kbd
`reactbits/`: CountUp
`AppShell` (sticky header: brand · run context · actions · ⌘K · theme) · `ThemeToggle` (visible, cycles system/light/dark) · `CommandPalette`

## Not done yet (next passes, screen by screen)

Landing/runs list · NewRun form · LiveRun · Cockpit (scorecard viz, queue, evidence drawer). Old screens still compile on the new tokens but keep their old layout. `framer-motion` (old) and `motion` (React Bits) both installed — migrate to `motion` as screens are rebuilt.
