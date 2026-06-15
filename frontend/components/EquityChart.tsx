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
import { terminal } from "@efloud/tokens";

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
                  <stop offset="0%" stopColor={terminal.chart.bull} stopOpacity={0.32} />
                  <stop offset="100%" stopColor={terminal.chart.bull} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={terminal.chart.grid} strokeDasharray="0" vertical={false} />
              <XAxis
                dataKey="label"
                stroke={terminal.chart.axis}
                tick={{ fill: terminal.chart.axisText, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: terminal.chart.grid }}
              />
              <YAxis
                domain={["auto", "auto"]}
                stroke={terminal.chart.axis}
                tick={{ fill: terminal.chart.axisText, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: terminal.chart.grid }}
                width={56}
                tickFormatter={(v) => `$${n(Number(v), 0)}`}
              />
              <Tooltip
                cursor={{ stroke: terminal.chart.cursor, strokeWidth: 1 }}
                contentStyle={{
                  background: terminal.chart.tooltipBg,
                  border: `1px solid ${terminal.chart.grid}`,
                  fontFamily: "var(--font-geist-mono)",
                  fontSize: "11px",
                  letterSpacing: "0.04em",
                  padding: "8px 12px",
                }}
                labelStyle={{ color: terminal.text.secondary }}
                itemStyle={{ color: terminal.text.primary }}
                formatter={(v) => [usd(Number(v)), "Balance"]}
              />
              <Area
                type="monotone"
                dataKey="balance"
                stroke={terminal.chart.bull}
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
