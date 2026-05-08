"use client";
import useSWR from "swr";
import { jsonFetcher, type OpenOrder } from "@/lib/api";

export function useOrders() {
  return useSWR<OpenOrder[]>("/api/orders", jsonFetcher, {
    refreshInterval: 4000,
    revalidateOnFocus: false,
  });
}
