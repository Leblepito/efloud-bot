"use client";

import { useEffect } from "react";
import { TopBar } from "@/components/TopBar";
import { StatusGrid } from "@/components/StatusGrid";
import { EquityChart } from "@/components/EquityChart";
import { PositionsTable } from "@/components/PositionsTable";
import { TradesTable } from "@/components/TradesTable";
import { ConfigPanel } from "@/components/ConfigPanel";
import { LiveSync } from "@/components/LiveSync";

export default function Dashboard() {
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
        <section>
          <EquityChart />
        </section>
        <section>
          <PositionsTable />
        </section>
        <section>
          <TradesTable />
        </section>
        <section>
          <ConfigPanel />
        </section>
        <footer className="pt-8 pb-12 text-[10px] tracking-widest font-mono text-text-muted text-center uppercase">
          Efloud SMC Bot v2.2 ▪ Not financial advice ▪ DYOR
        </footer>
      </main>
      <LiveSync />
    </div>
  );
}
