"use client";
import useSWR from "swr";
import { jsonFetcher, type Trade } from "@/lib/api";

export function useHistory(limit = 50) {
  return useSWR<Trade[]>(`/api/history?limit=${limit}`, jsonFetcher, {
    refreshInterval: 15000,
    revalidateOnFocus: false,
  });
}
