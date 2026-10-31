"use client";

import { useEffect, useRef, useState } from "react";
import { Users, BarChart3, Target, DollarSign } from "lucide-react";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

/* ─── Stat definitions ───────────────────────────────── */
interface StatItem {
  icon: typeof Users;
  label: string;
  value: number;
  decimals: number;
  prefix: string;
  suffix: string;
  accentColor: string;
  glowColor: string;
}

/* ─── Default / fallback values (shown while API loads or on error) ── */
const FALLBACK = { trades: 1247, winRate: 73.2, pnl: 15420, users: 2400 };

function buildStats(s: typeof FALLBACK): StatItem[] {
  return [
    {
      icon: BarChart3,
      label: "Total Trades",
      value: s.trades,
      decimals: 0,
      prefix: "",
      suffix: "+",
      accentColor: "text-[#00f0ff]",
      glowColor: "rgba(0, 240, 255, 0.15)",
    },
    {
      icon: Target,
      label: "Win Rate",
      value: s.winRate,
      decimals: 1,
      prefix: "",
      suffix: "%",
      accentColor: "text-[#00ff88]",
      glowColor: "rgba(0, 255, 136, 0.15)",
    },
    {
      icon: DollarSign,
      label: "Total P&L",
      value: s.pnl,
      decimals: 0,
      prefix: "$",
      suffix: "",
      accentColor: s.pnl >= 0 ? "text-[#00ff88]" : "text-[#ff3366]",
      glowColor: s.pnl >= 0 ? "rgba(0, 255, 136, 0.15)" : "rgba(255, 51, 102, 0.15)",
    },
    {
      icon: Users,
      label: "Active Traders",
      value: s.users,
      decimals: 1,
      prefix: "",
      suffix: "K+",
      accentColor: "text-[#ffaa00]",
      glowColor: "rgba(255, 170, 0, 0.15)",
    },
  ];
}

/* ─── Animated counter with decimal support ──────────── */
function StatCounter({
  value,
  decimals,
  prefix,
  suffix,
  className,
  duration = 2200,
}: {
  value: number;
  decimals: number;
  prefix: string;
  suffix: string;
  className?: string;
  duration?: number;
}) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const hasAnimated = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasAnimated.current) {
          hasAnimated.current = true;
          const startTime = performance.now();

          const animate = (currentTime: number) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            /* Cubic ease-out for natural deceleration */
            const eased = 1 - Math.pow(1 - progress, 3);
            setCount(eased * value);

            if (progress < 1) {
              requestAnimationFrame(animate);
            } else {
              setCount(value);
            }
          };

          requestAnimationFrame(animate);
          observer.unobserve(el);
        }
      },
      { threshold: 0.5 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [value, duration]);

  /* Format: integers get toLocaleString, decimals get toFixed */
  const formatted =
    decimals === 0
      ? Math.floor(count).toLocaleString()
      : count.toFixed(decimals);

  return (
    <span ref={ref} className={`font-mono-nums ${className ?? ""}`}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}

/* ─── Individual stat card ───────────────────────────── */
function StatCard({ stat, delay }: { stat: StatItem; delay: number }) {
  const Icon = stat.icon;

  return (
    <ScrollReveal delay={delay}>
      <div className="group relative flex flex-col items-center gap-3 px-6 py-6 sm:py-8 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.12] transition-all duration-300">
        {/* Glow on hover */}
        <div
          className="absolute top-4 left-1/2 -translate-x-1/2 w-16 h-16 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-2xl pointer-events-none"
          style={{ background: stat.glowColor }}
          aria-hidden="true"
        />

        {/* Icon container */}
        <div
          className={`relative flex items-center justify-center w-10 h-10 rounded-lg bg-white/[0.04] border border-white/[0.06] ${stat.accentColor}`}
        >
          <Icon className="w-5 h-5" strokeWidth={1.5} />
        </div>

        {/* Animated number */}
        <StatCounter
          value={stat.value}
          decimals={stat.decimals}
          prefix={stat.prefix}
          suffix={stat.suffix}
          duration={2200}
          className={`text-2xl sm:text-3xl font-bold ${stat.accentColor}`}
        />

        {/* Label */}
        <span className="text-xs sm:text-sm text-slate-400 font-medium tracking-wide">
          {stat.label}
        </span>
      </div>
    </ScrollReveal>
  );
}

/* ═══════════════════════════════════════════════════════
   LiveStatsBanner — animated platform statistics strip
   Fetches real bot stats from /api/bot?action=status,
   falls back to demo values on error / timeout.
   ═══════════════════════════════════════════════════════ */
export function LiveStatsBanner() {
  const [stats, setStats] = useState(FALLBACK);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/bot?action=status", { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((d) => {
        if (d?.closed_trades != null) {
          setStats({
            trades: d.closed_trades,
            winRate: d.win_rate ?? FALLBACK.winRate,
            pnl: d.total_pnl ?? FALLBACK.pnl,
            users: FALLBACK.users,
          });
        }
      })
      .catch(() => {
        /* Keep fallback defaults on error */
      });
    return () => controller.abort();
  }, []);

  /* Users value is displayed as "X.XK+" — divide to get decimal */
  const displayStats = buildStats({
    ...stats,
    users: stats.users / 1000,
  });

  return (
    <section id="live-stats" className="relative py-12 sm:py-16 px-4 overflow-hidden">
      {/* Top gradient separator */}
      <div
        className="absolute top-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(0,240,255,0.1) 30%, rgba(0,128,255,0.1) 70%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      {/* Bottom gradient separator */}
      <div
        className="absolute bottom-0 left-0 right-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(0,240,255,0.2) 30%, rgba(0,128,255,0.2) 70%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      <div className="mx-auto max-w-5xl">
        {/* Responsive grid: 2x2 mobile, 4-col desktop */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          {displayStats.map((stat, i) => (
            <StatCard key={stat.label} stat={stat} delay={i * 120} />
          ))}
        </div>
      </div>
    </section>
  );
}
