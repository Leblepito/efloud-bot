"use client";

import { useEffect, useRef, useCallback } from "react";

/* ─── Types ───────────────────────────────────────────── */
interface Candle {
  open: number;
  close: number;
  high: number;
  low: number;
  time: string;
}

interface TradeMarker {
  candleIndex: number;
  type: "buy" | "sell";
  label: string;
}

/* ─── Pre-generated chart data ────────────────────────── */
function generateChartData(): {
  candles: Candle[];
  ma7: number[];
  ma25: number[];
  markers: TradeMarker[];
} {
  // Deterministic candle data — realistic BTC/USDT 4H chart
  const basePrice = 66800;
  const rawCloses = [
    66820, 66950, 66780, 66600, 66450, 66520, 66700, 66880, 67050, 67200,
    67150, 67000, 66850, 66920, 67100, 67350, 67500, 67420, 67280, 67400,
    67600, 67750, 67680, 67550, 67700, 67850, 68000, 67900, 67780, 67920,
    68100, 68250, 68180, 68050, 68200, 68400,
  ];

  const candles: Candle[] = rawCloses.map((close, i) => {
    const prev = i > 0 ? rawCloses[i - 1] : basePrice;
    const open = prev + (close - prev) * 0.3;
    const bodyRange = Math.abs(close - open);
    const wickUp = bodyRange * (0.3 + ((i * 7) % 10) / 15);
    const wickDown = bodyRange * (0.2 + ((i * 11) % 10) / 15);
    const high = Math.max(open, close) + wickUp + ((i * 13) % 40);
    const low = Math.min(open, close) - wickDown - ((i * 17) % 35);

    const hour = ((i * 4) % 24).toString().padStart(2, "0");
    const day = Math.floor((i * 4) / 24) + 1;
    const time = `Apr ${day.toString().padStart(2, "0")} ${hour}:00`;

    return {
      open: Math.round(open * 100) / 100,
      close,
      high: Math.round(high * 100) / 100,
      low: Math.round(low * 100) / 100,
      time,
    };
  });

  // Moving averages
  function calcMA(period: number): number[] {
    return candles.map((_, i) => {
      const start = Math.max(0, i - period + 1);
      const slice = candles.slice(start, i + 1);
      return slice.reduce((s, c) => s + c.close, 0) / slice.length;
    });
  }

  const ma7 = calcMA(7);
  const ma25 = calcMA(25);

  const markers: TradeMarker[] = [
    { candleIndex: 8, type: "buy", label: "+2.4%" },
    { candleIndex: 16, type: "buy", label: "+5.1%" },
    { candleIndex: 22, type: "sell", label: "-1.2%" },
    { candleIndex: 30, type: "buy", label: "+8.7%" },
  ];

  return { candles, ma7, ma25, markers };
}

/* ─── Chart Renderer ──────────────────────────────────── */
function drawChart(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  progress: number,          // 0→1 entrance animation
  scanPhase: number,         // 0→1 scanning line position
  priceFlash: number,        // 0→1 flash intensity
  data: ReturnType<typeof generateChartData>,
) {
  const { candles, ma7, ma25, markers } = data;
  const pad = { top: 50, right: 80, bottom: 40, left: 16 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  // Price range
  const allPrices = candles.flatMap((c) => [c.high, c.low]);
  const minP = Math.min(...allPrices) - 40;
  const maxP = Math.max(...allPrices) + 40;
  const rangeP = maxP - minP || 1;

  const yScale = (v: number) => pad.top + chartH - ((v - minP) / rangeP) * chartH;
  const candleW = chartW / candles.length;

  ctx.clearRect(0, 0, w, h);

  // Visible candle count based on progress
  const visibleCount = Math.floor(progress * candles.length);

  /* ── Grid lines ── */
  const gridSteps = 5;
  ctx.strokeStyle = "rgba(255,255,255,0.04)";
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= gridSteps; i++) {
    const y = pad.top + (chartH / gridSteps) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(w - pad.right, y);
    ctx.stroke();
  }

  // Vertical grid (every 6 candles)
  for (let i = 0; i < candles.length; i += 6) {
    if (i > visibleCount) break;
    const x = pad.left + i * candleW + candleW / 2;
    ctx.beginPath();
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + chartH);
    ctx.stroke();
  }

  /* ── Price scale (right side) ── */
  ctx.font = "10px 'JetBrains Mono', monospace";
  ctx.textAlign = "right";
  ctx.fillStyle = "rgba(255,255,255,0.18)";
  for (let i = 0; i <= gridSteps; i++) {
    const priceVal = maxP - (rangeP / gridSteps) * i;
    const y = pad.top + (chartH / gridSteps) * i;
    ctx.fillText(priceVal.toFixed(0), w - pad.right + 50, y + 3);
  }

  /* ── Time labels (bottom) ── */
  ctx.textAlign = "center";
  ctx.fillStyle = "rgba(255,255,255,0.12)";
  ctx.font = "9px 'JetBrains Mono', monospace";
  for (let i = 0; i < visibleCount; i += 6) {
    const x = pad.left + i * candleW + candleW / 2;
    ctx.fillText(candles[i].time, x, h - pad.bottom + 18);
  }

  /* ── Candlesticks ── */
  const bodyW = candleW * 0.55;
  for (let i = 0; i < visibleCount; i++) {
    const c = candles[i];
    const isBull = c.close >= c.open;
    const x = pad.left + i * candleW + candleW / 2;

    // Entrance fade for newest candles
    const candleAge = visibleCount - i;
    const alpha = candleAge <= 3 ? 0.4 + (candleAge / 3) * 0.6 : 1;

    // Wick
    ctx.strokeStyle = isBull
      ? `rgba(0,255,136,${0.5 * alpha})`
      : `rgba(255,51,102,${0.5 * alpha})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, yScale(c.high));
    ctx.lineTo(x, yScale(c.low));
    ctx.stroke();

    // Body
    const bodyTop = yScale(Math.max(c.open, c.close));
    const bodyBot = yScale(Math.min(c.open, c.close));
    const bodyH = Math.max(bodyBot - bodyTop, 1);

    if (isBull) {
      const grad = ctx.createLinearGradient(x, bodyTop, x, bodyBot);
      grad.addColorStop(0, `rgba(0,255,136,${0.85 * alpha})`);
      grad.addColorStop(1, `rgba(0,255,136,${0.5 * alpha})`);
      ctx.fillStyle = grad;
    } else {
      const grad = ctx.createLinearGradient(x, bodyTop, x, bodyBot);
      grad.addColorStop(0, `rgba(255,51,102,${0.85 * alpha})`);
      grad.addColorStop(1, `rgba(255,51,102,${0.5 * alpha})`);
      ctx.fillStyle = grad;
    }
    ctx.fillRect(x - bodyW / 2, bodyTop, bodyW, bodyH);
  }

  /* ── Moving Average Lines ── */
  function drawMA(values: number[], color: string, opacity: number, lineW: number) {
    if (visibleCount < 2) return;
    ctx.strokeStyle = color;
    ctx.globalAlpha = opacity;
    ctx.lineWidth = lineW;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();

    for (let i = 0; i < visibleCount; i++) {
      const x = pad.left + i * candleW + candleW / 2;
      const y = yScale(values[i]);
      if (i === 0) ctx.moveTo(x, y);
      else {
        // Smooth bezier
        const prevX = pad.left + (i - 1) * candleW + candleW / 2;
        const prevY = yScale(values[i - 1]);
        const cpx = (prevX + x) / 2;
        ctx.bezierCurveTo(cpx, prevY, cpx, y, x, y);
      }
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  drawMA(ma7, "#00f0ff", 0.6, 1.5);
  drawMA(ma25, "#ffaa00", 0.35, 1);

  /* ── Trade Markers ── */
  for (const m of markers) {
    if (m.candleIndex >= visibleCount) continue;

    const c = candles[m.candleIndex];
    const x = pad.left + m.candleIndex * candleW + candleW / 2;
    const isBuy = m.type === "buy";
    const markerY = isBuy ? yScale(c.low) + 14 : yScale(c.high) - 14;

    // Entrance scale
    const markerProgress = Math.min(1, (visibleCount - m.candleIndex) / 4);
    const scale = markerProgress;

    ctx.save();
    ctx.translate(x, markerY);
    ctx.scale(scale, scale);

    // Glow
    if (markerProgress > 0.5) {
      const glowAlpha = 0.15 * markerProgress;
      ctx.beginPath();
      ctx.arc(0, 0, 12, 0, Math.PI * 2);
      ctx.fillStyle = isBuy
        ? `rgba(0,255,136,${glowAlpha})`
        : `rgba(255,51,102,${glowAlpha})`;
      ctx.fill();
    }

    // Triangle
    ctx.beginPath();
    if (isBuy) {
      ctx.moveTo(0, -5);
      ctx.lineTo(-4.5, 4);
      ctx.lineTo(4.5, 4);
    } else {
      ctx.moveTo(0, 5);
      ctx.lineTo(-4.5, -4);
      ctx.lineTo(4.5, -4);
    }
    ctx.closePath();
    ctx.fillStyle = isBuy ? "#00ff88" : "#ff3366";
    ctx.fill();

    // Label
    ctx.font = "bold 9px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = isBuy
      ? "rgba(0,255,136,0.9)"
      : "rgba(255,51,102,0.9)";
    const labelY = isBuy ? 16 : -12;
    ctx.fillText(m.label, 0, labelY);

    ctx.restore();
  }

  /* ── Scanning Line ── */
  const scanX = pad.left + scanPhase * chartW;
  if (scanX >= pad.left && scanX <= w - pad.right) {
    const grad = ctx.createLinearGradient(scanX, pad.top, scanX, pad.top + chartH);
    grad.addColorStop(0, "rgba(0,240,255,0)");
    grad.addColorStop(0.3, "rgba(0,240,255,0.15)");
    grad.addColorStop(0.5, "rgba(0,240,255,0.25)");
    grad.addColorStop(0.7, "rgba(0,240,255,0.15)");
    grad.addColorStop(1, "rgba(0,240,255,0)");

    ctx.strokeStyle = grad;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(scanX, pad.top);
    ctx.lineTo(scanX, pad.top + chartH);
    ctx.stroke();

    // Glow halo
    const haloGrad = ctx.createRadialGradient(scanX, pad.top + chartH / 2, 0, scanX, pad.top + chartH / 2, 40);
    haloGrad.addColorStop(0, "rgba(0,240,255,0.06)");
    haloGrad.addColorStop(1, "rgba(0,240,255,0)");
    ctx.fillStyle = haloGrad;
    ctx.fillRect(scanX - 40, pad.top, 80, chartH);
  }

  /* ── HUD: Top-left symbol/timeframe ── */
  ctx.font = "bold 13px 'JetBrains Mono', monospace";
  ctx.textAlign = "left";
  ctx.fillStyle = "rgba(255,255,255,0.7)";
  ctx.fillText("BTC/USDT", pad.left + 4, 24);

  // Timeframe badge
  ctx.fillStyle = "rgba(0,240,255,0.12)";
  const tfX = pad.left + 100;
  roundRect(ctx, tfX, 12, 28, 18, 4);
  ctx.fill();
  ctx.strokeStyle = "rgba(0,240,255,0.25)";
  ctx.lineWidth = 0.5;
  roundRect(ctx, tfX, 12, 28, 18, 4);
  ctx.stroke();
  ctx.font = "bold 10px 'JetBrains Mono', monospace";
  ctx.fillStyle = "rgba(0,240,255,0.8)";
  ctx.fillText("4H", tfX + 5, 24);

  /* ── HUD: Top-right live price ── */
  const priceStr = "$67,842.30";
  ctx.font = "bold 14px 'JetBrains Mono', monospace";
  ctx.textAlign = "right";

  // Flash effect
  const flashG = Math.min(1, priceFlash);
  if (flashG > 0) {
    ctx.fillStyle = `rgba(0,255,136,${0.15 * flashG})`;
    roundRect(ctx, w - pad.right - 120, 8, 118, 26, 6);
    ctx.fill();
  }

  ctx.fillStyle = `rgba(0,255,136,${0.9 + 0.1 * flashG})`;
  ctx.fillText(priceStr, w - pad.right - 8, 26);

  /* ── HUD: Bottom-right AI signal ── */
  const sigW = 130;
  const sigH = 22;
  const sigX = w - pad.right - sigW + 48;
  const sigY = h - pad.bottom + 24;

  // Badge background
  ctx.fillStyle = "rgba(0,255,136,0.06)";
  roundRect(ctx, sigX, sigY, sigW, sigH, 6);
  ctx.fill();
  ctx.strokeStyle = "rgba(0,255,136,0.2)";
  ctx.lineWidth = 0.5;
  roundRect(ctx, sigX, sigY, sigW, sigH, 6);
  ctx.stroke();

  // Pulsing glow behind badge
  const pulseAlpha = 0.04 + Math.sin(Date.now() / 600) * 0.03;
  ctx.fillStyle = `rgba(0,255,136,${pulseAlpha})`;
  roundRect(ctx, sigX - 2, sigY - 2, sigW + 4, sigH + 4, 8);
  ctx.fill();

  // Text
  ctx.font = "bold 9px 'JetBrains Mono', monospace";
  ctx.textAlign = "left";
  ctx.fillStyle = "rgba(0,255,136,0.7)";
  ctx.fillText("AI Signal: BULLISH", sigX + 10, sigY + 15);

  // Dot indicator
  ctx.beginPath();
  ctx.arc(sigX + 5, sigY + sigH / 2, 2, 0, Math.PI * 2);
  ctx.fillStyle = "#00ff88";
  ctx.fill();
}

/* ── Rounded rect helper ── */
function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

/* ═══════════════════════════════════════════════════════════
   MarketChartHero — Bloomberg-meets-sci-fi candlestick hero
   ═══════════════════════════════════════════════════════════ */
export function MarketChartHero() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dataRef = useRef<ReturnType<typeof generateChartData> | null>(null);
  const startRef = useRef<number>(0);
  const rafRef = useRef<number>(0);

  const animateRef = useRef<() => void>(() => {});

  animateRef.current = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (!dataRef.current) {
      dataRef.current = generateChartData();
    }

    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    const dpr = window.devicePixelRatio || 1;

    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    if (startRef.current === 0) startRef.current = Date.now();
    const elapsed = (Date.now() - startRef.current) / 1000;

    // Entrance animation: candles appear over 2 seconds
    const entranceProgress = Math.min(1, elapsed / 2.2);

    // Scan line: 8-second cycle, starts after entrance
    const scanDelay = 2.5;
    const scanCycle = 8;
    const scanElapsed = Math.max(0, elapsed - scanDelay);
    const scanPhase = (scanElapsed % scanCycle) / scanCycle;

    // Price flash: every 5 seconds, lasts 0.4s
    const flashCycle = 5;
    const flashElapsed = elapsed % flashCycle;
    const priceFlash = flashElapsed < 0.4 ? 1 - flashElapsed / 0.4 : 0;

    drawChart(ctx, w, h, entranceProgress, scanPhase, priceFlash, dataRef.current);

    rafRef.current = requestAnimationFrame(() => animateRef.current());
  };

  useEffect(() => {
    rafRef.current = requestAnimationFrame(() => animateRef.current());
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // Handle resize
  useEffect(() => {
    function handleResize() {
      startRef.current = 0; // replay entrance on resize
      dataRef.current = null; // regenerate (same deterministic data)
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div className="relative w-full overflow-hidden bg-black py-8 sm:py-12">
      {/* Subtle vignette */}
      <div
        className="absolute inset-0 pointer-events-none z-10"
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.4) 0%, transparent 15%, transparent 85%, rgba(0,0,0,0.6) 100%)",
        }}
      />
      {/* Left/right fade */}
      <div className="absolute inset-y-0 left-0 w-12 bg-gradient-to-r from-black to-transparent pointer-events-none z-10" />
      <div className="absolute inset-y-0 right-0 w-12 bg-gradient-to-l from-black to-transparent pointer-events-none z-10" />

      {/* Glass container */}
      <div className="relative mx-auto max-w-6xl px-4">
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] backdrop-blur-md overflow-hidden">
          <canvas
            ref={canvasRef}
            className="w-full h-[250px] sm:h-[320px] md:h-[400px]"
            aria-hidden="true"
          />
        </div>
      </div>
    </div>
  );
}
