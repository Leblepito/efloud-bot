"use client";

import { KillSwitch } from "./KillSwitch";
import { useStatus } from "@/hooks/useStatus";

export function TopBar() {
  const { data } = useStatus();
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-bg/95 backdrop-blur-sm">
      <div className="mx-auto max-w-7xl px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="font-mono text-[11px] tracking-[0.32em] text-text-primary">
            E F L O U D
          </div>
          <span className="text-[10px] font-mono tracking-widest text-text-muted">
            v2.2 ▪ {data?.testnet ? "TESTNET" : "MAINNET"} ▪ {data?.dry_run ? "DRY-RUN" : "LIVE"}
          </span>
        </div>
        <KillSwitch />
      </div>
    </header>
  );
}
