// API types and fetcher.

export type Status = {
  running: boolean;
  cycle_count: number;
  last_cycle_at: string | null;
  last_cycle_duration_ms: number;
  breaker_state: "OPEN" | "TRIPPED" | "HALTED" | "UNKNOWN";
  open_positions: number;
  config_path: string;
  testnet: boolean;
  dry_run: boolean;
  last_error: string | null;
};

export type OpenPosition = {
  symbol: string;
  direction: "LONG" | "SHORT";
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  size: number;
  current_price: number;
  unrealized_pct: number;
  tp1_hit: boolean;
  opened_at: string;
};

export type Trade = {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  entry: number;
  exit: number | null;
  sl: number;
  tp1: number;
  tp2: number;
  size: number;
  pnl_usdt: number | null;
  pnl_pct: number | null;
  reason: string | null;
  opened_at: string;
  closed_at: string | null;
  confluence: number | null;
};

export type EquityPoint = {
  ts: string;
  balance: number;
  open_positions_count: number;
};

export type ConfigSnapshot = {
  config_path: string;
  exchange: { testnet: boolean; leverage: number; margin_mode: string; market_type: string };
  operation: { dry_run: boolean; check_interval_sec: number };
  risk: Record<string, unknown>;
  safety: Record<string, unknown>;
  symbols: string[];
};

export async function jsonFetcher<T>(url: string): Promise<T> {
  const r = await fetch(url, { credentials: "include" });
  if (r.status === 401) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("unauthorized");
  }
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as T;
}

export async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => "");
    throw new Error(`HTTP ${r.status}: ${txt}`);
  }
  return (await r.json()) as T;
}
