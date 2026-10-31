"use client";

import { useI18n } from "@/lib/i18n/context";
import { Lock, Globe, CreditCard, Shield, Bot, Code } from "lucide-react";

export function TrustStrip() {
  const { t } = useI18n();

  const items = [
    { icon: Globe, text: t("trust_binance"), color: "text-[#00f0ff]" },
    { icon: Lock, text: t("trust_encryption"), color: "text-[#00f0ff]" },
    { icon: Bot, text: t("trust_ai_bot"), color: "text-[#00f0ff]" },
    { icon: Shield, text: t("trust_risk_mgmt"), color: "text-[#00f0ff]" },
    { icon: Code, text: t("trust_open_signals"), color: "text-[#00f0ff]" },
    { icon: CreditCard, text: t("trust_no_card"), color: "text-[#00f0ff]" },
  ];

  return (
    <section className="py-10 px-4 border-t border-white/[0.03]" style={{ background: "rgba(255,255,255,0.005)" }}>
      <div className="mx-auto max-w-6xl grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
        {items.map((item) => (
          <div
            key={item.text}
            className="flex flex-col items-center gap-2 py-4 px-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-white/[0.12] transition-colors duration-300"
          >
            <item.icon
              className={`w-5 h-5 ${item.color} shrink-0`}
              strokeWidth={1.5}
            />
            <span className="text-[11px] text-slate-400 font-medium tracking-wide text-center leading-tight">
              {item.text}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
