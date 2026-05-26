"use client";

import React, { useEffect, useState } from "react";
import { fromNow } from "@/lib/format";

interface SentimentData {
  last_updated: string;
  macro_sentiment: "RISK_ON" | "RISK_OFF" | "NEUTRAL";
  confidence_score: number;
  fear_and_greed: number;
  bitcoin_trend: string;
  reasoning: string;
}

export function AISentimentCard() {
  const [data, setData] = useState<SentimentData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    fetch("/api/ai/sentiment", { credentials: "include" })
      .then((res) => {
        if (res.status === 401) {
          setError("Unauthorized");
          return null;
        }
        return res.json();
      })
      .then((data) => {
        if (data) {
          setData(data);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Connection error");
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="border border-zinc-800 bg-zinc-950/40 p-5 rounded-xl animate-pulse text-zinc-500 font-mono text-xs">
        AI Duygu Durumu Yükleniyor...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="border border-rose-950/50 bg-rose-950/10 p-5 rounded-xl text-rose-400 font-mono text-xs">
        ⚠️ AI Duygu Durumu Yüklenemedi: {error || "Veri bulunamadı"}
      </div>
    );
  }

  const sentimentTones = {
    RISK_ON: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
    RISK_OFF: "text-rose-400 border-rose-500/20 bg-rose-500/5",
    NEUTRAL: "text-zinc-400 border-zinc-500/20 bg-zinc-500/5",
  };

  return (
    <div className="border border-zinc-800 bg-zinc-950/30 p-5 rounded-xl hover:border-zinc-700 transition-all duration-300 relative font-mono">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
          <h3 className="text-[10px] tracking-widest text-zinc-500 uppercase font-bold">
            Gemini AI Makro Duygu Durumu
          </h3>
        </div>
        <span className={`px-2.5 py-0.5 rounded border text-[10px] font-bold tracking-widest ${sentimentTones[data.macro_sentiment]}`}>
          {data.macro_sentiment}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4 text-xs">
        <div>
          <span className="text-[9px] uppercase tracking-wider text-zinc-500 block">Fear & Greed</span>
          <span className="text-zinc-200 font-bold text-sm">{data.fear_and_greed}</span>
        </div>
        <div>
          <span className="text-[9px] uppercase tracking-wider text-zinc-500 block">BTC Trend</span>
          <span className="text-indigo-400 font-bold text-sm">{data.bitcoin_trend}</span>
        </div>
        <div>
          <span className="text-[9px] uppercase tracking-wider text-zinc-500 block">Güven Oranı</span>
          <span className="text-zinc-200 font-bold text-sm">%{Math.round(data.confidence_score * 100)}</span>
        </div>
        <div>
          <span className="text-[9px] uppercase tracking-wider text-zinc-500 block">Son Güncelleme</span>
          <span className="text-zinc-400 text-[10px] block mt-1">{fromNow(data.last_updated)}</span>
        </div>
      </div>

      <div className="border-t border-zinc-800/60 pt-3">
        <span className="text-[9px] uppercase tracking-wider text-zinc-500 block mb-1">Gerekçe & Analiz Raporu</span>
        <p className="text-xs text-zinc-400 italic leading-relaxed">
          "{data.reasoning}"
        </p>
      </div>
    </div>
  );
}
