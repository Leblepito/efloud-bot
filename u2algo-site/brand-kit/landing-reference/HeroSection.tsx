"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Play,
  ArrowRight,
  Shield,
  Zap,
  Lock,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { MeshGradient } from "@/components/shared/MeshGradient";
import { ScrollReveal } from "@/components/shared/ScrollReveal";

/* ─── Mock ticker data ───────────────────────────────── */
interface TickerCoin {
  symbol: string;
  name: string;
  price: string;
  change: number;
}

const TICKER_DATA: TickerCoin[] = [
  { symbol: "BTC", name: "Bitcoin", price: "67,842.30", change: 2.34 },
  { symbol: "ETH", name: "Ethereum", price: "3,521.18", change: -0.87 },
  { symbol: "SOL", name: "Solana", price: "178.45", change: 5.12 },
  { symbol: "BNB", name: "BNB", price: "612.90", change: 1.05 },
  { symbol: "XRP", name: "Ripple", price: "0.6234", change: -1.42 },
  { symbol: "ADA", name: "Cardano", price: "0.4821", change: 3.78 },
  { symbol: "AVAX", name: "Avalanche", price: "38.92", change: -0.33 },
  { symbol: "DOT", name: "Polkadot", price: "7.84", change: 1.91 },
  { symbol: "LINK", name: "Chainlink", price: "18.23", change: 4.56 },
  { symbol: "MATIC", name: "Polygon", price: "0.9102", change: -2.14 },
];

const BADGES = [
  { icon: Shield, label: "24/7 AI Monitoring", delay: 600 },
  { icon: Zap, label: "0.03s Execution", delay: 800 },
  { icon: Lock, label: "256-bit Encrypted", delay: 1000 },
];


/* ─── Particle dot field (canvas-based) ──────────────── */
function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let particles: {
      x: number;
      y: number;
      vx: number;
      vy: number;
      r: number;
      opacity: number;
    }[] = [];

    const dpr = window.devicePixelRatio || 1;

    function resize() {
      if (!canvas || !ctx) return;
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function init() {
      if (!canvas) return;
      resize();
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      const count = Math.min(
        80,
        Math.floor((w * h) / 12000)
      );
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: Math.random() * 1.5 + 0.5,
        opacity: Math.random() * 0.3 + 0.1,
      }));
    }

    function draw() {
      if (!ctx || !canvas) return;
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      ctx.clearRect(0, 0, w, h);

      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = w;
        if (p.x > w) p.x = 0;
        if (p.y < 0) p.y = h;
        if (p.y > h) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0, 240, 255, ${p.opacity})`;
        ctx.fill();
      }

      animId = requestAnimationFrame(draw);
    }

    init();
    draw();

    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-[1]"
      aria-hidden="true"
    />
  );
}

/* ─── Auto-scrolling ticker strip ────────────────────── */
function TickerStrip() {
  const doubled = [...TICKER_DATA, ...TICKER_DATA];

  return (
    <div className="relative w-full overflow-hidden border-t border-white/[0.06] bg-white/[0.02]">
      {/* Fade edges */}
      <div className="absolute left-0 top-0 bottom-0 w-16 z-10 bg-gradient-to-r from-black to-transparent pointer-events-none" />
      <div className="absolute right-0 top-0 bottom-0 w-16 z-10 bg-gradient-to-l from-black to-transparent pointer-events-none" />

      <div
        className="flex"
        style={{
          animation: "hero-ticker-scroll 40s linear infinite",
        }}
      >
        {doubled.map((coin, i) => {
          const isPositive = coin.change >= 0;
          return (
            <div
              key={`${coin.symbol}-${i}`}
              className="flex items-center gap-3 px-6 py-3 shrink-0"
            >
              <span className="text-white font-display font-semibold text-sm">
                {coin.symbol}
              </span>
              <span className="text-slate-400 text-xs hidden sm:inline">
                {coin.name}
              </span>
              <span className="text-white font-mono-nums text-sm">
                ${coin.price}
              </span>
              <span
                className={`flex items-center gap-0.5 text-xs font-medium ${
                  isPositive ? "text-[#00ff88]" : "text-[#ff3366]"
                }`}
              >
                {isPositive ? (
                  <TrendingUp className="w-3 h-3" />
                ) : (
                  <TrendingDown className="w-3 h-3" />
                )}
                {isPositive ? "+" : ""}
                {coin.change.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Floating glass badge ───────────────────────────── */
function FloatingBadge({
  icon: Icon,
  label,
  delay,
}: {
  icon: typeof Shield;
  label: string;
  delay: number;
}) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  return (
    <div
      className={`
        inline-flex items-center gap-2 px-4 py-2 rounded-full
        bg-white/[0.04] border border-white/[0.08]
        backdrop-blur-md
        transition-all duration-700 ease-out
        ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3"}
      `}
    >
      <Icon className="w-3.5 h-3.5 text-[#00f0ff]" strokeWidth={1.5} />
      <span className="text-xs font-medium text-slate-300 whitespace-nowrap">
        {label}
      </span>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════
   HeroSection — dramatic, full-viewport landing hero
   ═══════════════════════════════════════════════════════ */
export function HeroSection() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  return (
    <section className="relative min-h-[calc(100vh-64px)] flex flex-col overflow-hidden bg-black">
      {/* Keyframes defined in globals.css: hero-ticker-scroll, hero-gradient-x, cta-glow */}

      {/* Background layers */}
      <div
        className="absolute inset-0 pointer-events-none z-0"
        aria-hidden="true"
        style={{ background: "radial-gradient(circle at center, rgba(6,182,212,0.08) 0%, transparent 65%)" }}
      />

      {/* Animated gradient orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0" aria-hidden="true">
        <div style={{ position: "absolute", top: "-10rem", right: "-10rem", width: "600px", height: "600px", borderRadius: "9999px", background: "rgba(6,182,212,0.05)", filter: "blur(120px)", animation: "orb-pulse 4s ease-in-out infinite" }} />
        <div style={{ position: "absolute", bottom: "-10rem", left: "-10rem", width: "500px", height: "500px", borderRadius: "9999px", background: "rgba(59,130,246,0.05)", filter: "blur(120px)", animation: "orb-pulse 4s ease-in-out infinite", animationDelay: "2s" }} />
        <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: "800px", height: "800px", borderRadius: "9999px", background: "rgba(168,85,247,0.03)", filter: "blur(160px)" }} />
      </div>

      {/* Subtle grid pattern */}
      <div
        className="absolute inset-0 pointer-events-none z-0"
        style={{
          backgroundImage: "linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }}
        aria-hidden="true"
      />

      <MeshGradient className="z-0" />
      <ParticleField />

      {/* Radial glow behind headline — cyan primary */}
      <div
        className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1100px] h-[900px] pointer-events-none z-0"
        aria-hidden="true"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,240,255,0.13) 0%, rgba(0,128,255,0.06) 40%, transparent 70%)",
        }}
      />
      {/* Radial glow — purple accent, offset right */}
      <div
        className="absolute top-1/2 left-[60%] -translate-x-1/2 -translate-y-1/2 w-[700px] h-[500px] pointer-events-none z-0"
        aria-hidden="true"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(99,102,241,0.07) 0%, transparent 65%)",
        }}
      />

      {/* Content */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 sm:px-6 text-center">
        {/* Live pill badge */}
        <div
          className={`
            inline-flex items-center gap-2 mb-6 px-4 py-1.5 rounded-full
            border border-[#00f0ff]/20 bg-[#00f0ff]/[0.05]
            transition-all duration-700 delay-100
            ${mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}
          `}
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#00f0ff] opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-[#00f0ff]" />
          </span>
          <span className="text-xs font-medium text-[#00f0ff] tracking-wide">
            Live on Binance Futures
          </span>
        </div>

        {/* Headline */}
        <h1
          className={`
            font-display font-extrabold tracking-tight leading-[1.08]
            text-5xl sm:text-6xl lg:text-7xl
            max-w-4xl
            transition-all duration-700 delay-200
            ${mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"}
          `}
        >
          <span className="text-white">Trade Smarter with </span>
          <span className="bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-500 bg-clip-text text-transparent">
            AI-Powered
          </span>
          <span className="text-white"> Trading</span>
        </h1>

        {/* Subheadline */}
        <p
          className={`
            mt-5 sm:mt-6 max-w-2xl text-base sm:text-lg text-slate-400 leading-relaxed
            transition-all duration-700 delay-300
            ${mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"}
          `}
        >
          Generate strategies with natural language, backtest against real market
          data, and deploy autonomous trading bots — all powered by advanced AI
          and institutional-grade risk management.
        </p>

        {/* CTA buttons */}
        <div
          className={`
            flex flex-col sm:flex-row items-center gap-3 sm:gap-4 mt-8 sm:mt-10
            transition-all duration-700 delay-[400ms]
            ${mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"}
          `}
        >
          {/* Primary gradient CTA — animated glow */}
          <Link
            href="/auth"
            className="
              group relative inline-flex items-center gap-2.5 px-8 py-4
              bg-gradient-to-r from-[#00f0ff] to-[#0080ff]
              text-white font-bold text-lg rounded-xl
              hover:brightness-110
              hover:shadow-[0_0_40px_rgba(0,240,255,0.28)]
              transition-all duration-300
              active:scale-[0.97]
              animate-cta-glow
            "
          >
            Start Free Demo
            <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
          </Link>

          {/* Ghost / outline CTA — scrolls to live stats */}
          <a
            href="#live-stats"
            className="
              inline-flex items-center gap-2.5 px-8 py-4
              border border-white/[0.12] bg-white/[0.04]
              text-slate-200 font-bold text-lg rounded-xl
              hover:bg-white/[0.09] hover:border-white/[0.22]
              hover:shadow-[0_0_20px_rgba(255,255,255,0.05)]
              transition-all duration-300
              active:scale-[0.97]
            "
          >
            <Play className="w-4.5 h-4.5" />
            See Live Results
          </a>
        </div>

        {/* Floating trust badges */}
        <ScrollReveal className="mt-10 sm:mt-14" delay={500}>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {BADGES.map((badge) => (
              <FloatingBadge
                key={badge.label}
                icon={badge.icon}
                label={badge.label}
                delay={badge.delay}
              />
            ))}
          </div>
        </ScrollReveal>

        {/* Stat bar */}
        <div
          className={`
            mt-16 grid grid-cols-2 sm:grid-cols-4 gap-6 max-w-3xl mx-auto
            transition-all duration-700 delay-[700ms]
            ${mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}
          `}
        >
          {[
            { label: "Signals Generated", value: "50,000+" },
            { label: "Backtests Run", value: "10,000+" },
            { label: "Active Traders", value: "2,500+" },
            { label: "Avg Win Rate", value: "73.2%" },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-2xl sm:text-3xl font-bold text-white font-display">{stat.value}</div>
              <div className="text-xs text-slate-500 mt-1 uppercase tracking-wider">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Ticker strip anchored to bottom */}
      <TickerStrip />
    </section>
  );
}
