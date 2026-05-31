"use client";
import { useI18n } from "@/lib/i18n/context";
import { AlertTriangle } from "lucide-react";

export function RiskDisclaimer() {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="rounded-xl border border-[#ffaa00]/10 bg-[#ffaa00]/[0.03] p-5 flex items-start gap-4">
        <div className="w-8 h-8 rounded-lg bg-[#ffaa00]/10 border border-[#ffaa00]/15 flex items-center justify-center shrink-0">
          <AlertTriangle className="w-4 h-4 text-[#ffaa00]/70" strokeWidth={1.5} />
        </div>
        <div className="space-y-1">
          <p className="text-[#ffaa00]/60 text-[11px] font-bold uppercase tracking-[0.15em]">Risk Disclaimer</p>
          <p className="text-white/25 text-xs leading-relaxed">
            {t("risk_disclaimer")}
          </p>
        </div>
      </div>
    </div>
  );
}
