"use client";
import useSWR from "swr";
import { jsonFetcher, type ConfigSnapshot } from "@/lib/api";

export function useConfig() {
  return useSWR<ConfigSnapshot>("/api/config", jsonFetcher, {
    revalidateOnFocus: false,
  });
}
