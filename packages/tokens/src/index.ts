/**
 * @efloud/tokens — EFloud Design Token System (single source of truth)
 *
 * Promoted from `u2algo-site/brand-kit/css/design-tokens.ts` (PR #1). These JS-land
 * constants stay in sync with `globals.css :root` custom properties. They are the
 * canonical token source for:
 *   - the operator dashboard (`frontend/`)            — wired now (PR #1/#2)
 *   - the marketing site (`u2algo-site/web`)          — wired in PR #6
 *   - the mobile app (`mobile/`, NativeWind preset)   — wired in PR #19
 *
 * Tailwind consumers should import the curated, collision-safe preset from
 * `@efloud/tokens/tailwind`. These raw constants are for JS-land (inline styles,
 * canvas/chart theming, RN StyleSheet) where Tailwind classes are unavailable.
 */

/* ═══════════════════════════════════════════════════════
   Brand Colors
   ═══════════════════════════════════════════════════════ */
export const colors = {
  /* Core brand */
  cyan: "#00f0ff",
  green: "#00ff88",
  red: "#ff3366",
  yellow: "#ffaa00",
  blue: "#0080ff",
  indigo: "#6366f1",
  purple: "#a855f7",

  /* Gradient pairs */
  gradientPrimary: { from: "#00f0ff", to: "#0080ff" },
  gradientAccent: { from: "#a855f7", to: "#6366f1" },
  gradientSuccess: { from: "#00ff88", to: "#00f0ff" },

  /* Surfaces */
  surfaceBase: "#000000",
  surfaceRaised: "rgba(15, 23, 42, 0.6)",
  surfaceOverlay: "rgba(30, 41, 59, 0.4)",
  surfaceHover: "rgba(30, 41, 59, 0.6)",
  navBg: "rgba(15, 23, 42, 0.5)",

  /* Card system (use in className: bg-white/[0.03]) */
  cardBg: "rgba(255, 255, 255, 0.03)",
  cardBgHover: "rgba(255, 255, 255, 0.05)",
  cardBorder: "rgba(255, 255, 255, 0.06)",
  cardBorderHover: "rgba(255, 255, 255, 0.12)",

  /* Borders */
  borderSubtle: "rgba(255, 255, 255, 0.05)",
  borderDefault: "rgba(255, 255, 255, 0.1)",
  borderHover: "rgba(255, 255, 255, 0.2)",

  /* Text */
  textPrimary: "#f8fafc",
  textSecondary: "#94a3b8",
  textMuted: "#64748b",

  /* Trading status */
  bullish: "#00ff88",
  bearish: "#ff3366",
  neutral: "#64748b",

  /* Landing cinematic palette */
  landing: {
    gradientStart: "#0a0a1a",
    gradientMid: "#0d1b2a",
    gradientEnd: "#1b2838",
    glow: "rgba(0, 240, 255, 0.15)",
    accent: "#00f0ff",
  },

  /* Education warm palette */
  education: {
    surface: "#1a1a2e",
    accent: "#7c3aed",
    warm: "#f59e0b",
    success: "#22c55e",
    fun: "#ec4899",
  },

  /* Trading pro palette */
  trading: {
    surface: "#0a0a0f",
    grid: "rgba(255, 255, 255, 0.02)",
    bullish: "#00ff88",
    bearish: "#ff3366",
    neutral: "#64748b",
  },
} as const;

/* ═══════════════════════════════════════════════════════
   Spacing (multiples of 4px base)
   ═══════════════════════════════════════════════════════ */
export const spacing = {
  xs: "4px",
  sm: "8px",
  md: "16px",
  lg: "24px",
  xl: "32px",
  "2xl": "48px",
  "3xl": "64px",
  section: "80px", // py-20
  hero: "96px",
} as const;

/* ═══════════════════════════════════════════════════════
   Border Radius
   ═══════════════════════════════════════════════════════ */
export const radius = {
  sm: "6px",
  md: "8px",
  lg: "12px",
  xl: "16px", // rounded-xl — default card
  "2xl": "20px",
  full: "9999px",
} as const;

/* ═══════════════════════════════════════════════════════
   Typography
   ═══════════════════════════════════════════════════════ */
export const typography = {
  fontFamily: {
    sans: "var(--font-inter), Inter, system-ui, sans-serif",
    mono: "var(--font-jetbrains), 'JetBrains Mono', monospace",
    display: "var(--font-outfit), 'Outfit', system-ui, sans-serif",
  },
  fontSize: {
    xs: "0.75rem", // 12px
    sm: "0.875rem", // 14px
    base: "1rem", // 16px
    lg: "1.125rem", // 18px
    xl: "1.25rem", // 20px
    "2xl": "1.5rem", // 24px
    "3xl": "1.875rem", // 30px
    "4xl": "2.25rem", // 36px
    "5xl": "3rem", // 48px
    "6xl": "3.75rem", // 60px
    "7xl": "4.5rem", // 72px
  },
} as const;

/* ═══════════════════════════════════════════════════════
   Effects
   ═══════════════════════════════════════════════════════ */
export const effects = {
  glassBlur: "24px",
  shadowGlow: "0 0 20px rgba(0, 240, 255, 0.25)",
  shadowLg: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
  ctaGlow: "0 0 30px rgba(0, 240, 255, 0.3)",
} as const;

/* ═══════════════════════════════════════════════════════
   Terminal palette — the operator dashboard (frontend/)
   "brutalist trader" identity. Distinct from the u2algo
   marketing brand above. Single source for the dashboard's
   Tailwind config AND its chart JS-land colors (recharts /
   lightweight-charts take hex strings, not classes).
   Values are byte-identical to the pre-PR-#2 inline literals,
   so adopting these is a no-visual-change refactor.
   ═══════════════════════════════════════════════════════ */
export const terminal = {
  bg: { base: "#000000", elevated: "#0A0A0A", surface: "#141414" },
  border: { base: "#1F1F1F", strong: "#2A2A2A", accent: "#00FF88" },
  text: { primary: "#FAFAFA", secondary: "#888888", muted: "#444444", dim: "#2A2A2A" },
  accent: { green: "#00FF88", amber: "#FFA500", red: "#FF3030" },
  /* Chart JS-land (recharts / lightweight-charts) */
  chart: {
    bull: "#00FF88",
    bear: "#FF4D4D", // note: candle/marker red — distinct from accent.red (#FF3030)
    neutral: "#FFA500",
    grid: "#1F1F1F",
    axis: "#444444",
    axisText: "#666666",
    cursor: "#2A2A2A",
    tooltipBg: "#0A0A0A",
    tagText: "#04040c",
    oi: "#60a5fa", // open-interest / heuristic accent (blue-400)
  },
  /* lightweight-charts canvas chrome (InteractiveChart) — zinc neutrals */
  chrome: {
    bg: "#09090b",        // canvas background (zinc-950)
    text: "#a1a1aa",      // axis text (zinc-400)
    grid: "#111113",      // grid lines
    crosshair: "#3f3f46", // crosshair (zinc-700)
    label: "#18181b",     // crosshair label bg + price/time scale borders (zinc-900)
    orderLine: "#6366f1", // pending order price line (indigo-500; case-equivalent to #6366F1)
  },
} as const;

/* ═══════════════════════════════════════════════════════
   Tailwind class helpers (common patterns)
   ═══════════════════════════════════════════════════════ */
export const tw = {
  card: "bg-white/[0.03] border border-white/[0.06] rounded-xl",
  cardHover: "hover:bg-white/[0.05] hover:border-white/[0.12] transition-all duration-300",
  gradientBtn: "bg-gradient-to-r from-[#00f0ff] to-[#0080ff] text-white font-semibold rounded-xl",
  ghostBtn: "border border-white/[0.1] bg-white/[0.04] text-slate-200 rounded-xl hover:bg-white/[0.08]",
  sectionPadding: "py-20 px-4",
  maxContainer: "mx-auto max-w-6xl",
  heading: "text-white font-display font-bold tracking-tight",
  muted: "text-slate-400",
  accent: "text-[#00f0ff]",
} as const;
