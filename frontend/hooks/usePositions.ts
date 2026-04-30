"use client";
import useSWR from "swr";
import { jsonFetcher, type OpenPosition } from "@/lib/api";

export function usePositions() {
  return useSWR<OpenPosition[]>("/api/positions", jsonFetcher, {
    refreshInterval: 4000,
    revalidateOnFocus: false,
  });
}
