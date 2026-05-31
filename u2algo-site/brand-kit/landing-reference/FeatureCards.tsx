"use client";

import Link from "next/link";
import {
  Bot,
  BarChart3,
  Radio,
  Activity,
  Layers,
  ArrowRight,
} from "lucide-react";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

/* ─── Feature definitions ───────────────────────────── */
interface Feature {
  icon: typeof Bot;
  title: string;
  description: string;
  href: string;
  accent: string;
  glowColor: string;
  iconBg: string;
}

const FEATURES: Feature[] = [
  {
    icon: Bot,
    title: "Bot Trading",
    description:
      "Deploy AI bots that trade 24/7. EW+SMC analysis, hedge mode, risk management.",
    href: "/bot",
    accent: "text-[#00f0ff]",
    glowColor: "rgba(0, 240, 255, 0.35)",
    iconBg: "bg-[#00f0ff]/10 border-[#00f0ff]/20",
  },
  {
    icon: BarChart3,
    title: "Backtest Engine",
    description:
      "Test strategies against historical data. Walk-forward validation, realistic slippage.",
    href: "/backtest",
    accent: "text-[#0080ff]",
    glowColor: "rgba(0, 128, 255, 0.35)",
    iconBg: "bg-[#0080ff]/10 border-[#0080ff]/20",
  },
  {
    icon: Radio,
    title: "AI Signals",
    description:
      "Real-time signals from multi-agent AI swarm. Consensus-based, confidence scored.",
    href: "/signals",
    accent: "text-[#00ff88]",
    glowColor: "rgba(0, 255, 136, 0.35)",
    iconBg: "bg-[#00ff88]/10 border-[#00ff88]/20",
  },
  {
    icon: Activity,
    title: "Indicators",
    description:
      "RSI, Bollinger, Elliott Wave, SMC, Fibonacci. Professional chart workbench.",
    href: "/indicators",
    accent: "text-[#ffaa00]",
    glowColor: "rgba(255, 170, 0, 0.35)",
    iconBg: "bg-[#ffaa00]/10 border-[#ffaa00]/20",
  },
  {
    icon: Layers,
    title: "Marketplace",
    description:
      "Share and sell strategies. Community-driven indicator library.",
    href: "/marketplace",
    accent: "text-[#ff3366]",
    glowColor: "rgba(255, 51, 102, 0.35)",
    iconBg: "bg-[#ff3366]/10 border-[#ff3366]/20",
  },
];

/* ─── Individual feature card ───────────────────────── */
function FeatureCard({ feature, delay }: { feature: Feature; delay: number }) {
  const Icon = feature.icon;

  return (
    <ScrollReveal delay={delay}>
      <div className="group relative flex flex-col gap-4 p-6 sm:p-7 rounded-2xl bg-white/[0.03] border border-white/[0.06] hover:border-cyan-500/20 hover:-translate-y-1 transition-all duration-300 h-full">
        {/* Glow effect behind icon on hover */}
        <div
          className="absolute top-6 left-6 w-14 h-14 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-2xl pointer-events-none"
          style={{ background: feature.glowColor }}
          aria-hidden="true"
        />

        {/* Icon circle */}
        <div
          className={`relative flex items-center justify-center w-12 h-12 rounded-xl border ${feature.iconBg} transition-all duration-300 group-hover:scale-110`}
        >
          <Icon
            className={`w-5.5 h-5.5 ${feature.accent}`}
            strokeWidth={1.5}
          />
        </div>

        {/* Title */}
        <h3 className="text-white font-display font-semibold text-lg leading-tight">
          {feature.title}
        </h3>

        {/* Description */}
        <p className="text-slate-400 text-sm leading-relaxed flex-1">
          {feature.description}
        </p>

        {/* Learn more link */}
        <Link
          href={feature.href}
          className={`inline-flex items-center gap-1.5 text-sm font-medium ${feature.accent} opacity-80 group-hover:opacity-100 transition-all duration-300`}
        >
          Learn more
          <ArrowRight className="w-3.5 h-3.5 transition-transform duration-300 group-hover:translate-x-1" />
        </Link>
      </div>
    </ScrollReveal>
  );
}

/* ─── Main section ──────────────────────────────────── */
export function FeatureCards() {
  return (
    <section className="relative py-20 sm:py-28 px-4 overflow-hidden">
      {/* Subtle top separator */}
      <div
        className="absolute top-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(0,240,255,0.12) 30%, rgba(0,128,255,0.12) 70%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      {/* Background radial glow */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[700px] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,240,255,0.04) 0%, transparent 65%)",
        }}
        aria-hidden="true"
      />

      <div className="relative mx-auto max-w-6xl">
        {/* Section header */}
        <ScrollReveal>
          <div className="text-center mb-14 sm:mb-18">
            <h2 className="font-display font-bold text-3xl sm:text-4xl md:text-5xl text-white leading-tight">
              Everything You Need to{" "}
              <span
                className="bg-clip-text text-transparent"
                style={{
                  backgroundImage:
                    "linear-gradient(135deg, #00f0ff 0%, #0080ff 100%)",
                }}
              >
                Trade Smarter
              </span>
            </h2>
            <p className="mt-4 sm:mt-5 text-slate-400 text-base sm:text-lg max-w-2xl mx-auto leading-relaxed">
              From AI-powered bots to interactive education, u2Algo gives you
              every tool to master the crypto markets.
            </p>
          </div>
        </ScrollReveal>

        {/* Feature grid: 1 col mobile, 2 col tablet, 3 col desktop */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
          {FEATURES.map((feature, i) => (
            <FeatureCard
              key={feature.title}
              feature={feature}
              delay={i * 100}
            />
          ))}
        </div>
      </div>

      {/* Subtle bottom separator */}
      <div
        className="absolute bottom-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(0,240,255,0.08) 30%, rgba(0,128,255,0.08) 70%, transparent 100%)",
        }}
        aria-hidden="true"
      />
    </section>
  );
}
