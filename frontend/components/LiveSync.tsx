"use client";

import { useState } from "react";
import { mutate } from "swr";
import { useWebSocket, type WsEvent } from "@/hooks/useWebSocket";

/**
 * Subscribes to /ws, re-fetches relevant SWR keys on events, and renders a
 * fixed bottom-right heartbeat pill showing live connection state.
 *  - OPEN          → green dot, "WS · <last_event>", ring pulse on each cycle
 *  - RECONNECTING  → amber dot, socket actually closed
 *
 * Durum GERÇEK soket state'inden gelir (useWebSocket onStatus). Eski 20s
 * paket-bekleme sezgisi prod'da 30s cycle aralığıyla her cycle'da ve bot
 * durdurulduğunda kalıcı olarak sahte "reconnecting" gösteriyordu
 * (2026-08-12 audit).
 */
export function LiveSync() {
  const [pulseKey, setPulseKey] = useState(0);
  const [lastEvent, setLastEvent] = useState<string>("idle");
  const [wsOpen, setWsOpen] = useState(true);

  useWebSocket((evt: WsEvent) => {
    setLastEvent(evt.type);
    switch (evt.type) {
      case "cycle_start":
      case "cycle_end":
        setPulseKey((k) => k + 1);
        mutate("/api/status");
        break;
      case "position_opened":
      case "position_closed":
      case "tp1_hit":
        mutate("/api/positions");
        mutate("/api/history?limit=50");
        mutate("/api/status");
        break;
      case "breaker_change":
      case "bot_started":
      case "bot_stopped":
      case "error":
        mutate("/api/status");
        break;
    }
  }, setWsOpen);

  const open = wsOpen;
  const dotCls = open ? "bg-accent-green" : "bg-accent-amber";
  const txtCls = open ? "text-text-muted" : "text-accent-amber";

  return (
    <div
      aria-live="polite"
      className="
        fixed bottom-4 right-4 z-[35] flex items-center gap-2 px-3 py-1.5
        rounded-full border border-border-strong bg-bg-elevated/90 backdrop-blur-md
        pointer-events-none select-none
      "
    >
      <span key={pulseKey} className={`inline-block w-1.5 h-1.5 rounded-full ${dotCls} ws-beat`} />
      <span className={`text-[10px] font-mono tracking-widest uppercase ${txtCls}`}>
        {open ? `WS · ${lastEvent}` : "WS · reconnecting"}
      </span>
    </div>
  );
}
