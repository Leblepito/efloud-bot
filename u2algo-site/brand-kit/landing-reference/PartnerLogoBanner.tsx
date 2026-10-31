"use client";

import { ScrollReveal } from "@/components/shared/ScrollReveal";

interface ExchangeLogo {
  name: string;
  letter: string;
  color: string;
}

const EXCHANGES: ExchangeLogo[] = [
  { name: "Binance", letter: "B", color: "#F0B90B" },
  { name: "OKX", letter: "O", color: "#FFFFFF" },
  { name: "Bybit", letter: "BY", color: "#F7A600" },
  { name: "KuCoin", letter: "K", color: "#23AF91" },
  { name: "Gate.io", letter: "G", color: "#2354E6" },
  { name: "Bitget", letter: "BG", color: "#00F0FF" },
  { name: "MEXC", letter: "MX", color: "#2ECC71" },
  { name: "HTX", letter: "H", color: "#2B6DEE" },
];

function LogoCard({ exchange }: { exchange: ExchangeLogo }) {
  return (
    <div className="group flex-shrink-0 w-[140px] h-[60px] rounded-xl border border-white/[0.06] bg-white/[0.02] flex items-center justify-center gap-2 mx-2 transition-all duration-300 hover:border-white/[0.15] hover:bg-white/[0.04] cursor-default">
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-black transition-all duration-300 grayscale group-hover:grayscale-0"
        style={{ backgroundColor: `${exchange.color}15`, color: exchange.color, border: `1px solid ${exchange.color}25` }}
      >
        {exchange.letter}
      </div>
      <span className="text-xs font-semibold text-slate-500 group-hover:text-white transition-colors duration-300">
        {exchange.name}
      </span>
    </div>
  );
}

export function PartnerLogoBanner() {
  const doubled = [...EXCHANGES, ...EXCHANGES];

  return (
    <section className="py-16 overflow-hidden">
      <ScrollReveal>
        <div className="text-center mb-8">
          <p className="text-[11px] text-slate-500 uppercase tracking-[0.2em]">Integrated With Top Exchanges</p>
        </div>
      </ScrollReveal>

      <div className="relative">
        {/* Fade edges */}
        <div className="absolute left-0 top-0 bottom-0 w-24 z-10 pointer-events-none" style={{ background: "linear-gradient(90deg, #050510, transparent)" }} />
        <div className="absolute right-0 top-0 bottom-0 w-24 z-10 pointer-events-none" style={{ background: "linear-gradient(270deg, #050510, transparent)" }} />

        {/* Marquee */}
        <div className="flex animate-marquee">
          {doubled.map((ex, i) => (
            <LogoCard key={`${ex.name}-${i}`} exchange={ex} />
          ))}
        </div>

        {/* CSS animation */}
        <style jsx>{`
          @keyframes marquee {
            0% { transform: translateX(0); }
            100% { transform: translateX(-50%); }
          }
          .animate-marquee {
            animation: marquee 30s linear infinite;
          }
          .animate-marquee:hover {
            animation-play-state: paused;
          }
        `}</style>
      </div>
    </section>
  );
}
