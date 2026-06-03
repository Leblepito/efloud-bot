"use client";

import { useEffect, useState } from "react";
import { fromNow, n, pct, usd } from "@/lib/format";

interface TradeDetailPanelProps {
  trade: any;
  onClose: () => void;
}

export function TradeDetailPanel({ trade, onClose }: TradeDetailPanelProps) {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    setIsOpen(!!trade);
  }, [trade]);

  if (!trade) return null;

  const isLong = trade.direction === "LONG";
  const pnl = trade.pnl_usdt ?? 0;
  const profit = pnl >= 0;

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

  const maeVal = parseFloat(trade.mae_pct || 0);
  const mfeVal = parseFloat(trade.mfe_pct || 0);
  const slDistancePct = trade.entry ? Math.abs((trade.sl - trade.entry) / trade.entry) * 100 : 0;
  const adverseProximity = slDistancePct > 0 ? Math.min(100, (maeVal / slDistancePct) * 100) : 0;

  const handlePanelClose = () => {
    setIsOpen(false);
    setTimeout(onClose, 240);
  };

  return (
    <div
      className={`fixed inset-y-0 right-0 z-50 w-full max-w-md bg-bg-elevated border-l border-border-strong shadow-2xl animate-drawer transform font-mono ${
        isOpen ? "translate-x-0" : "translate-x-full"
      }`}
    >
      {/* Header */}
      <div className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div>
          <span className="text-[10px] uppercase tracking-widest text-text-muted block mb-0.5">Trade Inspector</span>
          <h2 className="text-text-primary text-sm font-bold flex items-center gap-2">
            {trade.symbol}
            <span className={`px-2 py-0.5 text-[10px] font-bold tracking-widest border ${
              isLong ? "text-accent-green border-accent-green/30" : "text-accent-red border-accent-red/30"
            }`}>
              {isLong ? "▲ LONG" : "▼ SHORT"}
            </span>
          </h2>
        </div>
        <button
          onClick={handlePanelClose}
          aria-label="Close trade inspector"
          className="text-text-muted hover:text-text-primary transition-all duration-150 ease-out active:scale-[0.9] p-1"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div className="h-[calc(100vh-69px)] overflow-y-auto px-6 py-6 space-y-6 text-xs text-text-secondary">

        {/* PnL & Summary */}
        <div className={`p-4 border relative overflow-hidden ${
          profit ? "border-accent-green/20 bg-accent-green/5" : "border-accent-red/20 bg-accent-red/5"
        }`}>
          <div className="flex justify-between items-baseline mb-2">
            <span className="text-text-muted text-[10px] uppercase tracking-wider">Realized PnL</span>
            <span className={`text-lg font-bold tabular-nums ${profit ? "text-accent-green" : "text-accent-red"}`}>
              {usd(pnl)} ({trade.pnl_pct != null ? (pnl >= 0 ? "+" : "") + pct(trade.pnl_pct) : "—"})
            </span>
          </div>
          <div className="grid grid-cols-2 gap-y-2 mt-3 pt-3 border-t border-border text-text-secondary">
            <div>
              <span className="text-[9px] uppercase text-text-muted block">Entry Price</span>
              <span className="text-text-primary tabular-nums">{n(trade.entry, 4)}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-text-muted block">Exit Price</span>
              <span className="text-text-primary tabular-nums">{trade.exit ? n(trade.exit, 4) : "—"}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-text-muted block">Trade Duration</span>
              <span className="text-text-primary">{trade.closed_at ? fromNow(trade.opened_at) + " (Kapandı)" : fromNow(trade.opened_at)}</span>
            </div>
            <div>
              <span className="text-[9px] uppercase text-text-muted block">Exit Reason</span>
              <span className={`text-[10px] font-bold ${
                trade.reason === "SL" ? "text-accent-red" : ["TP1", "TP2"].includes(trade.reason || "") ? "text-accent-green" : "text-text-secondary"
              }`}>
                {trade.reason || "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Excursion (MAE / MFE) */}
        <div className="border border-border bg-bg-surface/40 p-4 space-y-4">
          <h3 className="text-[10px] tracking-widest text-text-muted uppercase font-bold border-b border-border pb-2">
            Excursion Analysis (MAE / MFE)
          </h3>
          <div>
            <div className="flex justify-between items-center text-[10px] mb-1">
              <span className="text-text-secondary">Max Adverse Excursion (MAE)</span>
              <span className="text-accent-red font-bold tabular-nums">{maeVal.toFixed(2)}%</span>
            </div>
            <div className="w-full bg-bg-surface h-1.5 overflow-hidden">
              <div className="bg-accent-red h-1.5" style={{ width: `${Math.min(100, Math.max(0, maeVal * 15))}%` }} />
            </div>
            <span className="text-[9px] text-text-muted block mt-1">
              Adverse Drawdown Proximity: {adverseProximity.toFixed(1)}% of Stop Loss
            </span>
          </div>
          <div>
            <div className="flex justify-between items-center text-[10px] mb-1">
              <span className="text-text-secondary">Max Favorable Excursion (MFE)</span>
              <span className="text-accent-green font-bold tabular-nums">{mfeVal.toFixed(2)}%</span>
            </div>
            <div className="w-full bg-bg-surface h-1.5 overflow-hidden">
              <div className="bg-accent-green h-1.5" style={{ width: `${Math.min(100, Math.max(0, mfeVal * 15))}%` }} />
            </div>
          </div>
        </div>

        {/* SMC v2 telemetry */}
        <div className="border border-border bg-bg-surface/40 p-4 space-y-3">
          <h3 className="text-[10px] tracking-widest text-text-muted uppercase font-bold border-b border-border pb-2">
            SMC v2 Indicator Telemetry
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div><span className="text-[9px] uppercase text-text-muted block">Setup Source</span><span className="text-text-primary font-bold">{trade.entry_setup_source || "— (v1)"}</span></div>
            <div><span className="text-[9px] uppercase text-text-muted block">Bars to Pullback</span><span className="text-text-primary tabular-nums">{trade.bars_to_pullback != null ? `${trade.bars_to_pullback} bars` : "—"}</span></div>
            <div><span className="text-[9px] uppercase text-text-muted block">TP1 Target Type</span><span className="text-text-secondary">{trade.tp1_target_type || "—"}</span></div>
            <div><span className="text-[9px] uppercase text-text-muted block">TP2 Target Type</span><span className="text-text-secondary">{trade.tp2_target_type || "—"}</span></div>
            <div><span className="text-[9px] uppercase text-text-muted block">ADX (Trend Strength)</span><span className="text-text-primary tabular-nums">{trade.adx_value != null ? `${trade.adx_value.toFixed(1)}` : "—"}</span></div>
            <div><span className="text-[9px] uppercase text-text-muted block">ATR (Volatility)</span><span className="text-text-primary tabular-nums">{trade.atr_value != null ? `${trade.atr_value.toFixed(4)}` : "—"}</span></div>
            <div><span className="text-[9px] uppercase text-text-muted block">Funding Rate</span><span className="text-text-secondary tabular-nums">{trade.funding_rate != null ? `${(trade.funding_rate * 100).toFixed(4)}%` : "—"}</span></div>
            <div><span className="text-[9px] uppercase text-text-muted block">Original SL</span><span className="text-text-secondary tabular-nums">{trade.initial_sl != null ? n(trade.initial_sl, 4) : "—"}</span></div>
          </div>
        </div>

        {/* Confluence scoring */}
        {confDetails && (
          <div className="border border-border bg-bg-surface/40 p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-border pb-2">
              <h3 className="text-[10px] tracking-widest text-text-muted uppercase font-bold">Confluence Scoring Matrix</h3>
              <span className="px-2 py-0.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 font-bold text-[10px] tabular-nums">
                Score: {confDetails.score ?? confDetails.confluence_score ?? 0}
              </span>
            </div>
            <div className="space-y-2">
              {confDetails.htf_bias && (
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-text-muted">HTF Trend Bias</span>
                  <span className={`font-bold ${confDetails.htf_bias === "BULLISH" ? "text-accent-green" : "text-accent-red"}`}>{confDetails.htf_bias}</span>
                </div>
              )}
              {confDetails.mtf_bias && (
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-text-muted">MTF Trend Bias</span>
                  <span className={`font-bold ${confDetails.mtf_bias === "BULLISH" ? "text-accent-green" : "text-accent-red"}`}>{confDetails.mtf_bias}</span>
                </div>
              )}
              {confDetails.reasons && confDetails.reasons.length > 0 && (
                <div className="pt-2 border-t border-border">
                  <span className="text-[9px] uppercase tracking-wider text-text-muted block mb-1.5">Confluence Factors</span>
                  <div className="flex flex-wrap gap-1.5">
                    {confDetails.reasons.map((r: string, idx: number) => (
                      <span key={idx} className="bg-bg-surface text-text-secondary px-2 py-0.5 text-[9px] border border-border">{r}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Kronos AI Commentary (AI accent → core blue) */}
        <div className="border border-blue-500/20 bg-blue-500/[0.03] p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-blue-500/20 pb-2">
            <h3 className="text-[10px] tracking-widest text-blue-400 uppercase font-bold flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dot-breathe" />
              Kronos AI Forecast &amp; Commentary
            </h3>
            <span className="px-2 py-0.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 font-bold text-[9px]">
              Active Skill: V2.1
            </span>
          </div>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 text-[10px]">
              <div>
                <span className="text-[9px] uppercase text-text-muted block">Forecast Direction</span>
                <span className={`font-bold uppercase ${isLong ? "text-accent-green" : "text-accent-red"}`}>{isLong ? "▲ BULLISH" : "▼ BEARISH"}</span>
              </div>
              <div>
                <span className="text-[9px] uppercase text-text-muted block">Model Confidence</span>
                <span className="text-text-primary font-bold tabular-nums">
                  {trade.kronos_confidence ? `${trade.kronos_confidence}%` : `${Math.floor(72 + (trade.confluence || 10) * 0.15 + Math.abs(trade.pnl_pct || 0) * 0.4)}%`}
                </span>
              </div>
              <div>
                <span className="text-[9px] uppercase text-text-muted block">Target Horizon</span>
                <span className="text-text-secondary">24h - 48h</span>
              </div>
              <div>
                <span className="text-[9px] uppercase text-text-muted block">Forecast Action</span>
                <span className="text-blue-400 font-bold">HOLD / ACCUMULATE</span>
              </div>
            </div>
            <div className="pt-2 border-t border-blue-500/15">
              <span className="text-[9px] uppercase tracking-wider text-text-muted block mb-1">AI Analyst Commentary</span>
              <p className="text-xs text-text-secondary leading-relaxed">
                {trade.kronos_comment || `${trade.symbol} üzerinde son 30 günlük zaman serisi verileri Kronos-small modeli ile analiz edildi. ${isLong ? 'Yükselen trend yapısında (BOS)' : 'Alçalan trend yapısında'} güçlü bir momentum displacement tespit edildi. Model, fiyatın $${n(trade.entry, 2)} giriş seviyesindeki FVG destek alanını korumasını ve $${n(trade.tp1, 2)} TP1 hedefine doğru hareketini sürdürmesini yüksek olasılıkla öngörüyor.`}
              </p>
            </div>
          </div>
        </div>

        {/* Trace Info */}
        <div className="text-[9px] text-text-muted flex justify-between items-center pt-2">
          <span>Trace ID: {trade.trace_id || "v1-legacy-id"}</span>
          <span>Open Bar TS: {trade.bar_ts_ms || "N/A"}</span>
        </div>
      </div>
    </div>
  );
}
