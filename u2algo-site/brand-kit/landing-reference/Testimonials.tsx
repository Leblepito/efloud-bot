"use client";
import { useRef } from "react";
import { useI18n } from "@/lib/i18n/context";
import { ScrollReveal } from "@/components/shared/ScrollReveal";
import { ChevronLeft, ChevronRight, Quote } from "lucide-react";

const testimonials = [
  {
    quote: "The AI consensus signals changed how I trade. 5 agents analyzing together > any single indicator.",
    name: "Marcus T.",
    role: "Day Trader",
    location: "London",
    result: "+32%",
    resultLabel: "portfolio in 3 months",
    initials: "MT",
    gradient: "from-[#00f0ff] to-blue-500",
  },
  {
    quote: "Backtest sonuclari gercekci. Slippage ve komisyon dahil, gercek trading'e en yakin simulasyon.",
    name: "Ayse K.",
    role: "Algo Trader",
    location: "Istanbul",
    result: "200+",
    resultLabel: "strategies backtested",
    initials: "AK",
    gradient: "from-emerald-500 to-teal-500",
  },
  {
    quote: "\u0E40\u0E04\u0E23\u0E37\u0E48\u0E2D\u0E07\u0E21\u0E37\u0E2D\u0E01\u0E32\u0E23\u0E28\u0E36\u0E01\u0E29\u0E32\u0E0A\u0E48\u0E27\u0E22\u0E43\u0E2B\u0E49\u0E09\u0E31\u0E19\u0E40\u0E02\u0E49\u0E32\u0E43\u0E08 Elliott Wave \u0E44\u0E14\u0E49\u0E14\u0E35\u0E02\u0E36\u0E49\u0E19\u0E21\u0E32\u0E01",
    name: "Somchai P.",
    role: "Swing Trader",
    location: "Bangkok",
    result: "Pro",
    resultLabel: "Academy graduate",
    initials: "SP",
    gradient: "from-purple-500 to-pink-500",
  },
  {
    quote: "Real-time signal alerts with confluence scoring saved me from multiple bad entries. The R:R filtering alone is worth the subscription.",
    name: "David L.",
    role: "Futures Trader",
    location: "Singapore",
    result: "87%",
    resultLabel: "win rate on filtered signals",
    initials: "DL",
    gradient: "from-amber-500 to-orange-500",
  },
];

export function Testimonials() {
  const { t } = useI18n();
  const scrollRef = useRef<HTMLDivElement>(null);

  const scroll = (direction: "left" | "right") => {
    if (!scrollRef.current) return;
    const scrollAmount = 360;
    scrollRef.current.scrollBy({
      left: direction === "left" ? -scrollAmount : scrollAmount,
      behavior: "smooth",
    });
  };

  return (
    <section className="py-24 px-4 overflow-hidden">
      <div className="mx-auto max-w-6xl">
        <ScrollReveal>
          <div className="flex items-end justify-between mb-12">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.04] text-white/40 border border-white/[0.06] mb-4 uppercase tracking-[0.2em]">
                Testimonials
              </div>
              <h2 className="text-3xl sm:text-4xl font-display font-bold text-white/90 tracking-tight">
                {t("testimonials_title")}
              </h2>
              <p className="text-slate-400 mt-2 text-sm max-w-lg">
                {t("testimonials_subtitle")}
              </p>
            </div>
            <div className="hidden sm:flex items-center gap-2">
              <button
                onClick={() => scroll("left")}
                className="w-10 h-10 rounded-xl border border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.12] transition-all flex items-center justify-center text-white/40 hover:text-white/70"
                aria-label="Scroll left"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => scroll("right")}
                className="w-10 h-10 rounded-xl border border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.12] transition-all flex items-center justify-center text-white/40 hover:text-white/70"
                aria-label="Scroll right"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </ScrollReveal>

        <div
          ref={scrollRef}
          className="flex gap-5 overflow-x-auto pb-4 snap-x snap-mandatory scrollbar-hide -mx-4 px-4"
        >
          {testimonials.map((item, i) => (
            <ScrollReveal key={item.name} delay={i * 80}>
              <div className="min-w-[320px] max-w-[360px] snap-center bg-white/[0.02] border border-white/[0.06] rounded-xl p-6 flex flex-col hover:border-[#00f0ff]/15 transition-all duration-300 group">
                {/* Quote icon */}
                <Quote className="w-8 h-8 text-[#00f0ff]/20 mb-4 group-hover:text-[#00f0ff]/30 transition-colors" strokeWidth={1} />

                {/* Quote text */}
                <p className="text-white/50 text-sm leading-relaxed flex-1 mb-6">
                  {item.quote}
                </p>

                {/* Author row */}
                <div className="flex items-center gap-3 mb-4">
                  <div
                    className={`w-10 h-10 rounded-full bg-gradient-to-br ${item.gradient} flex items-center justify-center text-white text-xs font-bold shadow-lg`}
                  >
                    {item.initials}
                  </div>
                  <div>
                    <p className="text-white/80 text-sm font-medium">{item.name}</p>
                    <p className="text-white/25 text-xs">
                      {item.role} &middot; {item.location}
                    </p>
                  </div>
                </div>

                {/* PnL badge */}
                <div className="pt-4 border-t border-white/[0.06] flex items-center gap-2">
                  <span className="text-[#00ff88] font-mono-nums text-lg font-bold">{item.result}</span>
                  <span className="text-white/25 text-xs">{item.resultLabel}</span>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
