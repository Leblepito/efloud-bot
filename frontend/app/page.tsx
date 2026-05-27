"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { StatusGrid } from "@/components/StatusGrid";
import { AISentimentCard } from "@/components/AISentimentCard";
import { EquityChart } from "@/components/EquityChart";
import { InteractiveChart } from "@/components/InteractiveChart";
import { PositionsTable } from "@/components/PositionsTable";
import { OpenOrdersTable } from "@/components/OpenOrdersTable";
import { TradesTable } from "@/components/TradesTable";
import { ConfigPanel } from "@/components/ConfigPanel";
import { LiveSync } from "@/components/LiveSync";
import { TradeDetailPanel } from "@/components/TradeDetailPanel";
import { SocialFeeds } from "@/components/SocialFeeds";
import { MarketIndicators } from "@/components/MarketIndicators";

export default function Dashboard() {
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSDT");
  const [selectedTrade, setSelectedTrade] = useState<any>(null);

  // Cookie tek domain'de (rewrites /api proxy üzerinden) — auth gate /api/status'un
  // 401 dönüşünden geliyor; jsonFetcher yönlendiriyor /login'e.
  useEffect(() => {
    fetch("/api/status", { credentials: "include" }).then((r) => {
      if (r.status === 401) window.location.href = "/login";
    });
  }, []);

  return (
    <div className="min-h-dvh">
      <TopBar />
      <main className="mx-auto max-w-7xl px-6 py-8 space-y-6">
        <section>
          <StatusGrid />
        </section>
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <AISentimentCard />
          <SocialFeeds />
        </section>
        <section>
          <MarketIndicators />
        </section>
        <section>
          <InteractiveChart
            selectedSymbol={selectedSymbol}
            selectedTrade={selectedTrade}
            onSelectSymbol={setSelectedSymbol}
          />
        </section>
        <section>
          <EquityChart />
        </section>
        <section>
          <PositionsTable onSelectSymbol={setSelectedSymbol} />
        </section>
        <section>
          <OpenOrdersTable onSelectSymbol={setSelectedSymbol} />
        </section>
        <section>
          <TradesTable onSelectTrade={setSelectedTrade} />
        </section>
        <section>
          <ConfigPanel />
        </section>
        <footer className="pt-8 pb-12 text-[10px] tracking-widest font-mono text-text-muted text-center uppercase">
          Efloud SMC Bot v2.2 ▪ Not financial advice ▪ DYOR
        </footer>
      </main>
      <LiveSync />
      <TradeDetailPanel trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  );
}
