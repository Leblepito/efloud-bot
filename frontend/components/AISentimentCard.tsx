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
      <div className="border border-border bg-bg-elevated p-5 animate-pulse text-text-muted font-mono text-xs">
        AI Duygu Durumu Yükleniyor...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="border border-accent-red/30 bg-accent-red/5 p-5 text-accent-red font-mono text-xs">
        AI Duygu Durumu Yüklenemedi: {error || "Veri bulunamadı"}
      </div>
    );
  }

  const sentimentTones: Record<SentimentData["macro_sentiment"], string> = {
    RISK_ON: "text-accent-green border-accent-green/30",
    RISK_OFF: "text-accent-red border-accent-red/30",
    NEUTRAL: "text-text-muted border-border",
  };
  const leftAccent: Record<SentimentData["macro_sentiment"], string> = {
    RISK_ON: "border-l-2 border-l-accent-green",
    RISK_OFF: "border-l-2 border-l-accent-red",
    NEUTRAL: "border-l-2 border-l-border-strong",
  };

  return (
    <div
      className={`border border-border bg-bg-elevated p-5 hover:border-border-strong transition-colors duration-200 font-mono ${leftAccent[data.macro_sentiment]}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dot-breathe" />
          <h3 className="text-[10px] tracking-widest text-text-secondary uppercase font-bold">
            Gemini AI Makro Duygu Durumu
          </h3>
        </div>
        <span className={`px-2.5 py-0.5 border text-[10px] font-bold tracking-widest ${sentimentTones[data.macro_sentiment]}`}>
          {data.macro_sentiment}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4 text-xs">
        <div>
          <span className="text-[9px] uppercase tracking-wider text-text-muted block">Fear &amp; Greed</span>
          <span className="text-text-primary font-bold text-sm tabular-nums">{data.fear_and_greed}</span>
        </div>
        <div>
          <span className="text-[9px] uppercase tracking-wider text-text-muted block">BTC Trend</span>
          <span className="text-blue-400 font-bold text-sm">{data.bitcoin_trend}</span>
        </div>
        <div>
          <span className="text-[9px] uppercase tracking-wider text-text-muted block">Güven Oranı</span>
          <span className="text-text-primary font-bold text-sm tabular-nums">%{Math.round(data.confidence_score * 100)}</span>
        </div>
        <div>
          <span className="text-[9px] uppercase tracking-wider text-text-muted block">Son Güncelleme</span>
          <span className="text-text-secondary text-[10px] block mt-1">{fromNow(data.last_updated)}</span>
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <span className="text-[9px] uppercase tracking-wider text-text-muted block mb-1">Gerekçe &amp; Analiz Raporu</span>
        <p className="text-xs text-text-secondary leading-relaxed">
          {data.reasoning}
        </p>
      </div>
    </div>
  );
}
