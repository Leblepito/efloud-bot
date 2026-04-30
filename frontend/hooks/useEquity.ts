"use client";
import useSWR from "swr";
import { jsonFetcher, type EquityPoint } from "@/lib/api";

export function useEquity(days = 7) {
  return useSWR<EquityPoint[]>(`/api/equity?days=${days}`, jsonFetcher, {
    refreshInterval: 60000,
    revalidateOnFocus: false,
  });
}
