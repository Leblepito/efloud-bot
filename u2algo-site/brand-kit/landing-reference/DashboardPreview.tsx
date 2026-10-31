"use client";

import { ScrollReveal } from "@/components/shared/ScrollReveal";
import { TrendingUp, TrendingDown, Activity, Crosshair } from "lucide-react";
import { CandlestickChart } from "./preview/CandlestickChart";
import { PositionsTable } from "./preview/PositionsTable";
import { AISignalBadge, ScanLine } from "./preview/SignalOverlay";
import { FloatingParticles } from "./preview/FloatingParticles";
import { OrderPanel } from "./preview/OrderPanel";
import { INDICATORS, TIMEFRAMES, ACTIVE_TIMEFRAME } from "./preview/mock-data";

const MINI_STATS = [
  { label: "Win Rate", value: "73.2%", color: "text-[#00ff88]", icon: TrendingUp },
  { label: "Profit Factor", value: "2.41", color: "text-[#00f0ff]", icon: Activity },
  { label: "Avg. RR", value: "1:2.8", color: "text-[#ffaa00]", icon: Crosshair },
  { label: "Max DD", value: "-4.2%", color: "text-[#ff3366]", icon: TrendingDown },
] as const;

export function DashboardPreview() {
  return (
    <section className="py-24 px-4 overflow-hidden">
      <div className="mx-auto max-w-6xl">
        {/* Section header */}
        <ScrollReveal>
          <div className="text-center mb-14">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.04] text-white/40 border border-white/[0.06] mb-4 uppercase tracking-[0.2em]">
              <Activity className="w-3 h-3" />
              Live Dashboard
            </div>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-display font-bold text-white/90 tracking-tight">
              Professional Trading Dashboard
            </h2>
            <p className="text-slate-400 mt-3 text-sm sm:text-base max-w-2xl mx-auto leading-relaxed">
              AI-powered analysis, real-time signals, and institutional-grade
              execution — all in one interface built for serious traders.
            </p>
          </div>
        </ScrollReveal>

        {/* Dashboard frame */}
        <ScrollReveal delay={150}>
          <div className="relative group">
            <div className="absolute -inset-[1px] rounded-2xl bg-gradient-to-b from-[#00f0ff]/20 via-[#00f0ff]/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700 blur-sm" />
            <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-[#00f0ff]/10 via-transparent to-transparent" />
            <div className="absolute -bottom-8 left-[10%] right-[10%] h-16 bg-[#00f0ff]/[0.04] blur-2xl rounded-full" />

            <div
              className="relative rounded-2xl border border-white/[0.08] overflow-hidden"
              style={{
                background: "linear-gradient(180deg, rgba(15,23,42,0.95) 0%, rgba(2,6,23,0.98) 100%)",
                transform: "perspective(2000px) rotateX(2deg)",
                transformOrigin: "center bottom",
              }}
            >
              <FloatingParticles />
              <ScanLine />

              {/* Browser chrome */}
              <div className="relative z-10 flex items-center gap-3 px-5 py-3 border-b border-white/[0.06] bg-white/[0.02]">
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
                </div>
                <div className="flex-1 flex justify-center">
                  <div className="flex items-center gap-2 px-4 py-1 rounded-lg bg-white/[0.03] border border-white/[0.05] max-w-xs w-full">
                    <div className="w-2.5 h-2.5 rounded-full bg-[#00ff88]/40" />
                    <span className="text-[10px] text-white/25 font-mono">app.u2algo.com/dashboard</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-[#00ff88] animate-pulse" />
                  <span className="text-[9px] text-white/20 font-mono">LIVE</span>
                </div>
              </div>

              {/* Dashboard content */}
              <div className="relative z-10 p-4 sm:p-5">
                <AISignalBadge />

                <div className="flex flex-col lg:flex-row gap-4">
                  {/* Chart area */}
                  <div className="lg:w-[62%] flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center">
                            <span className="text-[7px] font-black text-white">B</span>
                          </div>
                          <span className="text-sm font-bold text-white tracking-tight">BTCUSDT</span>
                        </div>
                        <span className="text-sm font-mono font-bold text-[#00ff88]">$67,432.18</span>
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-[#00ff88]/10 text-[#00ff88]">
                          <TrendingUp className="w-2.5 h-2.5 inline mr-0.5 -mt-px" />
                          +2.34%
                        </span>
                      </div>
                      <div className="hidden sm:flex items-center gap-2">
                        {TIMEFRAMES.map((tf) => (
                          <button
                            key={tf}
                            className={`px-2 py-0.5 rounded text-[9px] font-mono ${
                              tf === ACTIVE_TIMEFRAME
                                ? "bg-[#00f0ff]/10 text-[#00f0ff] font-bold"
                                : "text-white/20 hover:text-white/40"
                            } cursor-default`}
                          >
                            {tf}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-xl bg-white/[0.02] border border-white/[0.05] p-3 overflow-hidden">
                      <CandlestickChart />
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {INDICATORS.map((ind) => (
                        <div key={ind.label} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-white/[0.02] border border-white/[0.04]">
                          <span className="text-[8px] text-white/25 uppercase tracking-wider font-semibold">{ind.label}</span>
                          <span className={`text-[10px] font-mono font-medium ${ind.color}`}>{ind.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Order panel */}
                  <div className="lg:w-[38%] flex flex-col gap-4">
                    <div className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-bold text-white/70 tracking-wide">Place Order</span>
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-[#00f0ff]/10 text-[#00f0ff] font-mono">Spot</span>
                      </div>
                      <OrderPanel />
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      {MINI_STATS.map((stat) => (
                        <div key={stat.label} className="rounded-xl bg-white/[0.02] border border-white/[0.04] p-3 flex flex-col gap-1">
                          <div className="flex items-center gap-1.5">
                            <stat.icon className="w-2.5 h-2.5 text-white/15" />
                            <span className="text-[8px] text-white/20 uppercase tracking-wider font-semibold">{stat.label}</span>
                          </div>
                          <span className={`text-sm font-mono font-bold ${stat.color}`}>{stat.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Positions table */}
                <div className="mt-4 rounded-xl bg-white/[0.03] border border-white/[0.06] p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white/70 tracking-wide">Open Positions</span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-white/[0.06] text-white/30 font-mono">3</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-[#00ff88]" />
                      <span className="text-[9px] text-white/25 font-mono">Synced</span>
                    </div>
                  </div>
                  <PositionsTable />
                </div>
              </div>
            </div>
          </div>
        </ScrollReveal>

        {/* Bottom CTA */}
        <ScrollReveal delay={300}>
          <div className="text-center mt-10">
            <p className="text-slate-500 text-xs mb-4">No credit card required. Start with free tier.</p>
            <button className="px-8 py-3 rounded-xl text-sm font-bold text-white bg-gradient-to-r from-[#00f0ff] to-[#0080ff] shadow-lg shadow-[#00f0ff]/10 hover:shadow-[#00f0ff]/20 hover:brightness-110 transition-all cursor-default">
              Try the Dashboard Free
            </button>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
