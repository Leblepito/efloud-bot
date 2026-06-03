"use client";

import { useEffect, useState } from "react";
import { KillSwitch } from "./KillSwitch";
import { BotControl } from "./BotControl";
import { useStatus } from "@/hooks/useStatus";

/**
 * Unambiguous network-mode safety lock.
 * - TESTNET  → azure "TESTNET SANDBOX"
 * - MAINNET  → hard crimson "⚠ LIVE MAINNET" (pulsing dot)
 * - DRY-RUN  → amber "DRY-RUN · LOG ONLY"
 */
function NetworkBadges({ testnet, dryRun }: { testnet?: boolean; dryRun?: boolean }) {
  return (
    <div className="hidden md:flex items-center gap-2">
      {testnet ? (
        <span
          title="Orders route to the Binance Futures TESTNET — no real capital at risk."
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-blue-500/40 bg-blue-500/[0.06] font-mono text-[9px] font-semibold tracking-wider text-blue-400 uppercase"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
          Testnet Sandbox
        </span>
      ) : (
        <span
          title="LIVE PRODUCTION MAINNET — real capital is at risk."
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-accent-red/50 bg-accent-red/[0.08] font-mono text-[9px] font-bold tracking-wider text-accent-red uppercase"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-accent-red dot-breathe" />
          ⚠ Live Mainnet
        </span>
      )}
      {dryRun && (
        <span
          title="DRY-RUN: the engine logs intended orders but does not place them."
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-accent-amber/40 bg-accent-amber/[0.05] font-mono text-[9px] font-semibold tracking-wider text-accent-amber uppercase"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-accent-amber" />
          Dry-Run · Log Only
        </span>
      )}
    </div>
  );
}

/**
 * Connection-state chip driven by the /api/status SWR poll (no extra socket).
 *   data + no error → SYNCED (green) · error → OFFLINE (red) · first load → CONNECTING (amber)
 */
function SyncIndicator() {
  const { data, error, isLoading } = useStatus();
  const state: "synced" | "connecting" | "offline" = error
    ? "offline"
    : isLoading && !data
    ? "connecting"
    : "synced";

  const cfg = {
    synced:     { cls: "border-accent-green/30 text-accent-green", dot: "bg-accent-green dot-breathe", label: "SYNCED", title: "Telemetry stream OPEN · polling /api/status every 5s" },
    connecting: { cls: "border-accent-amber/30 text-accent-amber", dot: "bg-accent-amber animate-spin rounded-[1px]", label: "CONNECTING", title: "Connecting to telemetry…" },
    offline:    { cls: "border-accent-red/30 text-accent-red",     dot: "bg-accent-red", label: "OFFLINE", title: "Telemetry unreachable" },
  }[state];

  return (
    <span
      role="status"
      aria-label={`Connection ${cfg.label}`}
      title={cfg.title}
      className={`inline-flex items-center gap-2 h-9 px-3 rounded-md border bg-transparent font-mono text-[10px] font-semibold tracking-wider ${cfg.cls}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      <span className="hidden sm:inline">{cfg.label}</span>
    </span>
  );
}

export function TopBar() {
  const { data } = useStatus();
  const [isDemo, setIsDemo] = useState(false);

  useEffect(() => {
    setIsDemo(localStorage.getItem("efloud_demo_mode") === "true");
  }, []);

  const handleSwitchToLive = () => {
    localStorage.removeItem("efloud_demo_mode");
    localStorage.removeItem("efloud_mock_state");
    window.location.href = "/login";
  };

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-bg/85 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-6 h-14 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <div className="font-mono text-[11px] tracking-[0.32em] text-text-primary whitespace-nowrap">
            <span className="text-accent-green">E</span> F L O U D
          </div>
          <span className="hidden lg:inline text-[10px] font-mono tracking-widest text-text-muted">
            v2.2
          </span>
          <NetworkBadges testnet={data?.testnet} dryRun={data?.dry_run} />
          {isDemo && (
            <button
              onClick={handleSwitchToLive}
              aria-label="Demo mode active — click to switch to live login"
              title="Click to switch to the live login console"
              className="
                px-2 py-1 rounded border border-accent-amber/30 bg-transparent
                font-mono text-[9px] tracking-wider text-accent-amber hover:bg-accent-amber/10
                transition-colors duration-150 flex items-center gap-1.5 active:scale-[0.97] whitespace-nowrap
              "
            >
              <span className="w-1.5 h-1.5 rounded-full bg-accent-amber dot-breathe" />
              DEMO MODE
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <SyncIndicator />
          <BotControl />
          <KillSwitch />
        </div>
      </div>
    </header>
  );
}
