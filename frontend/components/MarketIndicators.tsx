"use client";

import React, { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, Tooltip, ResponsiveContainer } from "recharts";
import { n } from "@/lib/format";

interface FundingRateData {
  symbol: string;
  funding_rate: number;
  mark_price: number;
  index_price: number;
  next_funding_time: number;
}

interface OIHistoryPoint {
  timestamp: number;
  open_interest: number;
  open_interest_value: number;
  price: number;
}

interface OIResponse {
  symbol: string;
  history: OIHistoryPoint[];
  trend: "LONG_BUILDUP" | "SHORT_BUILDUP" | "SHORT_COVERING" | "LONG_LIQUIDATION" | "NEUTRAL";
  trend_description: string;
  trend_color: "emerald" | "rose" | "cyan" | "blue" | "zinc";
}

export function MarketIndicators() {
  const [fundingRates, setFundingRates] = useState<FundingRateData[]>([]);
  const [oiData, setOiData] = useState<OIResponse | null>(null);
  const [selectedOiSymbol, setSelectedOiSymbol] = useState("BTCUSDT");
  const [loading, setLoading] = useState(true);

  const fetchFunding = async () => {
    try {
      const res = await fetch("/api/market/funding-rates", { credentials: "include" });
      if (res.status === 401) return;
      const data = await res.json();
      setFundingRates(data);
    } catch (e) {
      console.error("Failed to fetch funding rates", e);
    }
  };

  const fetchOI = async (symbol: string) => {
    try {
      const res = await fetch(`/api/market/open-interest?symbol=${symbol}`, { credentials: "include" });
      if (res.status === 401) return;
      const data = await res.json();
      setOiData(data);
    } catch (e) {
      console.error("Failed to fetch open interest data", e);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchFunding(), fetchOI(selectedOiSymbol)]);
      setLoading(false);
    };
    init();
    const interval = setInterval(() => {
      fetchFunding();
      fetchOI(selectedOiSymbol);
    }, 15000);
    return () => clearInterval(interval);
  }, [selectedOiSymbol]);

  if (loading && fundingRates.length === 0) {
    return (
      <div className="border border-border bg-bg-elevated p-6 animate-pulse text-text-muted font-mono text-xs">
        Piyasa Kaldıraç Göstergeleri Yükleniyor...
      </div>
    );
  }

  // Funding-rate color coding → native accent palette
  const getFundingRateStyle = (rate: number) => {
    const pct = rate * 100;
    if (pct > 0.03)   return { bg: "bg-accent-green/10 border-accent-green/30", text: "text-accent-green", label: "AŞIRI BOĞA KALDIRACI" };
    if (pct > 0.005)  return { bg: "bg-accent-green/[0.04] border-accent-green/15", text: "text-accent-green", label: "STANDART BOĞA" };
    if (pct < -0.01)  return { bg: "bg-accent-red/10 border-accent-red/30", text: "text-accent-red", label: "AŞIRI AYI KALDIRACI" };
    if (pct < 0)      return { bg: "bg-accent-red/[0.04] border-accent-red/15", text: "text-accent-red", label: "AYI BASKISI" };
    return { bg: "bg-bg-surface border-border", text: "text-text-secondary", label: "DENGELİ" };
  };

  const trendColors: Record<OIResponse["trend_color"], string> = {
    emerald: "text-accent-green border-accent-green/25 bg-accent-green/5",
    rose: "text-accent-red border-accent-red/25 bg-accent-red/5",
    cyan: "text-blue-400 border-blue-500/25 bg-blue-500/5",
    blue: "text-blue-400 border-blue-500/25 bg-blue-500/5",
    zinc: "text-text-secondary border-border bg-bg-surface",
  };

  const formatChartDate = (ms: number) => {
    const d = new Date(ms);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 font-mono">
      {/* 1. Funding Rate Heatmap */}
      <div className="border border-border bg-bg-elevated p-5 hover:border-border-strong transition-colors duration-200 flex flex-col justify-between col-span-1">
        <div>
          <div className="flex items-center gap-2 mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-green dot-breathe" />
            <h3 className="text-[10px] tracking-widest text-text-secondary uppercase font-bold">
              Binance Fonlama Oranları
            </h3>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-4">
            {fundingRates.map((fr) => {
              const style = getFundingRateStyle(fr.funding_rate);
              return (
                <div
                  key={fr.symbol}
                  className={`border p-3 hover:-translate-y-0.5 transition-transform duration-150 cursor-pointer ${style.bg}`}
                >
                  <span className="text-[10px] text-text-muted font-bold block">{fr.symbol.replace("USDT", " / USDT")}</span>
                  <span className={`text-sm font-black tracking-tight tabular-nums ${style.text}`}>
                    {(fr.funding_rate * 100).toFixed(4)}%
                  </span>
                  <span className="text-[8px] text-text-muted uppercase tracking-wider block mt-1">
                    {style.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-t border-border pt-3 text-[9px] text-text-muted leading-relaxed uppercase">
          Fonlama oranı pozitifse Long'lar Short'lara öder (alıcı iştahı yüksek). Negatifse Short'lar Long'lara öder (satıcı iştahı yüksek).
        </div>
      </div>

      {/* 2. Open Interest & Leverage Trend */}
      <div className="border border-border bg-bg-elevated p-5 hover:border-border-strong transition-colors duration-200 col-span-2 flex flex-col justify-between">
        <div>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dot-breathe" />
              <h3 className="text-[10px] tracking-widest text-text-secondary uppercase font-bold">
                Kaldıraç &amp; Trend Sentezi (Coinanalys)
              </h3>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[9px] text-text-muted uppercase">Enstrüman:</span>
              <select
                value={selectedOiSymbol}
                onChange={(e) => setSelectedOiSymbol(e.target.value)}
                className="bg-bg-surface border border-border text-text-secondary px-2 py-1 text-[10px] focus:outline-none focus:border-blue-500/50 cursor-pointer"
              >
                {fundingRates.map((fr) => (
                  <option key={fr.symbol} value={fr.symbol}>{fr.symbol}</option>
                ))}
              </select>
            </div>
          </div>

          {oiData && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className={`md:col-span-1 border p-4 flex flex-col justify-center gap-1.5 ${trendColors[oiData.trend_color]}`}>
                <span className="text-[8px] uppercase tracking-wider opacity-60">Leverage Trend</span>
                <span className="text-xs font-black uppercase tracking-widest block leading-tight">
                  {oiData.trend.replace("_", " ")}
                </span>
                <p className="text-[9px] opacity-80 leading-normal">{oiData.trend_description}</p>
              </div>

              <div className="md:col-span-2 h-[120px] w-full border border-border p-2 bg-bg-surface">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={oiData.history} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                    <defs>
                      <linearGradient id="colorOi" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="timestamp" tickFormatter={formatChartDate} stroke="#2A2A2A" fontSize={8} tickLine={false} />
                    <Tooltip
                      labelFormatter={(t) => `Tarih: ${new Date(t).toLocaleTimeString()}`}
                      contentStyle={{ background: "#0A0A0A", border: "1px solid #1F1F1F", fontSize: "9px", borderRadius: 0 }}
                      formatter={(val: any, name: string) => {
                        if (name === "open_interest") return [n(val, 2), "Open Interest"];
                        if (name === "price") return [`$${n(val, 2)}`, "Fiyat"];
                        return [val, name];
                      }}
                    />
                    <Area type="monotone" dataKey="open_interest" stroke="#60a5fa" strokeWidth={1.5} fillOpacity={1} fill="url(#colorOi)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-border pt-3 text-[9px] text-text-muted leading-relaxed uppercase flex flex-wrap gap-x-4 gap-y-1">
          <span className="inline-flex items-center gap-1.5"><span className="w-1.5 h-1.5 bg-accent-green" />Price ↑ + OI ↑ = Long Buildup</span>
          <span className="inline-flex items-center gap-1.5"><span className="w-1.5 h-1.5 bg-accent-red" />Price ↓ + OI ↑ = Short Buildup</span>
          <span className="inline-flex items-center gap-1.5"><span className="w-1.5 h-1.5 bg-accent-amber" />Price ↑ + OI ↓ = Short Covering</span>
          <span className="inline-flex items-center gap-1.5"><span className="w-1.5 h-1.5 bg-blue-400" />Price ↓ + OI ↓ = Long Liquidation</span>
        </div>
      </div>
    </div>
  );
}
