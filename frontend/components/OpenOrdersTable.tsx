"use client";

import { useOrders } from "@/hooks/useOrders";
import { fromNow, n, priceDecimals } from "@/lib/format";
import type { OpenOrder } from "@/lib/api";

function formatType(t: string): string {
  switch (t) {
    case "take_profit_market":
      return "TP";
    case "stop_market":
      return "SL";
    case "limit":
      return "LIMIT";
    case "market":
      return "MKT";
    default:
      return t.toUpperCase();
  }
}

function priceFor(o: OpenOrder): number | null {
  // Stop/TP orders carry stopPrice; plain limit orders carry price.
  return o.stop_price ?? o.price;
}

function isoFromMs(ms: number | null): string | null {
  return ms ? new Date(ms).toISOString() : null;
}

export function OpenOrdersTable({ onSelectSymbol }: { onSelectSymbol?: (symbol: string) => void }) {
  const { data, isLoading } = useOrders();
  const rows = data ?? [];

  return (
    <div className="border border-border bg-bg-elevated">
      <div className="px-5 py-3 border-b border-border flex items-baseline justify-between">
        <div className="text-[10px] uppercase tracking-widest text-text-secondary font-mono">
          Open Orders
        </div>
        <div className="text-[11px] font-mono tabular-nums text-text-muted">
          {rows.length} pending
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px] font-mono tabular-nums">
          <thead className="border-b border-border">
            <tr className="text-text-muted uppercase tracking-widest text-[10px]">
              <th className="text-left px-5 py-2 font-normal">Symbol</th>
              <th className="text-left px-3 py-2 font-normal">Type</th>
              <th className="text-left px-3 py-2 font-normal">Side</th>
              <th className="text-right px-3 py-2 font-normal">Price</th>
              <th className="text-right px-3 py-2 font-normal">Amount</th>
              <th className="text-right px-3 py-2 font-normal">Filled</th>
              <th className="text-left px-3 py-2 font-normal">Flags</th>
              <th className="text-right px-5 py-2 font-normal">Age</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={8} className="px-5 py-6 text-center text-text-muted">loading…</td></tr>
            )}
            {!isLoading && rows.length === 0 && (
              <tr><td colSpan={8} className="px-5 py-6 text-center text-text-muted">no open orders</td></tr>
            )}
            {rows.map((o) => {
              const price = priceFor(o);
              const dec = price ? priceDecimals(price) : 2;
              const isBuy = o.side === "buy";
              const filledPct =
                o.amount && o.filled !== null && o.amount > 0
                  ? (o.filled / o.amount) * 100
                  : 0;
              return (
                <tr
                  key={o.id}
                  onClick={() => onSelectSymbol?.(o.symbol)}
                  className="border-b border-border hover:bg-bg-surface/80 active:bg-bg-surface/50 active:scale-[0.995] transition-all duration-150 ease-out animate-slideIn cursor-pointer"
                >
                  <td className="px-5 py-2.5 text-text-primary">{o.symbol}</td>
                  <td className="px-3 py-2.5">
                    <span className="text-[10px] tracking-widest text-text-secondary border border-border px-1.5 py-px">
                      {formatType(o.type)}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`text-[10px] tracking-widest ${isBuy ? "text-accent-green" : "text-accent-red"}`}>
                      {isBuy ? "▲ BUY" : "▼ SELL"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-text-primary">
                    {price !== null ? n(price, dec) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right text-text-secondary">
                    {o.amount !== null ? n(o.amount, 4) : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right text-text-secondary">
                    {filledPct > 0 ? `${n(filledPct, 1)}%` : "—"}
                  </td>
                  <td className="px-3 py-2.5">
                    {o.reduce_only && (
                      <span className="text-[9px] tracking-wider text-accent-green border border-accent-green/40 px-1 py-px">
                        REDUCE
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-2.5 text-right text-text-muted">
                    {fromNow(isoFromMs(o.timestamp))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
