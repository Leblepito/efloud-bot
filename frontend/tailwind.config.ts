import type { Config } from "tailwindcss";
import efloudTokens from "@efloud/tokens/tailwind";
import { terminal } from "@efloud/tokens";

const config: Config = {
  // Shared design-token preset (@efloud/tokens, PR #1). Additive/namespaced only —
  // this file's own `theme.extend` below takes precedence on any shared key.
  presets: [efloudTokens as Partial<Config>],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brutalist trader palette — sourced from @efloud/tokens `terminal` (PR #2).
        // Same values as before, now single-sourced; no visual change.
        bg: {
          DEFAULT: terminal.bg.base,
          elevated: terminal.bg.elevated,
          surface: terminal.bg.surface,
        },
        border: {
          DEFAULT: terminal.border.base,
          strong: terminal.border.strong,
          accent: terminal.border.accent,
        },
        text: {
          primary: terminal.text.primary,
          secondary: terminal.text.secondary,
          muted: terminal.text.muted,
          dim: terminal.text.dim,
        },
        accent: {
          green: terminal.accent.green, // alive, profit, OPEN
          amber: terminal.accent.amber, // warning, TRIPPED
          red: terminal.accent.red,     // critical, SHORT, loss, HALTED
        },
        // lightweight-charts canvas chrome — backs InteractiveChart's bg-chrome-bg (PR #4).
        // Only `bg` is used as a class; the other chrome tones are consumed via terminal.chrome.* in TS.
        chrome: {
          bg: terminal.chrome.bg,
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        wider: "0.08em",
        widest: "0.16em",
      },
      keyframes: {
        pulse: {
          "0%": { transform: "scale(1)", opacity: "1" },
          "50%": { opacity: "0.6" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        ringExpand: {
          "0%": { boxShadow: "0 0 0 0 rgba(0,255,136,0.5)" },
          "100%": { boxShadow: "0 0 0 12px rgba(0,255,136,0)" },
        },
      },
      animation: {
        pulse: "pulse 1.6s ease-out infinite",
        slideIn: "slideIn 240ms cubic-bezier(0.2, 0.6, 0.2, 1)",
        ringExpand: "ringExpand 600ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
