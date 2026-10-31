"use client";
import { useState } from "react";
import { useI18n } from "@/lib/i18n/context";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

const faqKeys = [
  { q: "faq_q1", a: "faq_a1" },
  { q: "faq_q2", a: "faq_a2" },
  { q: "faq_q3", a: "faq_a3" },
  { q: "faq_q4", a: "faq_a4" },
  { q: "faq_q5", a: "faq_a5" },
  { q: "faq_q6", a: "faq_a6" },
];

export function FAQ() {
  const { t } = useI18n();
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const faqs = faqKeys.map((k) => ({ question: t(k.q), answer: t(k.a) }));

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({
      "@type": "Question",
      name: f.question,
      acceptedAnswer: { "@type": "Answer", text: f.answer },
    })),
  };

  const toggle = (i: number) => setOpenIndex(openIndex === i ? null : i);

  return (
    <section className="py-24 px-4">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div className="mx-auto max-w-3xl">
        <ScrollReveal>
          <div className="text-center mb-14">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.04] text-white/40 border border-white/[0.06] mb-4 uppercase tracking-[0.2em]">
              FAQ
            </div>
            <h2 className="text-3xl sm:text-4xl font-display font-bold text-white/90 tracking-tight">
              {t("faq_title")}
            </h2>
          </div>
        </ScrollReveal>

        <div className="space-y-3" role="region" aria-label="FAQ">
          {faqs.map((faq, i) => (
            <ScrollReveal key={i} delay={i * 60}>
              <div
                className={`bg-white/[0.02] border rounded-xl overflow-hidden transition-all duration-300 ${
                  openIndex === i
                    ? "border-[#00f0ff]/15 shadow-lg shadow-[#00f0ff]/[0.02]"
                    : "border-white/[0.06] hover:border-white/[0.10]"
                }`}
              >
                <button
                  onClick={() => toggle(i)}
                  onKeyDown={(e) => {
                    const btns = document.querySelectorAll("[data-faq-btn]") as NodeListOf<HTMLElement>;
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      btns[i + 1]?.focus();
                    } else if (e.key === "ArrowUp") {
                      e.preventDefault();
                      btns[i - 1]?.focus();
                    } else if (e.key === "Home") {
                      e.preventDefault();
                      btns[0]?.focus();
                    } else if (e.key === "End") {
                      e.preventDefault();
                      btns[btns.length - 1]?.focus();
                    }
                  }}
                  data-faq-btn
                  aria-expanded={openIndex === i}
                  className="w-full flex items-center justify-between p-5 text-left group"
                >
                  <span className="flex items-center gap-3">
                    <span className="w-7 h-7 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-[10px] font-mono text-white/25 font-bold shrink-0">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="text-white/80 font-medium text-sm pr-4 group-hover:text-white/90 transition-colors">
                      {faq.question}
                    </span>
                  </span>
                  <div
                    className={`w-6 h-6 rounded-lg border border-white/[0.08] flex items-center justify-center shrink-0 transition-all duration-200 ${
                      openIndex === i ? "bg-[#00f0ff]/10 border-[#00f0ff]/20 rotate-180" : "bg-white/[0.02]"
                    }`}
                  >
                    <svg
                      className={`w-3.5 h-3.5 transition-colors ${openIndex === i ? "text-[#00f0ff]" : "text-white/30"}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>
                <div
                  className={`overflow-hidden transition-all duration-300 ease-out ${
                    openIndex === i ? "max-h-96 pb-5" : "max-h-0"
                  }`}
                >
                  <div className="px-5 pl-[3.75rem]">
                    <p className="text-white/35 text-sm leading-relaxed">
                      {faq.answer}
                    </p>
                  </div>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
