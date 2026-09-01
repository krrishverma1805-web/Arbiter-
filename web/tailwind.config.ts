import type { Config } from "tailwindcss";

// The design tokens from docs/05 §3.1, wired as CSS variables so light/dark parity
// is defined once on :root and overridden under [data-theme] / prefers-color-scheme.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        border: "var(--border)",
        text: "var(--text)",
        muted: "var(--text-muted)",
        accent: "var(--accent)",
        positive: "var(--positive)",
        attention: "var(--attention)",
        critical: "var(--critical)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
