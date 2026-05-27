"use client";

import React, { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
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
  const [error, setError] = useState<string | null>(null);

  // Fetch Funding Rates
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

  // Fetch Open Interest
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

    // Poll every 15 seconds to keep data fresh
    const interval = setInterval(() => {
      fetchFunding();
      fetchOI(selectedOiSymbol);
    }, 15000);

    return () => clearInterval(interval);
  }, [selectedOiSymbol]);

  if (loading && fundingRates.length === 0) {
    return (
      <div className="border border-zinc-800 bg-zinc-950/40 p-6 rounded-xl animate-pulse text-zinc-500 font-mono text-xs">
        Piyasa Kaldıraç Göstergeleri Yükleniyor...
      </div>
    );
  }

  // Helper for funding rate color coding
  const getFundingRateStyle = (rate: number) => {
    const pct = rate * 100;
    if (pct > 0.03) {
      return {
        bg: "bg-emerald-500/15 border-emerald-500/35",
        text: "text-emerald-400",
        label: "AŞIRI BOĞA KALDIRACI",
      };
    } else if (pct > 0.005) {
      return {
        bg: "bg-emerald-500/5 border-emerald-500/15",
        text: "text-emerald-500",
        label: "STANDART BOĞA",
      };
    } else if (pct < -0.01) {
      return {
        bg: "bg-rose-500/15 border-rose-500/35",
        text: "text-rose-400",
        label: "AŞIRI AYI KALDIRACI",
      };
    } else if (pct < 0) {
      return {
        bg: "bg-rose-500/5 border-rose-500/15",
        text: "text-rose-500",
        label: "AYI BASKISI",
      };
    } else {
      return {
        bg: "bg-zinc-500/5 border-zinc-500/15",
        text: "text-zinc-400",
        label: "DENGELİ",
      };
    }
  };

  const trendColors = {
    emerald: "text-emerald-400 border-emerald-500/25 bg-emerald-500/5",
    rose: "text-rose-400 border-rose-500/25 bg-rose-500/5",
    cyan: "text-cyan-400 border-cyan-500/25 bg-cyan-500/5",
    blue: "text-blue-400 border-blue-500/25 bg-blue-500/5",
    zinc: "text-zinc-400 border-zinc-500/25 bg-zinc-500/5",
  };

  // Format Recharts dates
  const formatChartDate = (ms: number) => {
    const d = new Date(ms);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 font-mono">
      {/* 1. Funding Rate Heatmap */}
      <div className="border border-zinc-800 bg-zinc-950/30 p-5 rounded-xl hover:border-zinc-700 transition-all duration-300 flex flex-col justify-between col-span-1">
        <div>
          <div className="flex items-center gap-2 mb-4">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <h3 className="text-[10px] tracking-widest text-zinc-500 uppercase font-bold">
              Binance Fonlama Oranları (Heatmap)
            </h3>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-4">
            {fundingRates.map((fr) => {
              const style = getFundingRateStyle(fr.funding_rate);
              return (
                <div
                  key={fr.symbol}
                  className={`border rounded-lg p-3 hover:scale-[1.02] transition-all duration-200 cursor-pointer ${style.bg}`}
                >
                  <span className="text-[10px] text-zinc-400 font-bold block">{fr.symbol.replace("USDT", " / USDT")}</span>
                  <span className={`text-sm font-black tracking-tight ${style.text}`}>
                    {(fr.funding_rate * 100).toFixed(4)}%
                  </span>
                  <span className="text-[8px] text-zinc-500 uppercase tracking-wider block mt-1">
                    {style.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-t border-zinc-900 pt-3 text-[9px] text-zinc-600 leading-relaxed uppercase">
          💡 Fonlama oranı pozitifse Long'lar Short'lara öder (Alıcı iştahı yüksek). Negatifse Short'lar Long'lara öder (Satıcı iştahı yüksek).
        </div>
      </div>

      {/* 2. Coinglass Open Interest and Leverage Trend */}
      <div className="border border-zinc-800 bg-zinc-950/30 p-5 rounded-xl hover:border-zinc-700 transition-all duration-300 col-span-2 flex flex-col justify-between">
        <div>
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
              <h3 className="text-[10px] tracking-widest text-zinc-500 uppercase font-bold">
                Kaldıraç & Trend Sentezi (Coinanalys)
              </h3>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[9px] text-zinc-500 uppercase">Enstrüman:</span>
              <select
                value={selectedOiSymbol}
                onChange={(e) => setSelectedOiSymbol(e.target.value)}
                className="bg-zinc-900 border border-zinc-800 text-zinc-300 px-2 py-1 text-[10px] rounded focus:outline-none focus:border-indigo-500/50 cursor-pointer"
              >
                {fundingRates.map((fr) => (
                  <option key={fr.symbol} value={fr.symbol}>
                    {fr.symbol}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Leverage Trend Synthesis */}
          {oiData && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className={`md:col-span-1 border rounded-lg p-4 flex flex-col justify-center gap-1.5 ${trendColors[oiData.trend_color]}`}>
                <span className="text-[8px] uppercase tracking-wider opacity-60">Leverage Trend</span>
                <span className="text-xs font-black uppercase tracking-widest block leading-tight">
                  {oiData.trend.replace("_", " ")}
                </span>
                <p className="text-[9px] opacity-80 leading-normal">
                  {oiData.trend_description}
                </p>
              </div>

              {/* Mini Chart */}
              <div className="md:col-span-2 h-[120px] w-full border border-zinc-900 rounded-lg p-2 bg-zinc-950/20">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={oiData.history} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                    <defs>
                      <linearGradient id="colorOi" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#818cf8" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="timestamp"
                      tickFormatter={formatChartDate}
                      stroke="#3f3f46"
                      fontSize={8}
                      tickLine={false}
                    />
                    <Tooltip
                      labelFormatter={(t) => `Tarih: ${new Date(t).toLocaleTimeString()}`}
                      contentStyle={{ background: "#09090b", border: "1px solid #27272a", fontSize: "9px" }}
                      formatter={(val: any, name: string) => {
                        if (name === "open_interest") return [n(val, 2), "Open Interest"];
                        if (name === "price") return [`$${n(val, 2)}`, "Fiyat"];
                        return [val, name];
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="open_interest"
                      stroke="#818cf8"
                      strokeWidth={1.5}
                      fillOpacity={1}
                      fill="url(#colorOi)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-zinc-900 pt-3 text-[9px] text-zinc-600 leading-relaxed uppercase flex flex-wrap gap-x-4 gap-y-1">
          <span>🟢 Price Up + OI Up = LONG BUILDUP (Güçlü Alıcı)</span>
          <span>🔴 Price Down + OI Up = SHORT BUILDUP (Güçlü Satıcı)</span>
          <span>🟡 Price Up + OI Down = SHORT COVERING (Tepkisel Boğa)</span>
          <span>🔵 Price Down + OI Down = LONG LIQUIDATION (Tasfiye)</span>
        </div>
      </div>
    </div>
  );
}
