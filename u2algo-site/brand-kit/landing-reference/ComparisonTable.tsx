"use client";

import { Check, X, Minus } from "lucide-react";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

type CellValue = true | false | "partial" | string;

interface Feature {
  name: string;
  u2algo: CellValue;
  tradingview: CellValue;
  threecommas: CellValue;
  cryptohopper: CellValue;
}

const FEATURES: Feature[] = [
  { name: "AI-Powered Signal Engine", u2algo: true, tradingview: false, threecommas: false, cryptohopper: "partial" },
  { name: "Multi-Agent Consensus", u2algo: true, tradingview: false, threecommas: false, cryptohopper: false },
  { name: "Elliott Wave Auto-Count", u2algo: true, tradingview: "partial", threecommas: false, cryptohopper: false },
  { name: "SMC / Order Block Detection", u2algo: true, tradingview: "partial", threecommas: false, cryptohopper: false },
  { name: "Strategy Backtesting", u2algo: true, tradingview: true, threecommas: true, cryptohopper: true },
  { name: "Live Bot Trading", u2algo: true, tradingview: false, threecommas: true, cryptohopper: true },
  { name: "Hedge Mode Support", u2algo: true, tradingview: false, threecommas: "partial", cryptohopper: false },
  { name: "Education & Games Hub", u2algo: true, tradingview: false, threecommas: false, cryptohopper: false },
  { name: "u2Coin Reward Economy", u2algo: true, tradingview: false, threecommas: false, cryptohopper: false },
  { name: "Prediction Arena", u2algo: true, tradingview: false, threecommas: false, cryptohopper: false },
  { name: "6 Language Support", u2algo: true, tradingview: true, threecommas: "partial", cryptohopper: "partial" },
  { name: "Free Tier Available", u2algo: true, tradingview: true, threecommas: false, cryptohopper: false },
  { name: "Starting Price", u2algo: "$0/mo", tradingview: "$14.95/mo", threecommas: "$29/mo", cryptohopper: "$24.16/mo" },
];

function CellIcon({ value }: { value: CellValue }) {
  if (value === true) return <Check className="w-4 h-4 text-[#00ff88]" />;
  if (value === false) return <X className="w-4 h-4 text-white/15" />;
  if (value === "partial") return <Minus className="w-4 h-4 text-[#ffaa00]" />;
  return <span className="text-xs font-bold text-white tabular-nums">{value}</span>;
}

export function ComparisonTable() {
  const platforms = [
    { key: "u2algo" as const, name: "u2Algo", highlight: true },
    { key: "tradingview" as const, name: "TradingView", highlight: false },
    { key: "threecommas" as const, name: "3Commas", highlight: false },
    { key: "cryptohopper" as const, name: "Cryptohopper", highlight: false },
  ];

  return (
    <section className="py-24 px-4">
      <div className="max-w-5xl mx-auto">
        <ScrollReveal>
          <div className="text-center mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.04] text-white/40 border border-white/[0.06] mb-4 uppercase tracking-[0.2em]">
              Compare
            </div>
            <h2 className="text-3xl sm:text-4xl font-display font-bold text-white/90 tracking-tight">
              Why Traders Choose <span className="text-[#00f0ff]">u2Algo</span>
            </h2>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="rounded-2xl border border-white/5 bg-white/[0.03] overflow-hidden shadow-[0_0_60px_-12px_rgba(6,182,212,0.15)]">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead>
                  <tr className="border-b border-white/[0.06]">
                    <th className="text-left text-[11px] text-slate-500 uppercase tracking-wider font-semibold px-5 py-4 w-[220px]">Feature</th>
                    {platforms.map((p) => (
                      <th key={p.key} className={`text-center px-4 py-4 text-xs font-bold ${p.highlight ? "text-[#00f0ff] bg-[#00f0ff]/[0.04]" : "text-slate-400"}`}>
                        {p.highlight && <div className="w-full h-0.5 bg-gradient-to-r from-transparent via-[#00f0ff] to-transparent mb-3 rounded-full" />}
                        {p.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {FEATURES.map((f, i) => (
                    <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                      <td className="text-[13px] text-slate-300 px-5 py-3">{f.name}</td>
                      {platforms.map((p) => (
                        <td key={p.key} className={`text-center px-4 py-3 ${p.highlight ? "bg-[#00f0ff]/[0.02]" : ""}`}>
                          <div className="flex items-center justify-center">
                            <CellIcon value={f[p.key]} />
                          </div>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={200}>
          <div className="flex items-center justify-center gap-6 mt-6 text-[10px] text-slate-500">
            <span className="flex items-center gap-1.5"><Check className="w-3 h-3 text-[#00ff88]" /> Full support</span>
            <span className="flex items-center gap-1.5"><Minus className="w-3 h-3 text-[#ffaa00]" /> Partial</span>
            <span className="flex items-center gap-1.5"><X className="w-3 h-3 text-white/20" /> Not available</span>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
