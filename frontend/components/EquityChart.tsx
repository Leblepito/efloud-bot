"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useEquity } from "@/hooks/useEquity";
import { n, shortDate, usd } from "@/lib/format";

export function EquityChart() {
  const { data } = useEquity(7);
  const points = (data ?? []).map((p) => ({
    ts: p.ts,
    label: shortDate(p.ts),
    balance: p.balance,
  }));
  const last = points[points.length - 1]?.balance;
  const first = points[0]?.balance;
  const delta = last != null && first != null ? last - first : 0;
  const deltaPct = first ? (delta / first) * 100 : 0;
  const positive = delta >= 0;

  return (
    <div className="border border-border bg-bg-elevated p-6">
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-text-secondary font-mono mb-2">
            Equity — 7 Days
          </div>
          <div className="font-mono text-3xl tabular-nums text-text-primary">
            {last != null ? usd(last) : "—"}
          </div>
        </div>
        <div className={`font-mono text-sm tabular-nums ${positive ? "text-accent-green" : "text-accent-red"}`}>
          {positive ? "▲" : "▼"} {usd(Math.abs(delta))} ({n(deltaPct, 2)}%)
        </div>
      </div>
      <div className="h-56">
        {points.length === 0 ? (
          <div className="h-full flex items-center justify-center text-text-muted text-xs font-mono">
            no data yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00FF88" stopOpacity={0.32} />
                  <stop offset="100%" stopColor="#00FF88" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1F1F1F" strokeDasharray="0" vertical={false} />
              <XAxis
                dataKey="label"
                stroke="#444"
                tick={{ fill: "#666", fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: "#1F1F1F" }}
              />
              <YAxis
                domain={["auto", "auto"]}
                stroke="#444"
                tick={{ fill: "#666", fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: "#1F1F1F" }}
                width={56}
                tickFormatter={(v) => `$${n(Number(v), 0)}`}
              />
              <Tooltip
                cursor={{ stroke: "#2A2A2A", strokeWidth: 1 }}
                contentStyle={{
                  background: "#0A0A0A",
                  border: "1px solid #1F1F1F",
                  fontFamily: "var(--font-geist-mono)",
                  fontSize: "11px",
                  letterSpacing: "0.04em",
                  padding: "8px 12px",
                }}
                labelStyle={{ color: "#888" }}
                itemStyle={{ color: "#FAFAFA" }}
                formatter={(v) => [usd(Number(v)), "Balance"]}
              />
              <Area
                type="monotone"
                dataKey="balance"
                stroke="#00FF88"
                strokeWidth={1.5}
                fill="url(#equityFill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
