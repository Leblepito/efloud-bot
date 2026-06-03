// ════════════════════════════════════════════════════════════════════
// smcOverlay.ts — calculated Smart Money Concepts overlay for the
// lightweight-charts candlestick series in InteractiveChart.tsx.
//
// Exports:
//   computeSMC(candles, timeframe, opts?)  → deterministic SMC telemetry
//   class SmcOverlayPrimitive               → canvas primitive that draws it
//
// Palette (terminal): bull #00FF88 · bear #FF4D4D · neutral #FFA500.
// Mirrors the PositionOverlayPrimitive API already used in this file
// (attached/detached/paneViews + target.useMediaCoordinateSpace renderer).
// ════════════════════════════════════════════════════════════════════

export type Candle = { time: number; open: number; high: number; low: number; close: number };

export type SmcStructure = { time: number; price: number; kind: "BOS" | "CHOCH"; dir: "bull" | "bear" };
export type SmcBox = { startTime: number; top: number; bottom: number; dir: "bull" | "bear"; mitigated: boolean };
export type SmcData = {
  structure: SmcStructure[];
  fvgs: SmcBox[];
  obs: SmcBox[];
  pdh: number | null;
  pdl: number | null;
  range: { high: number; low: number; eq: number } | null;
};

type ComputeOpts = {
  swingLookback?: number; // fractal half-window
  maxFvg?: number;
  maxOb?: number;
  maxStructure?: number;
  rangeBars?: number; // bars used for premium/discount range
};

/** Deterministic SMC computation from raw candles (no backend dependency). */
export function computeSMC(candles: Candle[], timeframe: string, opts: ComputeOpts = {}): SmcData {
  const L = opts.swingLookback ?? 5;
  const maxFvg = opts.maxFvg ?? 6;
  const maxOb = opts.maxOb ?? 4;
  const maxStructure = opts.maxStructure ?? 6;
  const rangeBars = opts.rangeBars ?? 50;
  const empty: SmcData = { structure: [], fvgs: [], obs: [], pdh: null, pdl: null, range: null };
  if (!candles || candles.length < L * 2 + 5) return empty;

  const n = candles.length;

  // ── 1. Fractal swing points ──────────────────────────────────────
  type Swing = { idx: number; time: number; price: number; type: "high" | "low" };
  const swings: Swing[] = [];
  for (let i = L; i < n - L; i++) {
    let isHigh = true, isLow = true;
    for (let j = i - L; j <= i + L; j++) {
      if (j === i) continue;
      if (candles[j].high >= candles[i].high) isHigh = false;
      if (candles[j].low <= candles[i].low) isLow = false;
    }
    if (isHigh) swings.push({ idx: i, time: candles[i].time, price: candles[i].high, type: "high" });
    if (isLow) swings.push({ idx: i, time: candles[i].time, price: candles[i].low, type: "low" });
  }

  // ── 2. Break of Structure / Change of Character ──────────────────
  const structure: SmcStructure[] = [];
  let trend: "bull" | "bear" | null = null;
  let lastHigh: Swing | null = null;
  let lastLow: Swing | null = null;
  let si = 0;
  for (let i = 0; i < n; i++) {
    // absorb swings confirmed by this bar
    while (si < swings.length && swings[si].idx <= i) {
      if (swings[si].type === "high") lastHigh = swings[si];
      else lastLow = swings[si];
      si++;
    }
    const c = candles[i];
    if (lastHigh && c.close > lastHigh.price && i > lastHigh.idx) {
      const kind = trend === "bear" ? "CHOCH" : "BOS";
      structure.push({ time: c.time, price: lastHigh.price, kind, dir: "bull" });
      trend = "bull";
      lastHigh = null; // consumed
    } else if (lastLow && c.close < lastLow.price && i > lastLow.idx) {
      const kind = trend === "bull" ? "CHOCH" : "BOS";
      structure.push({ time: c.time, price: lastLow.price, kind, dir: "bear" });
      trend = "bear";
      lastLow = null;
    }
  }

  // ── 3. Fair Value Gaps (3-candle imbalance) ──────────────────────
  const fvgs: SmcBox[] = [];
  for (let i = 1; i < n - 1; i++) {
    const a = candles[i - 1], c = candles[i + 1];
    // bullish gap: prior high below next low
    if (a.high < c.low) {
      const top = c.low, bottom = a.high;
      const mitigated = candles.slice(i + 2).some((k) => k.low <= bottom);
      fvgs.push({ startTime: candles[i].time, top, bottom, dir: "bull", mitigated });
    } else if (a.low > c.high) {
      const top = a.low, bottom = c.high;
      const mitigated = candles.slice(i + 2).some((k) => k.high >= top);
      fvgs.push({ startTime: candles[i].time, top, bottom, dir: "bear", mitigated });
    }
  }
  const recentFvgs = fvgs.filter((f) => !f.mitigated).slice(-maxFvg);

  // ── 4. Order Blocks (last opposing candle before a structure break) ─
  const obs: SmcBox[] = [];
  for (const s of structure) {
    const breakIdx = candles.findIndex((c) => c.time === s.time);
    if (breakIdx < 1) continue;
    if (s.dir === "bull") {
      for (let k = breakIdx - 1; k >= Math.max(0, breakIdx - 12); k--) {
        if (candles[k].close < candles[k].open) {
          obs.push({ startTime: candles[k].time, top: candles[k].high, bottom: candles[k].low, dir: "bull", mitigated: false });
          break;
        }
      }
    } else {
      for (let k = breakIdx - 1; k >= Math.max(0, breakIdx - 12); k--) {
        if (candles[k].close > candles[k].open) {
          obs.push({ startTime: candles[k].time, top: candles[k].high, bottom: candles[k].low, dir: "bear", mitigated: false });
          break;
        }
      }
    }
  }
  const recentObs = obs.slice(-maxOb);

  // ── 5. Previous Day High / Low ───────────────────────────────────
  let pdh: number | null = null, pdl: number | null = null;
  const last = candles[n - 1];
  const dayMs = 86400000;
  const lastDayStart = Math.floor((last.time * 1000) / dayMs) * dayMs;
  const prevDayStart = lastDayStart - dayMs;
  const prevDay = candles.filter((c) => c.time * 1000 >= prevDayStart && c.time * 1000 < lastDayStart);
  if (prevDay.length) {
    pdh = Math.max(...prevDay.map((c) => c.high));
    pdl = Math.min(...prevDay.map((c) => c.low));
  }

  // ── 6. Premium / Discount / Equilibrium (recent dealing range) ───
  const slice = candles.slice(-rangeBars);
  const high = Math.max(...slice.map((c) => c.high));
  const low = Math.min(...slice.map((c) => c.low));
  const range = { high, low, eq: (high + low) / 2 };

  return { structure: structure.slice(-maxStructure), fvgs: recentFvgs, obs: recentObs, pdh, pdl, range };
}

// ── Canvas primitive ───────────────────────────────────────────────
const BULL = "#00FF88";
const BEAR = "#FF4D4D";
const NEUTRAL = "#FFA500";

type Layers = { structure?: boolean; fvg?: boolean; ob?: boolean; zones?: boolean; pdhl?: boolean };

export class SmcOverlayPrimitive {
  private _series: any = null;
  private _chart: any = null;
  private _paneView: any;

  constructor(private data: SmcData, private layers: Layers = { structure: true, fvg: true, ob: true, zones: true, pdhl: true }) {
    this._paneView = {
      update: () => {},
      renderer: () => ({
        draw: (target: any) => {
          if (!this._series || !this._chart) return;
          target.useMediaCoordinateSpace(({ context, mediaSize }: any) => {
            const ts = this._chart.timeScale();
            const series = this._series;
            const W = mediaSize.width;
            const priceY = (p: number) => series.priceToCoordinate(p);
            const timeX = (t: number) => ts.timeToCoordinate(t as any);

            const label = (x: number, y: number, text: string, color: string, align: "left" | "right" = "left") => {
              context.save();
              context.font = "bold 8px var(--font-geist-mono), monospace";
              const w = context.measureText(text).width + 8;
              const tagX = align === "left" ? x : x - w;
              context.fillStyle = color;
              context.globalAlpha = 0.9;
              context.fillRect(tagX, y - 7, w, 12);
              context.globalAlpha = 1;
              context.fillStyle = "#04040c";
              context.textAlign = "left";
              context.textBaseline = "middle";
              context.fillText(text, tagX + 4, y);
              context.restore();
            };

            context.save();

            // 1. Premium / Discount / Equilibrium zones (full width rails)
            if (this.layers.zones && this.data.range) {
              const yHigh = priceY(this.data.range.high);
              const yEq = priceY(this.data.range.eq);
              const yLow = priceY(this.data.range.low);
              if (yHigh !== null && yEq !== null && yLow !== null) {
                context.fillStyle = "rgba(255, 77, 77, 0.05)";
                context.fillRect(0, yHigh, W, yEq - yHigh);
                context.fillStyle = "rgba(0, 255, 136, 0.05)";
                context.fillRect(0, yEq, W, yLow - yEq);
                context.strokeStyle = "rgba(255, 165, 0, 0.45)";
                context.setLineDash([6, 4]);
                context.beginPath(); context.moveTo(0, yEq); context.lineTo(W, yEq); context.stroke();
                context.setLineDash([]);
                label(2, yHigh + 7, "PREMIUM", "rgba(255, 77, 77, 0.85)");
                label(2, yEq, "EQ 0.5", "rgba(255, 165, 0, 0.85)");
                label(2, yLow - 7, "DISCOUNT", "rgba(0, 255, 136, 0.85)");
              }
            }

            // 2. Order Blocks (start → right edge)
            if (this.layers.ob) {
              for (const ob of this.data.obs) {
                const x = timeX(ob.startTime);
                const yTop = priceY(ob.top), yBot = priceY(ob.bottom);
                if (x === null || yTop === null || yBot === null) continue;
                const col = ob.dir === "bull" ? BULL : BEAR;
                context.fillStyle = ob.dir === "bull" ? "rgba(0,255,136,0.10)" : "rgba(255,77,77,0.10)";
                context.fillRect(x, yTop, W - x, yBot - yTop);
                context.strokeStyle = col;
                context.globalAlpha = 0.45;
                context.strokeRect(x, yTop, W - x, yBot - yTop);
                context.globalAlpha = 1;
                label(W, (yTop + yBot) / 2, ob.dir === "bull" ? "OB +" : "OB −", col, "right");
              }
            }

            // 3. Fair Value Gaps (start → right edge, hatched-light)
            if (this.layers.fvg) {
              for (const f of this.data.fvgs) {
                const x = timeX(f.startTime);
                const yTop = priceY(f.top), yBot = priceY(f.bottom);
                if (x === null || yTop === null || yBot === null) continue;
                const col = f.dir === "bull" ? BULL : BEAR;
                context.fillStyle = f.dir === "bull" ? "rgba(0,255,136,0.07)" : "rgba(255,77,77,0.07)";
                context.fillRect(x, yTop, W - x, yBot - yTop);
                context.strokeStyle = col;
                context.globalAlpha = 0.3;
                context.setLineDash([2, 2]);
                context.strokeRect(x, yTop, W - x, yBot - yTop);
                context.setLineDash([]);
                context.globalAlpha = 1;
                label(W, (yTop + yBot) / 2, "FVG", col, "right");
              }
            }

            // 4. BOS / ChoCh horizontal break levels
            if (this.layers.structure) {
              for (const s of this.data.structure) {
                const x = timeX(s.time);
                const y = priceY(s.price);
                if (x === null || y === null) continue;
                const col = s.dir === "bull" ? BULL : BEAR;
                context.strokeStyle = col;
                context.globalAlpha = 0.6;
                context.setLineDash(s.kind === "CHOCH" ? [2, 3] : [7, 3]);
                context.beginPath(); context.moveTo(Math.max(0, x), y); context.lineTo(W, y); context.stroke();
                context.setLineDash([]);
                context.globalAlpha = 1;
                label(Math.max(0, x), y, s.kind, col, "left");
              }
            }

            // 5. Previous Day High / Low (full width)
            if (this.layers.pdhl) {
              const drawHL = (p: number | null, text: string) => {
                if (p === null) return;
                const y = priceY(p);
                if (y === null) return;
                context.strokeStyle = "rgba(161,161,170,0.5)";
                context.setLineDash([1, 3]);
                context.beginPath(); context.moveTo(0, y); context.lineTo(W, y); context.stroke();
                context.setLineDash([]);
                label(W, y, text, "rgba(161,161,170,0.9)", "right");
              };
              drawHL(this.data.pdh, "PDH");
              drawHL(this.data.pdl, "PDL");
            }

            context.restore();
          });
        },
      }),
    };
  }

  attached(param: any) { this._series = param.series; this._chart = param.chart; }
  detached() { this._series = null; this._chart = null; }
  paneViews() { return [this._paneView]; }
  priceAxisViews() { return []; }
  timeAxisViews() { return []; }
}
