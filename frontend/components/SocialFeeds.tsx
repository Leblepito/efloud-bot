"use client";

import React, { useEffect, useState } from "react";
import { fromNow } from "@/lib/format";

interface FeedItem {
  id: string;
  source: "twitter" | "telegram";
  author: string;
  content: string;
  timestamp: string;
}

interface SocialFeedResponse {
  telegram: FeedItem[];
  twitter: FeedItem[];
}

export function SocialFeeds() {
  const [activeTab, setActiveTab] = useState<"telegram" | "twitter">("telegram");
  const [data, setData] = useState<SocialFeedResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/social/feeds", { credentials: "include" })
      .then((res) => {
        if (res.status === 401) {
          setError("Unauthorized");
          return null;
        }
        return res.json();
      })
      .then((resData) => {
        if (resData) {
          setData(resData);
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
      <div className="border border-zinc-800 bg-zinc-950/40 p-6 rounded-xl animate-pulse text-zinc-500 font-mono text-xs">
        Sosyal Medya Akışları Yükleniyor...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="border border-rose-950/50 bg-rose-950/10 p-6 rounded-xl text-rose-400 font-mono text-xs">
        ⚠️ Sosyal akışlar yüklenemedi: {error || "Veri bulunamadı"}
      </div>
    );
  }

  const items = activeTab === "telegram" ? data.telegram : data.twitter;

  return (
    <div className="border border-zinc-800 bg-zinc-950/30 rounded-xl overflow-hidden font-mono hover:border-zinc-700 transition-all duration-300">
      {/* Header & Tabs */}
      <div className="px-5 py-4 border-b border-zinc-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-zinc-950/45">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <h3 className="text-[10px] tracking-widest text-zinc-500 uppercase font-bold">
            Efloud Topluluk Akışları & TA Analizleri
          </h3>
        </div>

        {/* Tab Buttons */}
        <div className="flex bg-zinc-900 border border-zinc-800 p-0.5 rounded-md">
          <button
            onClick={() => setActiveTab("telegram")}
            className={`px-3 py-1 text-[10px] tracking-wider font-bold rounded transition-all duration-200 ${
              activeTab === "telegram"
                ? "bg-cyan-500/10 text-cyan-400 font-bold"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            ✈️ TELEGRAM
          </button>
          <button
            onClick={() => setActiveTab("twitter")}
            className={`px-3 py-1 text-[10px] tracking-wider font-bold rounded transition-all duration-200 ${
              activeTab === "twitter"
                ? "bg-cyan-500/10 text-cyan-400 font-bold"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            𝕏 TWITTER
          </button>
        </div>
      </div>

      {/* Feed List */}
      <div className="divide-y divide-zinc-900 max-h-[350px] overflow-y-auto custom-scrollbar">
        {items.length === 0 && (
          <div className="p-6 text-center text-zinc-600 text-xs">
            Henüz gönderi bulunmuyor.
          </div>
        )}
        {items.map((item) => (
          <div
            key={item.id}
            className="p-5 hover:bg-zinc-900/20 transition-all duration-200 flex flex-col gap-2"
          >
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-xs font-bold text-zinc-200 flex items-center gap-1.5">
                {item.source === "telegram" ? (
                  <span className="text-cyan-400">✈️</span>
                ) : (
                  <span className="text-zinc-400">𝕏</span>
                )}
                {item.author}
              </span>
              <span className="text-[9px] text-zinc-500">{fromNow(item.timestamp)}</span>
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap">
              {item.content}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
