// Number / time formatters — finance-grade tabular numerics.

const fmtCache = new Map<number, Intl.NumberFormat>();

export function n(value: number, decimals = 2): string {
  if (!isFinite(value)) return "—";
  let f = fmtCache.get(decimals);
  if (!f) {
    f = new Intl.NumberFormat("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    fmtCache.set(decimals, f);
  }
  return f.format(value);
}

export function pct(value: number, decimals = 2): string {
  if (!isFinite(value)) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${n(value, decimals)}%`;
}

export function usd(value: number, decimals = 2): string {
  if (!isFinite(value)) return "—";
  return `$${n(value, decimals)}`;
}

export function priceDecimals(price: number): number {
  // Smart decimals: BTC 95000 → 0, SOL 240 → 2, DOGE 0.45 → 4, SHIB 0.0001 → 6
  if (price === 0 || !isFinite(price)) return 2;
  const abs = Math.abs(price);
  if (abs >= 1000) return 1;
  if (abs >= 100) return 2;
  if (abs >= 1) return 3;
  if (abs >= 0.01) return 4;
  return 6;
}

export function fromNow(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const dt = (Date.now() - t) / 1000;
  if (dt < 1) return "now";
  if (dt < 60) return `${Math.floor(dt)}s ago`;
  if (dt < 3600) return `${Math.floor(dt / 60)}m ago`;
  if (dt < 86400) return `${Math.floor(dt / 3600)}h ago`;
  return `${Math.floor(dt / 86400)}d ago`;
}

export function shortTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

/**
 * CCXT/journal sembollerini Binance stream formuna indirger:
 * "FIL/USDT:USDT" → "FILUSDT", "BTC/USDT" → "BTCUSDT", "ETHUSDT" → "ETHUSDT".
 * NOT: `.replace(":", "")` kalıbı kontrat suffix'ini SİLMEZ ("FILUSDTUSDT"
 * üretir) — /api/orders sembolleri ccxt suffix'i taşıdığından eşleşme hep
 * boşa düşüyordu (2026-08-12 audit).
 */
export function normalizeSymbol(sym: string): string {
  return sym.split(":")[0].replace("/", "");
}
