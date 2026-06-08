/**
 * @efloud/tokens/tailwind — shared Tailwind preset.
 *
 * Derived from the canonical tokens in `./index`. Consumed via `presets: [...]`
 * in each app's `tailwind.config.ts`.
 *
 * IMPORTANT (PR #1 is a no-visual-change refactor): this preset only ADDS new,
 * namespaced theme keys (`brand` colors, `font-display`, `shadow-glow`, etc.) that
 * the dashboard does not currently use. It deliberately does NOT override Tailwind's
 * default scales (borderRadius / spacing / fontSize) — doing so would silently
 * restyle every `rounded-xl` / `text-sm` / `p-4` already in the dashboard. Tailwind's
 * JIT only emits classes that are referenced, so adding these keys produces zero new
 * CSS until a component opts in (PR #2 onward).
 */
import type { Config } from "tailwindcss";
import { colors, typography, effects } from "./index";

const preset: Partial<Config> = {
  theme: {
    extend: {
      colors: {
        // Namespaced u2algo brand palette — new, non-colliding.
        brand: {
          cyan: colors.cyan,
          green: colors.green,
          red: colors.red,
          yellow: colors.yellow,
          blue: colors.blue,
          indigo: colors.indigo,
          purple: colors.purple,
          bullish: colors.bullish,
          bearish: colors.bearish,
          neutral: colors.neutral,
        },
      },
      fontFamily: {
        // `sans`/`mono` are owned by each app's own config; only `display` is new here.
        display: [typography.fontFamily.display],
      },
      boxShadow: {
        glow: effects.shadowGlow,
        "cta-glow": effects.ctaGlow,
      },
      backdropBlur: {
        glass: effects.glassBlur,
      },
    },
  },
};

export default preset;
