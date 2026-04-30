import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brutalist trader palette — pure black base
        bg: {
          DEFAULT: "#000000",
          elevated: "#0A0A0A",
          surface: "#141414",
        },
        border: {
          DEFAULT: "#1F1F1F",
          strong: "#2A2A2A",
          accent: "#00FF88",
        },
        text: {
          primary: "#FAFAFA",
          secondary: "#888888",
          muted: "#444444",
          dim: "#2A2A2A",
        },
        accent: {
          green: "#00FF88",   // alive, profit, OPEN
          amber: "#FFA500",   // warning, TRIPPED
          red: "#FF3030",     // critical, SHORT, loss, HALTED
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
