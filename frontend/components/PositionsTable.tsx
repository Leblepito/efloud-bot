"use client";

import { usePositions } from "@/hooks/usePositions";
import { fromNow, n, pct, priceDecimals } from "@/lib/format";

export function PositionsTable({ onSelectSymbol }: { onSelectSymbol?: (symbol: string) => void }) {
  const { data, isLoading } = usePositions();
  const rows = data ?? [];

  return (
    <div className="border border-border bg-bg-elevated">
      <div className="px-5 py-3 border-b border-border flex items-baseline justify-between">
        <div className="text-[10px] uppercase tracking-widest text-text-secondary font-mono">
          Open Positions
        </div>
        <div className="text-[11px] font-mono tabular-nums text-text-muted">
          {rows.length} open
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px] font-mono tabular-nums">
          <thead className="border-b border-border">
            <tr className="text-text-muted uppercase tracking-widest text-[10px]">
              <th className="text-left px-5 py-2 font-normal">Symbol</th>
              <th className="text-left px-3 py-2 font-normal">Side</th>
              <th className="text-right px-3 py-2 font-normal">Entry</th>
              <th className="text-right px-3 py-2 font-normal">Mark</th>
              <th className="text-right px-3 py-2 font-normal">SL</th>
              <th className="text-right px-3 py-2 font-normal">TP1</th>
              <th className="text-right px-3 py-2 font-normal">TP2</th>
              <th className="text-right px-3 py-2 font-normal">Size</th>
              <th className="text-right px-3 py-2 font-normal">PnL</th>
              <th className="text-right px-5 py-2 font-normal">Age</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={10} className="px-5 py-6 text-center text-text-muted">loading…</td></tr>
            )}
            {!isLoading && rows.length === 0 && (
              <tr><td colSpan={10} className="px-5 py-6 text-center text-text-muted">no open positions</td></tr>
            )}
            {rows.map((p) => {
              const dec = priceDecimals(p.entry);
              const isLong = p.direction === "LONG";
              const profit = p.unrealized_pct >= 0;
              return (
                <tr
                  key={p.symbol}
                  onClick={() => onSelectSymbol?.(p.symbol)}
                  className="border-b border-border hover:bg-bg-surface transition-colors animate-slideIn cursor-pointer"
                >
                  <td className="px-5 py-2.5 text-text-primary">
                    {p.symbol}
                    {p.tp1_hit && (
                      <span className="ml-2 text-[9px] tracking-wider text-accent-green border border-accent-green/40 px-1 py-px">
                        TP1
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`text-[10px] tracking-widest ${isLong ? "text-accent-green" : "text-accent-red"}`}>
                      {isLong ? "▲ LONG" : "▼ SHORT"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-text-primary">{n(p.entry, dec)}</td>
                  <td className="px-3 py-2.5 text-right text-text-primary">{n(p.current_price, dec)}</td>
                  <td className="px-3 py-2.5 text-right text-text-secondary">{n(p.sl, dec)}</td>
                  <td className="px-3 py-2.5 text-right text-text-secondary">{n(p.tp1, dec)}</td>
                  <td className="px-3 py-2.5 text-right text-text-secondary">{n(p.tp2, dec)}</td>
                  <td className="px-3 py-2.5 text-right text-text-secondary">{n(p.size, 4)}</td>
                  <td className={`px-3 py-2.5 text-right ${profit ? "text-accent-green" : "text-accent-red"}`}>
                    {pct(p.unrealized_pct)}
                  </td>
                  <td className="px-5 py-2.5 text-right text-text-muted">{fromNow(p.opened_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
