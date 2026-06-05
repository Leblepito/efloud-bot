"use client";

import React from "react";

interface Trade {
  kronos_comment?: string;
  kronos_confidence?: number;
  confluence?: number | null;
  symbol?: string;
}

interface KronosCardProps {
  trade: Trade;
}

export function KronosCard({ trade }: KronosCardProps) {
  if (!trade || !trade.kronos_comment) {
    return null;
  }

  const comment = trade.kronos_comment;
  const confidence = trade.kronos_confidence ?? 50;

  // Deduce the categorical band based on confidence score and text hints
  const getBandInfo = (conf: number, text: string) => {
    const lower = text.toLowerCase();
    if (lower.includes("narrow") || lower.includes("dar") || conf >= 85) {
      return {
        name: "NARROW",
        color: "text-accent-green border-accent-green/30 bg-accent-green/5",
        desc: "High confidence technical alignment",
      };
    }
    if (lower.includes("moderate") || lower.includes("orta") || conf >= 60) {
      return {
        name: "MODERATE",
        color: "text-yellow-400 border-yellow-400/30 bg-yellow-400/5",
        desc: "Mixed direction or wider dispersion",
      };
    }
    return {
      name: "WIDE",
      color: "text-accent-red border-accent-red/30 bg-accent-red/5",
      desc: "Model is hedging / high variance",
    };
  };

  const band = getBandInfo(confidence, comment);

  return (
    <div className="border border-blue-500/20 bg-blue-500/[0.03] p-4 space-y-3 font-mono border-l-2 border-l-blue-400">
      <div className="flex items-center justify-between border-b border-blue-500/15 pb-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dot-breathe" />
          <h3 className="text-[10px] tracking-widest text-blue-400 uppercase font-bold">
            Kronos AI Forecast
          </h3>
        </div>
        <span className={`px-2 py-0.5 border text-[9px] font-bold tracking-widest ${band.color}`}>
          {band.name}
        </span>
      </div>

      <div className="space-y-2.5">
        <div className="text-[10px] text-text-muted leading-tight">
          <span className="text-text-secondary font-bold">Band Status: </span>
          {band.desc}
        </div>

        <div className="pt-2 border-t border-blue-500/10">
          <span className="text-[9px] uppercase tracking-wider text-text-muted block mb-1">
            AI Advisory Commentary
          </span>
          <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">
            {comment}
          </p>
        </div>

        <div className="pt-2 border-t border-blue-500/10 text-[9px] text-blue-400/70 leading-normal flex items-start gap-1">
          <span>⚠️</span>
          <span>
            <strong>ADVISORY ONLY:</strong> This analysis is post-signal commentary and did <strong>NOT</strong> influence or gate the trade execution.
          </span>
        </div>
      </div>
    </div>
  );
}
