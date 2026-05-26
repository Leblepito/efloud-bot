"use client";

import { useEffect, useState } from "react";
import { fromNow, n, pct, usd } from "@/lib/format";

interface TradeDetailPanelProps {
  trade: any;
  onClose: () => void;
}

export function TradeDetailPanel({ trade, onClose }: TradeDetailPanelProps) {
  const [isOpen, setIsOpen] = useState(false);

  // Trigger anim when trade changes
  useEffect(() => {
    if (trade) {
      setIsOpen(true);
    } else {
      setIsOpen(false);
    }
  }, [trade]);

  if (!trade) return null;

  const isLong = trade.direction === "LONG";
  const pnl = trade.pnl_usdt ?? 0;
  const profit = pnl >= 0;

  // Format confluence details
  let confDetails: any = null;
  if (trade.confluence_details) {
    try {
      confDetails = typeof trade.confluence_details === "string"
        ? JSON.parse(trade.confluence_details)
        : trade.confluence_details;
    } catch (e) {
      console.warn("Failed to parse confluence_details", e);
    }
  }

  // Sl Hunt proximity calculations
  const maeVal = parseFloat(trade.mae_pct || 0);
  const mfeVal = parseFloat(trade.mfe_pct || 0);
  
  // Calculate potential drawdown limit if SL was hit
  // If exit was SL, then Mae is close to 100% of SL distance
  const slDistancePct = trade.entry ? Math.abs((trade.sl - trade.entry) / trade.entry) * 100 : 0;
  // Adverse proximity: MAE % vs SL Distance %
  const adverseProximity = slDistancePct > 0 ? Math.min(100, (maeVal / slDistancePct) * 100) : 0;

  const handlePanelClose = () => {
    setIsOpen(false);
    setTimeout(onClose, 300); // Allow animation to complete
  };

  return (
    <div
      className={`fixed inset-y-0 right-0 z-50 w-full max-w-md bg-zinc-950/95 border-l border-zinc-800/80 backdrop-blur-md shadow-2xl transition-transform duration-300 transform font-mono ${
        isOpen ? "translate-x-0" : "translate-x-full"
      }`}
    >
      {/* Header */}
      <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
        <div>
          <span className="text-[10px] uppercase tracking-widest text-zinc-500 block mb-0.5">Trade Inspector</span>
          <h2 className="text-zinc-200 text-sm font-bold flex items-center gap-2">
            {trade.symbol} 
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-widest ${
              isLong ? "text-emerald-400 border border-emerald-500/20 bg-emerald-500/5" : "text-rose-400 border border-rose-500/20 bg-rose-500/5"
            }`}>
              {isLong ? "▲ LONG" : "▼ SHORT"}
            </span>
          </h2>
        </div>
        <button
          onClick={handlePanelClose}
          className="text-zinc-500 hover:text-zinc-300 transition-colors p-1"
        >
          ✕
        </button>
      </div>

      {/* Content Scroll Area */}
      <div className="h-[calc(100vh-69px)] overflow-y-auto px-6 py-6 space-y-6 text-xs text-zinc-400">
        
        {/* PnL & Summary Card */}
        <div className={`p-4 rounded-xl border relative overflow-hidden ${
          profit ? "border-emerald-500/10 bg-emerald-500/5" : "border-rose-500/10 bg-rose-500/5"
        }`}>
          <div className="flex justify-between items-baseline mb-2">
            <span className="text-zinc-500 text-[10px] uppercase tracking-wider">Realized PnL</span>
            <span className={`text-lg font-bold ${profit ? "text-emerald-400" : "text-rose-400"}`}>
              {usd(pnl)} ({trade.pnl_pct != null ? (pnl >= 0 ? "+" : "") + pct(trade.pnl_pct) : "—"})
            </span>
          </div>
          <div className="grid grid-cols-2 gap-y-2 mt-3 pt-3 border-t border-zinc-800/40 text-zinc-400">
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">Entry Price</span>
              <span className="text-zinc-200">{n(trade.entry, 4)}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">Exit Price</span>
              <span className="text-zinc-200">{trade.exit ? n(trade.exit, 4) : "—"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">Trade Duration</span>
              <span className="text-zinc-200">{trade.closed_at ? fromNow(trade.opened_at) + " (Kapandı)" : fromNow(trade.opened_at)}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">Exit Reason</span>
              <span className={`text-[10px] font-bold ${
                trade.reason === "SL" ? "text-rose-400" : ["TP1", "TP2"].includes(trade.reason || "") ? "text-emerald-400" : "text-zinc-300"
              }`}>
                {trade.reason || "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Dynamic Excursion Indicators (MAE/MFE) */}
        <div className="border border-zinc-800 bg-zinc-950/20 p-4 rounded-xl space-y-4">
          <h3 className="text-[10px] tracking-widest text-zinc-500 uppercase font-bold border-b border-zinc-800/50 pb-2">
            Excursion Analysis (MAE / MFE)
          </h3>
          
          {/* MAE Meter */}
          <div>
            <div className="flex justify-between items-center text-[10px] mb-1">
              <span className="text-zinc-400">Max Adverse Excursion (MAE)</span>
              <span className="text-rose-400 font-bold">{maeVal.toFixed(2)}%</span>
            </div>
            <div className="w-full bg-zinc-900 h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-rose-500 h-1.5 rounded-full"
                style={{ width: `${Math.min(100, Math.max(0, maeVal * 15))}%` }} // Scale factor for visualization
              />
            </div>
            <span className="text-[9px] text-zinc-600 block mt-1">
              Adverse Drawdown Proximity: {adverseProximity.toFixed(1)}% of Stop Loss
            </span>
          </div>

          {/* MFE Meter */}
          <div>
            <div className="flex justify-between items-center text-[10px] mb-1">
              <span className="text-zinc-400">Max Favorable Excursion (MFE)</span>
              <span className="text-emerald-400 font-bold">{mfeVal.toFixed(2)}%</span>
            </div>
            <div className="w-full bg-zinc-900 h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-emerald-500 h-1.5 rounded-full"
                style={{ width: `${Math.min(100, Math.max(0, mfeVal * 15))}%` }} // Scale factor for visualization
              />
            </div>
          </div>
        </div>

        {/* SMC v2 Advanced Telemetry */}
        <div className="border border-zinc-800 bg-zinc-950/20 p-4 rounded-xl space-y-3">
          <h3 className="text-[10px] tracking-widest text-zinc-500 uppercase font-bold border-b border-zinc-800/50 pb-2">
            SMC v2 Indicator Telemetry
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">Setup Source</span>
              <span className="text-zinc-200 font-bold">{trade.entry_setup_source || "— (v1)"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">Bars to Pullback</span>
              <span className="text-zinc-200">{trade.bars_to_pullback != null ? `${trade.bars_to_pullback} bars` : "—"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">TP1 Target Type</span>
              <span className="text-zinc-300">{trade.tp1_target_type || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">TP2 Target Type</span>
              <span className="text-zinc-300">{trade.tp2_target_type || "—"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">ADX (Trend Strength)</span>
              <span className="text-zinc-200">{trade.adx_value != null ? `${trade.adx_value.toFixed(1)}` : "—"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">ATR (Volatility)</span>
              <span className="text-zinc-200">{trade.atr_value != null ? `${trade.atr_value.toFixed(4)}` : "—"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">Funding Rate</span>
              <span className="text-zinc-300">{trade.funding_rate != null ? `${(trade.funding_rate * 100).toFixed(4)}%` : "—"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-zinc-500 block">Original SL</span>
              <span className="text-zinc-300">{trade.initial_sl != null ? n(trade.initial_sl, 4) : "—"}</span>
            </div>
          </div>
        </div>

        {/* Confluence scoring & triggers */}
        {confDetails && (
          <div className="border border-zinc-800 bg-zinc-950/20 p-4 rounded-xl space-y-3">
            <div className="flex items-center justify-between border-b border-zinc-800/50 pb-2">
              <h3 className="text-[10px] tracking-widest text-zinc-500 uppercase font-bold">
                Confluence Scoring Matrix
              </h3>
              <span className="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-bold text-[10px]">
                Score: {confDetails.score ?? confDetails.confluence_score ?? 0}
              </span>
            </div>

            <div className="space-y-2">
              {confDetails.htf_bias && (
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-zinc-500">HTF Trend Bias</span>
                  <span className={`font-bold ${confDetails.htf_bias === "BULLISH" ? "text-emerald-400" : "text-rose-400"}`}>
                    {confDetails.htf_bias}
                  </span>
                </div>
              )}
              {confDetails.mtf_bias && (
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-zinc-500">MTF Trend Bias</span>
                  <span className={`font-bold ${confDetails.mtf_bias === "BULLISH" ? "text-emerald-400" : "text-rose-400"}`}>
                    {confDetails.mtf_bias}
                  </span>
                </div>
              )}
              {confDetails.reasons && confDetails.reasons.length > 0 && (
                <div className="pt-2 border-t border-zinc-900">
                  <span className="text-[9px] uppercase tracking-wider text-zinc-500 block mb-1.5">Confluence Factors</span>
                  <div className="flex flex-wrap gap-1.5">
                    {confDetails.reasons.map((r: string, idx: number) => (
                      <span key={idx} className="bg-zinc-900 text-zinc-300 px-2 py-0.5 rounded-sm text-[9px] border border-zinc-800">
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Trace Info */}
        <div className="text-[9px] text-zinc-600 flex justify-between items-center pt-2">
          <span>Trace ID: {trade.trace_id || "v1-legacy-id"}</span>
          <span>Open Bar TS: {trade.bar_ts_ms || "N/A"}</span>
        </div>

      </div>
    </div>
  );
}
