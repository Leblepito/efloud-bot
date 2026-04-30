"use client";

import { useStatus } from "@/hooks/useStatus";
import { fromNow } from "@/lib/format";
import { StatusCard } from "./StatusCard";

export function StatusGrid() {
  const { data, isLoading } = useStatus();

  const breakerTone =
    data?.breaker_state === "OPEN" ? "good" :
    data?.breaker_state === "TRIPPED" ? "warn" :
    data?.breaker_state === "HALTED" ? "bad" : "neutral";

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px bg-border">
      <StatusCard
        label="Bot"
        tone={data?.running ? "good" : "bad"}
        value={isLoading ? "…" : data?.running ? "RUNNING" : "STOPPED"}
        pulse={data?.running}
      />
      <StatusCard
        label="Breaker"
        tone={breakerTone}
        value={data?.breaker_state ?? "—"}
      />
      <StatusCard
        label="Cycle"
        value={data ? `#${data.cycle_count}` : "—"}
        sub={data?.last_cycle_at ? `${fromNow(data.last_cycle_at)} • ${data.last_cycle_duration_ms}ms` : "—"}
      />
      <StatusCard
        label="Open Positions"
        value={data?.open_positions ?? 0}
        sub={data?.config_path}
      />
    </div>
  );
}
