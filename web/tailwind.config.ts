import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/* docs/05 §3 — the visual system. Tokens live as RGB-channel CSS vars in
   globals.css; here they become Tailwind colours with full `/opacity` support.
   Light/dark parity is handled by the vars, so `dark:` is rarely needed. */
const rgb = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Arbiter tokens
        bg: rgb("--bg"),
        surface: {
          DEFAULT: rgb("--surface"),
          2: rgb("--surface-2"),
        },
        border: rgb("--border"),
        text: {
          DEFAULT: rgb("--text"),
          muted: rgb("--text-muted"),
        },
        accent: {
          DEFAULT: rgb("--accent"),
          ink: rgb("--accent-ink"),
        },
        positive: rgb("--positive"),
        attention: rgb("--attention"),
        critical: rgb("--critical"),

        // shadcn/ui semantic aliases (so registry components render on-brand)
        background: rgb("--bg"),
        foreground: rgb("--text"),
        card: { DEFAULT: rgb("--surface"), foreground: rgb("--text") },
        popover: { DEFAULT: rgb("--surface"), foreground: rgb("--text") },
        primary: { DEFAULT: rgb("--accent"), foreground: rgb("--accent-ink") },
        secondary: { DEFAULT: rgb("--surface-2"), foreground: rgb("--text") },
        muted: { DEFAULT: rgb("--surface-2"), foreground: rgb("--text-muted") },
        destructive: { DEFAULT: rgb("--critical"), foreground: "rgb(255 255 255 / <alpha-value>)" },
        input: rgb("--border"),
        ring: rgb("--accent"),
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        // docs/05 §3.2 — the scale is 12 / 13 / 14 / 16 / 20 / 28, nothing else
        "2xs": ["0.75rem", { lineHeight: "1rem" }], // 12
        xs: ["0.8125rem", { lineHeight: "1.125rem" }], // 13
        sm: ["0.875rem", { lineHeight: "1.375rem" }], // 14 (base)
        base: ["1rem", { lineHeight: "1.5rem" }], // 16
        lg: ["1.25rem", { lineHeight: "1.75rem" }], // 20
        xl: ["1.75rem", { lineHeight: "2rem", letterSpacing: "-0.02em" }], // 28 display
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow)",
        none: "none",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.12s ease-out",
        "accordion-up": "accordion-up 0.12s ease-out",
      },
      transitionDuration: {
        DEFAULT: "120ms", // docs/05 §3.4 — one duration, 120ms
      },
    },
  },
  plugins: [animate],
};
export default config;
