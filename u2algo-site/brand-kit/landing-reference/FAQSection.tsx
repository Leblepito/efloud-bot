"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

interface FAQItem {
  question: string;
  answer: string;
}

const FAQ_DATA: FAQItem[] = [
  {
    question: "Is my money safe with u2Algo?",
    answer: "u2Algo never holds your funds. Your assets stay on your exchange (Binance, OKX, etc.). We use API keys with trade-only permissions — no withdrawal access. Keys are encrypted with AES-256 at rest.",
  },
  {
    question: "Which exchanges are supported?",
    answer: "Currently Binance Futures (mainnet and testnet). OKX, Bybit, and KuCoin support is coming in Q2 2026. All exchanges connect via secure API keys.",
  },
  {
    question: "Can I lose money using trading bots?",
    answer: "Yes. Trading involves risk. Our bots include risk management (stop-loss, position sizing, kill switch at 15% drawdown), but losses are possible. Always use amounts you can afford to lose. Start with paper trading on the free plan.",
  },
  {
    question: "Is there a free trial?",
    answer: "Yes! The Free plan includes basic indicators, 3 backtests/day, and paper trading. Pro and Premium plans include a 7-day free trial with full access. No credit card required to start.",
  },
  {
    question: "How does the AI signal engine work?",
    answer: "Five specialized AI agents (Elliott Wave, SMC, Momentum, Risk, Alpha Scout) independently analyze each market. When 3+ agents agree, a consensus signal is generated with entry, stop-loss, and take-profit levels. Higher agreement = higher confidence.",
  },
  {
    question: "What strategies does the bot support?",
    answer: "The bot combines Elliott Wave analysis with Smart Money Concepts (SMC) — including order blocks, fair value gaps, and market structure breaks. You can configure confluence modes, timeframes, risk parameters, and hedge mode for advanced multi-directional trading.",
  },
  {
    question: "Can I cancel my subscription anytime?",
    answer: "Absolutely. No contracts, no lock-in periods. Cancel from your Settings page and you'll keep access until the end of your billing period. Downgrade to Free anytime.",
  },
  {
    question: "Do I need trading experience?",
    answer: "No. The AI handles complex analysis — you just review and approve signals. Start with paper trading on the Free plan, explore the strategy builder, and let the bot handle execution while you learn.",
  },
];

function AccordionItem({ item, isOpen, onToggle }: { item: FAQItem; isOpen: boolean; onToggle: () => void }) {
  return (
    <div className="border-b border-white/[0.06] last:border-b-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between py-4 px-1 text-left group"
      >
        <span className={`text-sm font-semibold transition-colors ${isOpen ? "text-[#00f0ff]" : "text-white/80 group-hover:text-white"}`}>
          {item.question}
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-500 shrink-0 ml-4 transition-transform duration-200 ${isOpen ? "rotate-180 text-[#00f0ff]" : ""}`} />
      </button>
      <div className={`overflow-hidden transition-all duration-300 ${isOpen ? "max-h-48 pb-4" : "max-h-0"}`}>
        <p className="text-[13px] text-slate-400 leading-relaxed px-1">{item.answer}</p>
      </div>
    </div>
  );
}

export function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <section className="py-24 px-4">
      <div className="max-w-3xl mx-auto">
        <ScrollReveal>
          <div className="text-center mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.04] text-white/40 border border-white/[0.06] mb-4 uppercase tracking-[0.2em]">
              FAQ
            </div>
            <h2 className="text-3xl sm:text-4xl font-display font-bold text-white/90 tracking-tight">
              Frequently Asked <span className="text-[#00f0ff]">Questions</span>
            </h2>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] px-6 sm:px-8">
            {FAQ_DATA.map((item, i) => (
              <AccordionItem
                key={i}
                item={item}
                isOpen={openIndex === i}
                onToggle={() => setOpenIndex(openIndex === i ? null : i)}
              />
            ))}
          </div>
        </ScrollReveal>
      </div>

      {/* Schema.org FAQPage JSON-LD */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            mainEntity: FAQ_DATA.map(item => ({
              "@type": "Question",
              name: item.question,
              acceptedAnswer: {
                "@type": "Answer",
                text: item.answer,
              },
            })),
          }),
        }}
      />
    </section>
  );
}
