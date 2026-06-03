"use client";

import useSWR from "swr";
import { jsonFetcher } from "@/lib/api";
import type { SmcData } from "@/components/smcOverlay";

export type SmcSignal = SmcData & { symbol: string; timeframe: string; source: "engine" | "heuristic" | "unavailable" };

/**
 * Calculated SMC structure from the backend (`/api/signals/smc`).
 * Backend prefers live engine output and falls back to its own heuristic, so a
 * non-null payload is safe to feed straight into `new SmcOverlayPrimitive(data)`.
 * Pass `enabled=false` (e.g. when the SMC overlay toggle is off) to skip polling.
 */
export function useSmcSignals(symbol: string, timeframe: string, enabled = true) {
  return useSWR<SmcSignal>(
    enabled ? `/api/signals/smc?symbol=${symbol}&timeframe=${timeframe}` : null,
    jsonFetcher,
    {
      refreshInterval: 30000,
      revalidateOnFocus: false,
      keepPreviousData: true,
    }
  );
}
