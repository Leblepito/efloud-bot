"use client";

import Link from "next/link";
import { ArrowRight, Zap } from "lucide-react";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

export function CTABanner() {
  return (
    <section className="py-20 px-4">
      <ScrollReveal>
        <div className="max-w-4xl mx-auto relative overflow-hidden rounded-2xl">
          {/* Background gradient */}
          <div className="absolute inset-0 bg-gradient-to-r from-[#00f0ff]/20 via-[#0080ff]/15 to-[#a855f7]/10" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
          <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "radial-gradient(circle, white 1px, transparent 1px)", backgroundSize: "20px 20px" }} />

          <div className="relative z-10 px-6 sm:px-12 py-12 sm:py-16 text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold bg-white/[0.08] text-[#00f0ff] border border-[#00f0ff]/20 mb-6">
              <Zap className="w-3 h-3" />
              Start trading in under 2 minutes
            </div>

            <h2 className="text-3xl sm:text-5xl font-display font-bold text-white tracking-tight mb-4">
              Ready to Trade <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#00f0ff] to-[#0080ff]">Smarter</span>?
            </h2>
            <p className="text-slate-300 text-sm sm:text-base max-w-lg mx-auto mb-8">
              Join thousands of traders using AI-powered signals, automated bots, and professional backtesting tools.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link
                href="/auth"
                className="group px-8 py-4 bg-gradient-to-r from-[#00f0ff] to-[#0080ff] text-white font-bold rounded-xl transition-all text-sm hover:scale-[1.02] hover:brightness-110 flex items-center justify-center gap-2 animate-cta-glow"
              >
                Start Free — No Credit Card
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <Link
                href="/pricing"
                className="px-6 py-3.5 border border-white/[0.1] bg-white/[0.04] text-slate-200 font-semibold text-sm rounded-xl hover:bg-white/[0.08] transition-all"
              >
                View Pricing
              </Link>
            </div>

            <p className="text-[10px] text-slate-500 mt-4">
              No credit card required. Free forever plan available.
            </p>
          </div>
        </div>
      </ScrollReveal>
    </section>
  );
}
