"use client";

import { useState } from "react";
import { mutate } from "swr";
import { useWebSocket, type WsEvent } from "@/hooks/useWebSocket";

/**
 * Invisible component: subscribes to /ws and re-fetches relevant SWR keys on events.
 * Also drives the "cycle heartbeat" indicator pulse via a small fixed-position dot.
 */
export function LiveSync() {
  const [pulseKey, setPulseKey] = useState(0);
  const [lastEvent, setLastEvent] = useState<string | null>(null);

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
  });

  return (
    <div
      aria-hidden
      className="fixed bottom-4 right-4 flex items-center gap-2 pointer-events-none select-none"
    >
      <span
        key={pulseKey}
        className="inline-block w-1.5 h-1.5 bg-accent-green animate-ringExpand"
      />
      <span className="text-[10px] font-mono tracking-widest text-text-muted">
        WS {lastEvent ?? "…"}
      </span>
    </div>
  );
}
