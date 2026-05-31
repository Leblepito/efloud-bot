"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { Calculator, TrendingUp, ShieldAlert, BarChart3, ArrowRight } from "lucide-react";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

const BOT_TYPES = [
  { value: "dca", label: "DCA Bot", monthlyReturn: 4.2, maxDD: 8.5, sharpe: 1.85 },
  { value: "grid", label: "Grid Bot", monthlyReturn: 3.8, maxDD: 12.3, sharpe: 1.52 },
  { value: "signal", label: "AI Signal Bot", monthlyReturn: 5.6, maxDD: 15.1, sharpe: 2.12 },
];

const PERIODS = [
  { value: 3, label: "3 months" },
  { value: 6, label: "6 months" },
  { value: 12, label: "12 months" },
];

function AnimatedNumber({ value, prefix = "", suffix = "" }: { value: number; prefix?: string; suffix?: string }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef<number | null>(null);

  useEffect(() => {
    const start = display;
    const diff = value - start;
    const duration = 600;
    const startTime = performance.now();

    function tick(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(start + diff * eased);
      if (progress < 1) ref.current = requestAnimationFrame(tick);
    }

    ref.current = requestAnimationFrame(tick);
    return () => { if (ref.current) cancelAnimationFrame(ref.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <span className="tabular-nums">
      {prefix}{display >= 1000 ? `${(display / 1000).toFixed(1)}k` : display.toFixed(display < 100 ? 1 : 0)}{suffix}
    </span>
  );
}

export function ROICalculator() {
  const [capital, setCapital] = useState(10000);
  const [botType, setBotType] = useState(BOT_TYPES[0]);
  const [months, setMonths] = useState(6);

  const compoundReturn = capital * Math.pow(1 + botType.monthlyReturn / 100, months) - capital;
  const totalValue = capital + compoundReturn;
  const returnPct = (compoundReturn / capital) * 100;

  return (
    <section className="py-24 px-4">
      <div className="max-w-4xl mx-auto">
        <ScrollReveal>
          <div className="text-center mb-10">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.04] text-white/40 border border-white/[0.06] mb-4 uppercase tracking-[0.2em]">
              ROI Calculator
            </div>
            <h2 className="text-3xl sm:text-4xl font-display font-bold text-white/90 tracking-tight">
              Estimate Your <span className="text-[#00f0ff]">Returns</span>
            </h2>
            <p className="mt-3 text-sm text-slate-400 max-w-lg mx-auto">
              Based on historical performance. Past results do not guarantee future returns.
            </p>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="rounded-2xl border border-[#00f0ff]/15 bg-gradient-to-b from-[#00f0ff]/[0.04] via-transparent to-transparent p-6 sm:p-8">
            {/* Inputs */}
            <div className="grid sm:grid-cols-3 gap-5 mb-8">
              {/* Capital */}
              <div>
                <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-2 block">Starting Capital</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm">$</span>
                  <input
                    type="number"
                    aria-label="Starting capital in USD"
                    value={capital}
                    onChange={(e) => setCapital(Math.max(100, Number(e.target.value) || 0))}
                    min={100}
                    max={1000000}
                    className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] pl-7 pr-4 py-3 text-white text-base sm:text-sm min-h-[44px] tabular-nums focus:outline-none focus:border-[#00f0ff]/30 focus:ring-1 focus:ring-[#00f0ff]/20"
                  />
                </div>
              </div>

              {/* Bot type */}
              <div>
                <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-2 block">Bot Strategy</label>
                <select
                  aria-label="Bot strategy type"
                  value={botType.value}
                  onChange={(e) => setBotType(BOT_TYPES.find(b => b.value === e.target.value) || BOT_TYPES[0])}
                  className="w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 text-white text-sm focus:outline-none focus:border-[#00f0ff]/30 appearance-none cursor-pointer"
                >
                  {BOT_TYPES.map(b => (
                    <option key={b.value} value={b.value} className="bg-slate-900">{b.label}</option>
                  ))}
                </select>
              </div>

              {/* Period */}
              <div>
                <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold mb-2 block">Time Period</label>
                <div className="flex gap-2">
                  {PERIODS.map(p => (
                    <button
                      key={p.value}
                      onClick={() => setMonths(p.value)}
                      className={`flex-1 py-3 rounded-xl text-xs font-semibold transition-all ${
                        months === p.value
                          ? "bg-[#00f0ff]/15 border border-[#00f0ff]/30 text-[#00f0ff]"
                          : "border border-white/[0.06] bg-white/[0.02] text-slate-400 hover:text-white"
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Results */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 text-center">
                <TrendingUp className="w-5 h-5 text-[#00ff88]/60 mx-auto mb-2" />
                <div className="text-2xl font-bold text-[#00ff88]">
                  <AnimatedNumber value={compoundReturn} prefix="+$" />
                </div>
                <div className="text-[10px] text-slate-500 mt-1">Estimated Profit</div>
              </div>

              <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 text-center">
                <Calculator className="w-5 h-5 text-[#00f0ff]/60 mx-auto mb-2" />
                <div className="text-2xl font-bold text-white">
                  <AnimatedNumber value={totalValue} prefix="$" />
                </div>
                <div className="text-[10px] text-slate-500 mt-1">Total Value</div>
              </div>

              <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 text-center">
                <ShieldAlert className="w-5 h-5 text-[#ffaa00]/60 mx-auto mb-2" />
                <div className="text-2xl font-bold text-[#ffaa00]">
                  <AnimatedNumber value={botType.maxDD} suffix="%" />
                </div>
                <div className="text-[10px] text-slate-500 mt-1">Max Drawdown</div>
              </div>

              <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 text-center">
                <BarChart3 className="w-5 h-5 text-[#a855f7]/60 mx-auto mb-2" />
                <div className="text-2xl font-bold text-[#a855f7]">
                  <AnimatedNumber value={botType.sharpe} />
                </div>
                <div className="text-[10px] text-slate-500 mt-1">Sharpe Ratio</div>
              </div>
            </div>

            {/* Return percentage bar */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] text-slate-500">Return on Investment</span>
                <span className="text-sm font-bold text-[#00ff88] tabular-nums">+{returnPct.toFixed(1)}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-white/[0.06] overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-[#00f0ff] to-[#00ff88] transition-all duration-700" style={{ width: `${Math.min(100, returnPct)}%` }} />
              </div>
            </div>

            {/* CTA */}
            <div className="text-center">
              <Link href="/auth">
                <button className="group px-8 py-3.5 bg-gradient-to-r from-[#00f0ff] to-[#0080ff] hover:from-[#00f0ff]/90 hover:to-[#0080ff]/90 text-white font-bold rounded-xl transition-all text-sm hover:scale-[1.02] shadow-lg shadow-[#00f0ff]/15 flex items-center gap-2 mx-auto">
                  Start Free Trial
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                </button>
              </Link>
              <p className="text-[10px] text-slate-400 mt-3">No credit card required. Cancel anytime.</p>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
