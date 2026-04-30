"use client";
import useSWR from "swr";
import { jsonFetcher, type Status } from "@/lib/api";

export function useStatus() {
  return useSWR<Status>("/api/status", jsonFetcher, {
    refreshInterval: 5000,
    revalidateOnFocus: false,
  });
}
