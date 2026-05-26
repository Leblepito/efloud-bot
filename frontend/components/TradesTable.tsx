"use client";

import { useHistory } from "@/hooks/useHistory";
import { fromNow, n, pct, priceDecimals, usd } from "@/lib/format";

const reasonStyle: Record<string, string> = {
  TP1: "text-accent-green border-accent-green/40",
  TP2: "text-accent-green border-accent-green/40",
  SL: "text-accent-red border-accent-red/40",
  SL_POLL: "text-accent-red border-accent-red/40",
  TP2_POLL: "text-accent-green border-accent-green/40",
  KILL_SWITCH: "text-accent-amber border-accent-amber/40",
  RECONCILED: "text-text-secondary border-border-strong",
};

export function TradesTable({ onSelectTrade }: { onSelectTrade?: (trade: any) => void }) {
  const { data, isLoading } = useHistory(50);
  const rows = data ?? [];
  const total = rows.reduce((acc, t) => acc + (t.pnl_usdt ?? 0), 0);
  const wins = rows.filter((t) => (t.pnl_usdt ?? 0) > 0).length;
  const losses = rows.filter((t) => (t.pnl_usdt ?? 0) < 0).length;

  return (
    <div className="border border-border bg-bg-elevated">
      <div className="px-5 py-3 border-b border-border flex flex-wrap items-baseline justify-between gap-3">
        <div className="text-[10px] uppercase tracking-widest text-text-secondary font-mono">
          Recent Trades
        </div>
        <div className="text-[11px] font-mono tabular-nums text-text-muted flex gap-6">
          <span>
            <span className="text-accent-green">{wins}W</span>
            {" / "}
            <span className="text-accent-red">{losses}L</span>
          </span>
          <span className={total >= 0 ? "text-accent-green" : "text-accent-red"}>
            net {usd(total)}
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px] font-mono tabular-nums">
          <thead className="border-b border-border">
            <tr className="text-text-muted uppercase tracking-widest text-[10px]">
              <th className="text-left px-5 py-2 font-normal">Symbol</th>
              <th className="text-left px-3 py-2 font-normal">Side</th>
              <th className="text-right px-3 py-2 font-normal">Entry</th>
              <th className="text-right px-3 py-2 font-normal">Exit</th>
              <th className="text-right px-3 py-2 font-normal">PnL</th>
              <th className="text-left px-3 py-2 font-normal">Reason</th>
              <th className="text-right px-5 py-2 font-normal">Closed</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={7} className="px-5 py-6 text-center text-text-muted">loading…</td></tr>
            )}
            {!isLoading && rows.length === 0 && (
              <tr><td colSpan={7} className="px-5 py-6 text-center text-text-muted">no trades yet</td></tr>
            )}
            {rows.map((t) => {
              const dec = priceDecimals(t.entry);
              const isLong = t.direction === "LONG";
              const pnl = t.pnl_usdt ?? 0;
              const profit = pnl >= 0;
              const badgeCls = reasonStyle[t.reason ?? ""] ?? "text-text-muted border-border";
              return (
                <tr
                  key={t.id}
                  onClick={() => onSelectTrade?.(t)}
                  className="border-b border-border hover:bg-bg-surface transition-colors cursor-pointer"
                >
                  <td className="px-5 py-2 text-text-primary">{t.symbol}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] tracking-widest ${isLong ? "text-accent-green" : "text-accent-red"}`}>
                      {isLong ? "▲" : "▼"} {t.direction}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-text-primary">{n(t.entry, dec)}</td>
                  <td className="px-3 py-2 text-right text-text-primary">
                    {t.exit != null ? n(t.exit, dec) : "—"}
                  </td>
                  <td className={`px-3 py-2 text-right ${profit ? "text-accent-green" : "text-accent-red"}`}>
                    {usd(pnl)}{" "}
                    <span className="text-text-muted">
                      {t.pnl_pct != null ? `(${pct(t.pnl_pct)})` : ""}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {t.reason ? (
                      <span className={`text-[10px] tracking-wider px-1.5 py-0.5 border ${badgeCls}`}>
                        {t.reason}
                      </span>
                    ) : (
                      <span className="text-text-muted">—</span>
                    )}
                  </td>
                  <td className="px-5 py-2 text-right text-text-muted">{fromNow(t.closed_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
