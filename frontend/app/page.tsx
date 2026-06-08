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
import { SocialLearningCenter } from "@/components/SocialLearningCenter";
import { TabNav, type TabKey } from "@/components/TabNav";

export default function Dashboard() {
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSDT");
  const [selectedTrade, setSelectedTrade] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  // Selecting a trade (from TradesTable on the Positions tab) jumps the chart on
  // Overview — switch there so the user sees it.
  useEffect(() => {
    if (selectedTrade) setActiveTab("overview");
  }, [selectedTrade]);

  // Cookie tek domain'de (rewrites /api proxy üzerinden) — auth gate /api/status'un
  // 401 dönüşünden geliyor; jsonFetcher yönlendiriyor /login'e.
  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem("efloud_demo_mode") === "true") {
      return;
    }
    fetch("/api/status", { credentials: "include" }).then((r) => {
      if (r.status === 401) window.location.href = "/login";
    });
  }, []);

  return (
    <div className="min-h-dvh">
      <TopBar />
      <TabNav active={activeTab} onChange={setActiveTab} />
      <main className="mx-auto max-w-7xl px-6 py-8">
        {/* Panels are kept mounted (CSS-hidden when inactive) so the live chart's
            WebSocket and the selectedSymbol/selectedTrade cross-links survive tab switches. */}
        <div className={activeTab === "overview" ? "space-y-6" : "hidden"}>
          <section>
            <StatusGrid />
          </section>
          <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <AISentimentCard />
            <SocialFeeds />
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
        </div>

        <div className={activeTab === "positions" ? "space-y-6" : "hidden"}>
          <section>
            <PositionsTable onSelectSymbol={setSelectedSymbol} selectedSymbol={selectedSymbol} />
          </section>
          <section>
            <OpenOrdersTable onSelectSymbol={setSelectedSymbol} />
          </section>
          <section>
            <TradesTable onSelectTrade={setSelectedTrade} selectedId={selectedTrade?.id} />
          </section>
        </div>

        <div className={activeTab === "research" ? "space-y-6" : "hidden"}>
          <section>
            <SocialLearningCenter />
          </section>
          <section>
            <MarketIndicators />
          </section>
        </div>

        <div className={activeTab === "config" ? "space-y-6" : "hidden"}>
          <section>
            <ConfigPanel />
          </section>
        </div>

        <footer className="pt-8 pb-12 text-[10px] tracking-widest font-mono text-text-muted text-center uppercase">
          Efloud SMC Bot v2.2 ▪ Not financial advice ▪ DYOR
        </footer>
      </main>
      <LiveSync />
      <TradeDetailPanel trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  );
}
