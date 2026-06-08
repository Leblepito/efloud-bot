"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, LineStyle, IChartApi, ISeriesApi, CandlestickSeries, HistogramSeries, createSeriesMarkers } from "lightweight-charts";
import { SmcOverlayPrimitive, computeSMC } from "./smcOverlay";
import { usePositions } from "@/hooks/usePositions";
import { useOrders } from "@/hooks/useOrders";
import { useConfig } from "@/hooks/useConfig";
import { useHistory } from "@/hooks/useHistory";
import { useSmcSignals } from "@/hooks/useSmcSignals";
import { n } from "@/lib/format";
import { terminal } from "@efloud/tokens";

// TradingView-style Long/Short Position Drawing Overlay Primitive
class PositionOverlayPrimitive {
  private _series: any = null;
  private _chart: any = null;
  private _paneView: any;

  constructor(
    private entryPrice: number,
    private slPrice: number,
    private tp1Price: number,
    private tp2Price: number,
    private tp1Hit: boolean,
    private entryTime: number,
    private exitTime: number | null,
    private isLong: boolean
  ) {
    this._paneView = {
      update: () => {},
      renderer: () => ({
        draw: (target: any) => {
          if (!this._series || !this._chart) return;

          target.useMediaCoordinateSpace(({ context, mediaSize }: any) => {
            const timeScale = this._chart.timeScale();
            const visibleRange = timeScale.getVisibleRange();
            
            let entryX = timeScale.timeToCoordinate(this.entryTime);
            const entryY = this._series.priceToCoordinate(this.entryPrice);
            
            const slY = this.slPrice ? this._series.priceToCoordinate(this.slPrice) : null;
            const tp1Y = this.tp1Price ? this._series.priceToCoordinate(this.tp1Price) : null;
            const tp2Y = this.tp2Price ? this._series.priceToCoordinate(this.tp2Price) : null;
            // Profit zone extends to the farthest valid target (TP2 if present, else TP1)
            const furthestTpY = tp2Y !== null ? tp2Y : tp1Y;

            if (entryX === null) {
              if (visibleRange && (this.entryTime < (visibleRange.from as number))) {
                entryX = 0; // Clamp entry to left edge of screen if it is in the past
              } else {
                return; // Not visible or in the future
              }
            }

            if (entryY === null) return;

            // If the entire closed trade is in the past and off-screen, do not draw
            if (visibleRange && this.exitTime !== null && (this.exitTime < (visibleRange.from as number))) {
              return;
            }

            const exitX = this.exitTime ? timeScale.timeToCoordinate(this.exitTime) : null;
            const rectEndX = exitX !== null ? exitX : mediaSize.width;
            
            // If the entire box is off-screen to the left or right, do not draw
            if (rectEndX < 0 || entryX > mediaSize.width) return;

            const rectWidth = rectEndX - entryX;

            let lossYStart = entryY;
            let lossHeight = 0;
            let profitYStart = entryY;
            let profitHeight = 0;

            if (this.isLong) {
              if (slY !== null) {
                lossHeight = slY - entryY;
                lossYStart = entryY;
              }
              if (furthestTpY !== null) {
                profitHeight = entryY - furthestTpY;
                profitYStart = furthestTpY;
              }
            } else {
              if (slY !== null) {
                lossHeight = entryY - slY;
                lossYStart = slY;
              }
              if (furthestTpY !== null) {
                profitHeight = furthestTpY - entryY;
                profitYStart = entryY;
              }
            }

            context.save();

            // Position-overlay washes below use derived alpha variants (rgba) of the
            // emerald/red/amber tailwind palette; left inline per PR #4 (consistent with
            // smcOverlay/PR #2 — only solid hex are sourced from @efloud/tokens).
            // 1. Draw Shaded Regions
            // Loss Zone (Red Shading)
            if (lossHeight > 0) {
              context.fillStyle = "rgba(239, 68, 68, 0.15)";
              context.fillRect(entryX, lossYStart, rectWidth, lossHeight);
            }

            // Profit Zone (Emerald Green Shading)
            if (profitHeight > 0) {
              context.fillStyle = "rgba(16, 185, 129, 0.15)";
              context.fillRect(entryX, profitYStart, rectWidth, profitHeight);
            }

            // 2. Draw Clean Border/Level Lines (Only within start and end coordinates)
            context.lineWidth = 1;

            const lossPct = this.entryPrice ? Math.abs(((this.slPrice - this.entryPrice) / this.entryPrice) * 100) : 0;
            const tp1Pct = this.entryPrice && this.tp1Price ? Math.abs(((this.tp1Price - this.entryPrice) / this.entryPrice) * 100) : 0;
            const tp2Pct = this.entryPrice && this.tp2Price ? Math.abs(((this.tp2Price - this.entryPrice) / this.entryPrice) * 100) : 0;

            const labelEndX = Math.min(rectEndX, mediaSize.width);

            const drawPriceTag = (y: number, text: string, bgColor: string) => {
              context.save();
              context.font = "bold 9px var(--font-geist-mono), monospace";
              const textWidth = context.measureText(text).width;
              const tagW = textWidth + 8;
              const tagH = 14;
              // Make sure the tag fits within the canvas horizontally
              const tagX = Math.max(0, labelEndX - tagW);
              const tagY = y - tagH / 2;

              context.fillStyle = bgColor;
              context.beginPath();
              if (context.roundRect) {
                context.roundRect(tagX, tagY, tagW, tagH, 2);
              } else {
                context.rect(tagX, tagY, tagW, tagH);
              }
              context.fill();

              context.fillStyle = "#ffffff";
              context.textAlign = "left";
              context.textBaseline = "middle";
              context.fillText(text, tagX + 4, y);
              context.restore();
            };

            // Stop Loss Line
            if (slY !== null) {
              context.strokeStyle = "rgba(239, 68, 68, 0.4)";
              context.beginPath();
              context.moveTo(entryX, slY);
              context.lineTo(rectEndX, slY);
              context.stroke();
              
              drawPriceTag(slY, `SL: ${this.slPrice.toFixed(4)} (-${lossPct.toFixed(2)}%)`, "rgba(220, 38, 38, 0.85)");
            }

            // Take Profit 1 Line (dashed; dimmed + ✓ once already hit)
            if (tp1Y !== null) {
              context.strokeStyle = this.tp1Hit ? "rgba(16, 185, 129, 0.25)" : "rgba(16, 185, 129, 0.45)";
              context.setLineDash([5, 3]);
              context.beginPath();
              context.moveTo(entryX, tp1Y);
              context.lineTo(rectEndX, tp1Y);
              context.stroke();
              context.setLineDash([]);

              drawPriceTag(tp1Y, `TP1${this.tp1Hit ? " ✓" : ""}: ${this.tp1Price.toFixed(4)} (+${tp1Pct.toFixed(2)}%)`, this.tp1Hit ? "rgba(5, 150, 105, 0.55)" : "rgba(5, 150, 105, 0.85)");
            }

            // Take Profit 2 Line (solid)
            if (tp2Y !== null) {
              context.strokeStyle = "rgba(16, 185, 129, 0.5)";
              context.beginPath();
              context.moveTo(entryX, tp2Y);
              context.lineTo(rectEndX, tp2Y);
              context.stroke();

              drawPriceTag(tp2Y, `TP2: ${this.tp2Price.toFixed(4)} (+${tp2Pct.toFixed(2)}%)`, "rgba(5, 150, 105, 0.9)");
            }

            // Entry Line
            context.strokeStyle = "rgba(245, 158, 11, 0.5)";
            context.beginPath();
            context.moveTo(entryX, entryY);
            context.lineTo(rectEndX, entryY);
            context.stroke();

            drawPriceTag(entryY, `ENTRY: ${this.entryPrice.toFixed(4)}`, "rgba(217, 119, 6, 0.85)");

            // 3. Draw Vertical Boundaries (Start and End)
            // Vertical starting line
            if (entryX >= 0 && entryX <= mediaSize.width) {
              context.strokeStyle = "rgba(161, 161, 170, 0.4)";
              context.setLineDash([4, 4]);
              context.beginPath();
              context.moveTo(entryX, Math.min(lossYStart, profitYStart));
              context.lineTo(entryX, Math.max(lossYStart + lossHeight, profitYStart + profitHeight));
              context.stroke();
              context.setLineDash([]);
            }

            // Vertical ending line
            if (exitX !== null && exitX >= 0 && exitX <= mediaSize.width) {
              context.strokeStyle = "rgba(161, 161, 170, 0.4)";
              context.setLineDash([4, 4]);
              context.beginPath();
              context.moveTo(exitX, Math.min(lossYStart, profitYStart));
              context.lineTo(exitX, Math.max(lossYStart + lossHeight, profitYStart + profitHeight));
              context.stroke();
              context.setLineDash([]);
            }

            // 4. Draw Center Floating Badges (Centering dynamically in the visible horizontal box)
            const visibleLeft = Math.max(0, entryX);
            const visibleRight = Math.min(mediaSize.width, rectEndX);
            const visibleWidth = visibleRight - visibleLeft;
            const middleX = (visibleLeft + visibleRight) / 2;

            const drawBadge = (x: number, y: number, text: string, bgColor: string, textColor: string) => {
              context.save();
              context.font = "bold 9px var(--font-geist-mono), monospace";
              const textWidth = context.measureText(text).width;
              const padX = 6;
              const padY = 3;
              const badgeW = textWidth + padX * 2;
              const badgeH = 14;
              const badgeX = x - badgeW / 2;
              const badgeY = y - badgeH / 2;

              context.fillStyle = bgColor;
              context.beginPath();
              if (context.roundRect) {
                context.roundRect(badgeX, badgeY, badgeW, badgeH, 3);
              } else {
                context.rect(badgeX, badgeY, badgeW, badgeH);
              }
              context.fill();

              context.fillStyle = textColor;
              context.textAlign = "center";
              context.textBaseline = "middle";
              context.fillText(text, x, y);
              context.restore();
            };

            if (visibleWidth > 40) {
              if (lossHeight > 16) {
                drawBadge(middleX, lossYStart + lossHeight / 2, `SL: -${lossPct.toFixed(2)}%`, "rgba(220, 38, 38, 0.75)", "#ffffff");
              }
              if (profitHeight > 16) {
                const farPct = this.tp2Price ? tp2Pct : tp1Pct;
                drawBadge(middleX, profitYStart + profitHeight / 2, `TP: +${farPct.toFixed(2)}%`, "rgba(5, 150, 105, 0.75)", "#ffffff");
              }
            }

            context.restore();
          });
        }
      })
    };
  }

  attached(param: any) {
    this._series = param.series;
    this._chart = param.chart;
  }

  detached() {
    this._series = null;
    this._chart = null;
  }

  paneViews() {
    return [this._paneView];
  }

  priceAxisViews() {
    return [];
  }

  timeAxisViews() {
    return [];
  }
}

function alignTimestampToTimeframe(timestamp: number, timeframe: string): number {
  const date = new Date(timestamp * 1000);
  if (timeframe.endsWith("m")) {
    const minutes = parseInt(timeframe);
    const m = Math.floor(date.getUTCMinutes() / minutes) * minutes;
    date.setUTCMinutes(m, 0, 0);
  } else if (timeframe.endsWith("h")) {
    const hours = parseInt(timeframe);
    const h = Math.floor(date.getUTCHours() / hours) * hours;
    date.setUTCMinutes(0, 0, 0);
    date.setUTCHours(h);
  } else if (timeframe.endsWith("d")) {
    date.setUTCHours(0, 0, 0, 0);
  }
  return Math.floor(date.getTime() / 1000);
}

type InteractiveChartProps = {
  selectedSymbol?: string;
  selectedTrade?: any;
  onSelectSymbol?: (symbol: string) => void;
};

export function InteractiveChart({ selectedSymbol, selectedTrade, onSelectSymbol }: InteractiveChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const fundingSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const predictedFundingSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersPluginRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const candlesRef = useRef<any[]>([]);
  const smcPrimitiveRef = useRef<any>(null);
  const [showSMC, setShowSMC] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);

  const { data: positions } = usePositions();
  const { data: orders } = useOrders();
  const { data: config } = useConfig();
  const { data: history } = useHistory(200);

  const [activeSymbol, setActiveSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("15m");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showFundingRate, setShowFundingRate] = useState(true);

  const { data: serverSmc } = useSmcSignals(activeSymbol, timeframe, showSMC);

  // HUD Legend / Floating Overlays States
  const [latestCandle, setLatestCandle] = useState<any | null>(null);
  const [latestFunding, setLatestFunding] = useState<number | null>(null);
  const [latestPredicted, setLatestPredicted] = useState<number | null>(null);

  const [hoveredCandle, setHoveredCandle] = useState<any | null>(null);
  const [hoveredFunding, setHoveredFunding] = useState<number | null>(null);
  const [hoveredPredicted, setHoveredPredicted] = useState<number | null>(null);

  // Sync with external selected symbol from page/table selection
  useEffect(() => {
    if (selectedSymbol) {
      const normalized = selectedSymbol.replace("/", "").replace(":", "");
      setActiveSymbol(normalized);
    }
  }, [selectedSymbol]);

  // Sync with external selected trade from history table selection
  useEffect(() => {
    if (selectedTrade) {
      const normalized = selectedTrade.symbol.replace("/", "").replace(":", "");
      setActiveSymbol(normalized);
      setTimeframe("15m"); // Default to 15m for historical SMC trades

      const openedSec = Math.floor(new Date(selectedTrade.opened_at).getTime() / 1000);
      const closedSec = selectedTrade.closed_at
        ? Math.floor(new Date(selectedTrade.closed_at).getTime() / 1000)
        : Math.floor(Date.now() / 1000);

      const margin = 15 * 900; // 15m candle margin

      setTimeout(() => {
        if (chartRef.current) {
          chartRef.current.timeScale().setVisibleRange({
            from: (openedSec - margin) as any,
            to: (closedSec + margin) as any,
          });
        }
      }, 1000);
    }
  }, [selectedTrade]);

  // Extract config symbols to populate dropdown
  const symbolOptions = Array.from(
    new Set([
      "BTC",
      "ETH",
      "SOL",
      "TRX",
      "XRP",
      ...(config?.symbols?.map((s) => s.split(/[\/:]/)[0].replace(/USDT$/i, "")) ?? []),
      ...(positions?.map((p) => p.symbol.split(/[\/:]/)[0].replace(/USDT$/i, "")) ?? []),
      ...(orders?.map((o) => o.symbol.split(/[\/:]/)[0].replace(/USDT$/i, "")) ?? []),
    ])
  )
    .filter(Boolean)
    .map((sym) => `${sym.toUpperCase()}USDT`);

  // Re-fetch data and re-initialize chart when symbol, timeframe, or showFundingRate shifts
  useEffect(() => {
    if (!chartContainerRef.current) return;
    setIsLoading(true);
    setError(null);

    // 1. Initialize Lightweight Chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: terminal.chrome.bg },
        textColor: terminal.chrome.text, // zinc-400
        fontSize: 10,
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { color: terminal.chrome.grid },
        horzLines: { color: terminal.chrome.grid },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: terminal.chrome.crosshair, // zinc-700
          labelBackgroundColor: terminal.chrome.label,
        },
        horzLine: {
          color: terminal.chrome.crosshair,
          labelBackgroundColor: terminal.chrome.label,
        },
      },
      rightPriceScale: {
        borderColor: terminal.chrome.label,
        autoScale: true,
      },
      timeScale: {
        borderColor: terminal.chrome.label,
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // 2. Add Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: terminal.chart.bull,
      downColor: terminal.chart.bear,
      borderUpColor: terminal.chart.bull,
      borderDownColor: terminal.chart.bear,
      wickUpColor: terminal.chart.bull,
      wickDownColor: terminal.chart.bear,
    });
    candleSeriesRef.current = candleSeries;
    markersPluginRef.current = createSeriesMarkers(candleSeries);

    // Apply custom scale vertical partitions for multi-pane alignment
    chart.priceScale("right").applyOptions({
      scaleMargins: showFundingRate
        ? { top: 0.05, bottom: 0.45 } // Leave bottom 45% for the two indicators
        : { top: 0.05, bottom: 0.05 },
    });

    // 2b. Add Histograms for Coinalyze-style actual and predicted funding rates
    let fundingSeries: any = null;
    let predictedFundingSeries: any = null;

    if (showFundingRate) {
      fundingSeries = chart.addSeries(HistogramSeries, {
        priceFormat: {
          type: "custom",
          formatter: (val: number) => val.toFixed(5) + "%",
        },
        priceScaleId: "left",
      });
      fundingSeriesRef.current = fundingSeries;

      predictedFundingSeries = chart.addSeries(HistogramSeries, {
        priceFormat: {
          type: "custom",
          formatter: (val: number) => val.toFixed(5) + "%",
        },
        priceScaleId: "predicted-scale",
      });
      predictedFundingSeriesRef.current = predictedFundingSeries;

      // Configure Left price scale (Settled Funding Rate middle pane)
      chart.priceScale("left").applyOptions({
        scaleMargins: {
          top: 0.58,
          bottom: 0.23,
        },
        borderVisible: false,
        visible: true,
      });

      // Configure Custom price scale (Predicted Funding Rate bottom pane)
      chart.priceScale("predicted-scale").applyOptions({
        scaleMargins: {
          top: 0.79,
          bottom: 0.02,
        },
        borderVisible: false,
        visible: false, // Keep layout clean and neat, values displayed in floating legend HUD
      });
    } else {
      fundingSeriesRef.current = null;
      predictedFundingSeriesRef.current = null;
    }

    // 3. Handle responsive resizing smoothly
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !entries[0]) return;
      const { width, height } = entries[0].contentRect;
      chart.resize(width, height);
    });
    resizeObserver.observe(chartContainerRef.current);

    // 4. Fetch historical market data from Binance Futures in parallel
    const controller = new AbortController();
    const fetchHistory = async () => {
      try {
        let url = `https://fapi.binance.com/fapi/v1/klines?symbol=${activeSymbol}&interval=${timeframe}&limit=1000`;
        
        if (selectedTrade && selectedTrade.symbol.replace("/", "").replace(":", "") === activeSymbol) {
          const openedMs = new Date(selectedTrade.opened_at).getTime();
          let candleDurationMs = 15 * 60000; // default 15m
          if (timeframe === "1m") candleDurationMs = 60000;
          else if (timeframe === "5m") candleDurationMs = 5 * 60000;
          else if (timeframe === "15m") candleDurationMs = 15 * 60000;
          else if (timeframe === "1h") candleDurationMs = 60 * 60000;
          else if (timeframe === "4h") candleDurationMs = 4 * 60 * 60000;
          else if (timeframe === "1d") candleDurationMs = 24 * 60 * 60000;
          
          const startMs = openedMs - 100 * candleDurationMs;
          url += `&startTime=${Math.floor(startMs)}`;
        }

        const [klineRes, fundingRes, predictedRes] = await Promise.all([
          fetch(url, { signal: controller.signal }),
          showFundingRate
            ? fetch(`https://fapi.binance.com/fapi/v1/fundingRate?symbol=${activeSymbol}&limit=1000`, { signal: controller.signal })
            : Promise.resolve(null),
          showFundingRate
            ? fetch(`https://fapi.binance.com/fapi/v1/premiumIndexKlines?symbol=${activeSymbol}&interval=${timeframe}&limit=1000`, { signal: controller.signal })
            : Promise.resolve(null),
        ]);

        if (!klineRes.ok) throw new Error(`Binance returned HTTP ${klineRes.status}`);
        const klineData = await klineRes.json();
        
        const cdata = klineData.map((d: any) => ({
          time: Math.floor(d[0] / 1000) as any,
          open: parseFloat(d[1]),
          high: parseFloat(d[2]),
          low: parseFloat(d[3]),
          close: parseFloat(d[4]),
        }));

        candleSeries.setData(cdata);
        candlesRef.current = cdata;

        // Update latest candle HUD state
        if (cdata.length > 0) {
          const lastC = cdata[cdata.length - 1];
          const change = lastC.close - lastC.open;
          const changePercent = (change / lastC.open) * 100;
          setLatestCandle({
            open: lastC.open,
            high: lastC.high,
            low: lastC.low,
            close: lastC.close,
            change,
            changePercent,
          });
        }

        // Set settled historical funding rates
        if (fundingRes && fundingRes.ok && fundingSeries) {
          const fundingData = await fundingRes.json();
          const fdata = fundingData.map((item: any) => {
            const rate = parseFloat(item.fundingRate) * 100; // e.g. 0.01%
            return {
              time: Math.floor(item.fundingTime / 1000) as any,
              value: rate,
              color: rate >= 0 ? "rgba(16, 185, 129, 0.75)" : "rgba(239, 68, 68, 0.75)",
            };
          });

          // Deduplicate and sort chronologically
          const uniqueFdata: any[] = [];
          const seenTimes = new Set();
          for (const item of fdata) {
            if (!seenTimes.has(item.time)) {
              seenTimes.add(item.time);
              uniqueFdata.push(item);
            }
          }
          uniqueFdata.sort((a, b) => a.time - b.time);
          fundingSeries.setData(uniqueFdata);

          if (uniqueFdata.length > 0) {
            setLatestFunding(uniqueFdata[uniqueFdata.length - 1].value);
          }
        } else {
          setLatestFunding(null);
        }

        // Set high-frequency predicted funding rates (premium index close)
        if (predictedRes && predictedRes.ok && predictedFundingSeries) {
          const predictedData = await predictedRes.json();
          const pdata = predictedData.map((item: any) => {
            const rate = parseFloat(item[4]) * 100; // premium index close as %
            return {
              time: Math.floor(item[0] / 1000) as any,
              value: rate,
              color: rate >= 0 ? "rgba(16, 185, 129, 0.75)" : "rgba(239, 68, 68, 0.75)",
            };
          });

          // Deduplicate and sort chronologically
          const uniquePdata: any[] = [];
          const seenTimes = new Set();
          for (const item of pdata) {
            if (!seenTimes.has(item.time)) {
              seenTimes.add(item.time);
              uniquePdata.push(item);
            }
          }
          uniquePdata.sort((a, b) => a.time - b.time);
          predictedFundingSeries.setData(uniquePdata);

          if (uniquePdata.length > 0) {
            setLatestPredicted(uniquePdata[uniquePdata.length - 1].value);
          }
        } else {
          setLatestPredicted(null);
        }

        chart.timeScale().fitContent();
        setIsLoading(false);
      } catch (err: any) {
        if (err.name !== "AbortError") {
          console.error("Failed to fetch data from Binance:", err);
          setError("Failed to fetch historical chart data from Binance Futures.");
          setIsLoading(false);
        }
      }
    };

    fetchHistory();

    // 5. Connect to Live Binance Futures Websocket
    const wsUrl = `wss://fstream.binance.com/ws/${activeSymbol.toLowerCase()}@kline_${timeframe}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    setWsConnected(false);
    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.e === "kline") {
          const k = msg.k;
          const candle = {
            time: Math.floor(k.t / 1000) as any,
            open: parseFloat(k.o),
            high: parseFloat(k.h),
            low: parseFloat(k.l),
            close: parseFloat(k.c),
          };
          candleSeries.update(candle);

          // Update latest HUD state dynamically
          const change = candle.close - candle.open;
          const changePercent = (change / candle.open) * 100;
          setLatestCandle({
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
            change,
            changePercent,
          });
        }
      } catch (e) {
        console.error("Error processing websocket message:", e);
      }
    };

    // 6. Subscribe to Crosshair Move for real-time Hover Info Overlay
    chart.subscribeCrosshairMove((param) => {
      if (
        !param.time ||
        !param.point ||
        param.point.x < 0 ||
        param.point.y < 0
      ) {
        setHoveredCandle(null);
        setHoveredFunding(null);
        setHoveredPredicted(null);
        return;
      }

      // Candlestick Hover data
      const cData = param.seriesData.get(candleSeries);
      if (cData) {
        const c = cData as any;
        const change = c.close - c.open;
        const changePercent = c.open ? (change / c.open) * 100 : 0;
        setHoveredCandle({
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          change,
          changePercent,
        });
      } else {
        setHoveredCandle(null);
      }

      // Settled Funding Rate Hover data
      if (fundingSeries) {
        const fData = param.seriesData.get(fundingSeries);
        if (fData) {
          setHoveredFunding((fData as any).value);
        } else {
          setHoveredFunding(null);
        }
      }

      // Predicted Funding Rate Hover data
      if (predictedFundingSeries) {
        const pData = param.seriesData.get(predictedFundingSeries);
        if (pData) {
          setHoveredPredicted((pData as any).value);
        } else {
          setHoveredPredicted(null);
        }
      }
    });

    // 7. Cleanup connections and chart instances
    return () => {
      controller.abort();
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      resizeObserver.disconnect();
      chart.removeSeries(candleSeries);
      if (fundingSeries) chart.removeSeries(fundingSeries);
      if (predictedFundingSeries) chart.removeSeries(predictedFundingSeries);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      fundingSeriesRef.current = null;
      predictedFundingSeriesRef.current = null;
      markersPluginRef.current = null;
    };
  }, [activeSymbol, timeframe, showFundingRate]);

  // 8. Render position pricing overlays (Entry, TP, SL)
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries) return;

    const activeLines: any[] = [];
    let positionPrimitive: any = null;

    const activePos = positions?.find(
      (p) => p.symbol.replace("/", "").replace(":", "") === activeSymbol
    );

    const histTrade = selectedTrade && selectedTrade.symbol.replace("/", "").replace(":", "") === activeSymbol ? selectedTrade : null;
    const displayPos = activePos || histTrade;

    if (displayPos) {
      const isLong = displayPos.direction === "LONG";
      const rawEntryTime = Math.floor(new Date(displayPos.opened_at).getTime() / 1000);
      const rawExitTime = displayPos.closed_at ? Math.floor(new Date(displayPos.closed_at).getTime() / 1000) : null;
      
      const entryTime = alignTimestampToTimeframe(rawEntryTime, timeframe);
      const exitTime = rawExitTime ? alignTimestampToTimeframe(rawExitTime, timeframe) : null;
      
      if (entryTime && displayPos.entry) {
        positionPrimitive = new PositionOverlayPrimitive(
          displayPos.entry,
          displayPos.sl,
          displayPos.tp1,
          displayPos.tp2,
          Boolean(displayPos.tp1_hit),
          entryTime,
          exitTime,
          isLong
        );
        (candleSeries as any).attachPrimitive(positionPrimitive);
      }
    }

    const activeOrders = orders?.filter(
      (o) => o.symbol.replace("/", "").replace(":", "") === activeSymbol && o.price
    );

    activeOrders?.forEach((order) => {
      if (order.price) {
        const orderLine = candleSeries.createPriceLine({
          price: order.price,
          color: terminal.chrome.orderLine,
          lineWidth: 2,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: `${order.side.toUpperCase()} ${order.type.toUpperCase()}: ${n(order.price, 4)}`,
        });
        activeLines.push(orderLine);
      }
    });

    return () => {
      activeLines.forEach((line) => {
        try {
          candleSeries.removePriceLine(line);
        } catch (e) {}
      });
      if (positionPrimitive) {
        try {
          (candleSeries as any).detachPrimitive(positionPrimitive);
        } catch (e) {}
      }
    };
  }, [positions, orders, activeSymbol, selectedTrade, isLoading]);

  // 8b. Calculated SMC overlay (BOS/ChoCh · OB · FVG · premium/discount · PDH/PDL)
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;
    const detach = () => {
      if (smcPrimitiveRef.current) {
        try { (series as any).detachPrimitive(smcPrimitiveRef.current); } catch {}
        smcPrimitiveRef.current = null;
      }
    };
    detach();
    if (showSMC) {
      const hasServer = serverSmc && (serverSmc.structure?.length || serverSmc.obs?.length || serverSmc.fvgs?.length);
      const smc = hasServer
        ? serverSmc
        : (candlesRef.current.length > 30 ? computeSMC(candlesRef.current, timeframe) : null);
      if (smc) {
        const prim = new SmcOverlayPrimitive(smc);
        (series as any).attachPrimitive(prim);
        smcPrimitiveRef.current = prim;
      }
    }
    return detach;
  }, [showSMC, isLoading, activeSymbol, timeframe, serverSmc]);

  // 9. Render historical trade markers (ENTRY/EXIT)
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries || !history) return;

    const markers: any[] = [];
    const symbolTrades = history.filter(
      (t) => t.symbol.replace("/", "").replace(":", "") === activeSymbol
    );

    symbolTrades.forEach((t) => {
      const entryTime = Math.floor(new Date(t.opened_at).getTime() / 1000);
      const isLong = t.direction === "LONG";

      markers.push({
        time: entryTime as any,
        position: isLong ? "belowBar" : "aboveBar",
        shape: isLong ? "arrowUp" : "arrowDown",
        color: isLong ? terminal.chart.bull : terminal.chart.bear,
        text: `${isLong ? "L" : "S"} Entry: ${t.entry}`,
      });

      if (t.closed_at) {
        const exitTime = Math.floor(new Date(t.closed_at).getTime() / 1000);
        const pnl = t.pnl_usdt ?? 0;
        const profit = pnl >= 0;

        markers.push({
          time: exitTime as any,
          position: isLong ? "aboveBar" : "belowBar",
          shape: "circle",
          color: profit ? terminal.chart.bull : terminal.chart.bear,
          text: `Exit: ${t.reason ?? "RECONCILED"} (${t.pnl_pct != null ? (Number(t.pnl_pct) >= 0 ? "+" : "") + Number(t.pnl_pct).toFixed(2) : "—"}%)`,
        });
      }
    });

    markers.sort((a, b) => a.time - b.time);

    if (markersPluginRef.current) {
      markersPluginRef.current.setMarkers(markers);
    }
  }, [history, activeSymbol, isLoading]);

  const handleSymbolChange = (symbol: string) => {
    setActiveSymbol(symbol);
    if (onSelectSymbol) {
      onSelectSymbol(symbol);
    }
  };

  const displayCandle = hoveredCandle || latestCandle;
  const displayFunding = hoveredFunding !== null ? hoveredFunding : latestFunding;
  const displayPredicted = hoveredPredicted !== null ? hoveredPredicted : latestPredicted;

  return (
    <div className="border border-border bg-bg-elevated p-6 flex flex-col h-[520px]">
      {/* Chart Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4 font-mono">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-[10px] uppercase tracking-widest text-text-secondary block mb-1">
              Active Instrument
            </span>
            <select
              value={activeSymbol}
              onChange={(e) => handleSymbolChange(e.target.value)}
              className="bg-bg-surface border border-border text-text-primary px-3 py-1.5 text-xs focus:outline-none focus:border-accent-green/80 cursor-pointer rounded-sm"
            >
              {symbolOptions.map((sym) => (
                <option key={sym} value={sym}>
                  {sym.replace("USDT", " / USDT")}
                </option>
              ))}
            </select>
          </div>

          <div>
            <span className="text-[10px] uppercase tracking-widest text-text-secondary block mb-1">
              Timeframe
            </span>
            <div className="flex border border-border rounded-sm overflow-hidden bg-bg-surface">
              {["1m", "5m", "15m", "1h", "4h", "1d"].map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-3 py-1.5 text-xs transition-colors hover:bg-bg-elevated ${
                    timeframe === tf
                      ? "bg-accent-green/10 text-accent-green font-bold"
                      : "text-text-muted"
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="text-[10px] uppercase tracking-widest text-text-secondary block mb-1">
              Indicators
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setShowFundingRate(!showFundingRate)}
                className={`px-3 py-1.5 text-xs transition-colors border ${
                  showFundingRate
                    ? "bg-accent-green/10 text-accent-green border-accent-green/50 font-bold"
                    : "bg-bg-surface text-text-muted hover:bg-bg-elevated border-border"
                }`}
              >
                Funding Rate
              </button>
              <button
                onClick={() => setShowSMC(!showSMC)}
                className={`px-3 py-1.5 text-xs transition-colors border ${
                  showSMC
                    ? "bg-accent-green/10 text-accent-green border-accent-green/50 font-bold"
                    : "bg-bg-surface text-text-muted hover:bg-bg-elevated border-border"
                }`}
              >
                SMC Overlay
              </button>
            </div>
          </div>
        </div>

        <div className="text-right flex items-center gap-3">
          {isLoading ? (
            <div className="text-[11px] text-accent-green flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-green dot-breathe" />
              loading binance klines…
            </div>
          ) : wsConnected ? (
            <div className="text-[11px] text-text-muted flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-green ws-beat" />
              Binance live feed connected
            </div>
          ) : (
            <div className="text-[11px] text-accent-amber flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-amber dot-breathe" />
              reconnecting to binance…
            </div>
          )}
        </div>
      </div>

      {/* Main Chart Relative Container */}
      <div className="relative flex-1 min-h-0 w-full overflow-hidden border border-border bg-chrome-bg">
        
        {/* Floating Legend Overlays */}
        {/* 1. Candlestick HUD */}
        {displayCandle && (
          <div className="absolute top-2 left-3 z-10 font-mono text-[9px] bg-bg-elevated/90 px-2 py-1 border border-border flex flex-wrap items-center gap-x-2 gap-y-0.5 text-text-muted select-none">
            <span className="text-text-primary font-bold">{activeSymbol} · {timeframe} · Binance Futures</span>
            <span className="w-[1px] h-3 bg-border hidden sm:inline" />
            <span>O:<span className={displayCandle.close >= displayCandle.open ? "text-accent-green font-bold ml-0.5" : "text-accent-red font-bold ml-0.5"}>{displayCandle.open.toFixed(2)}</span></span>
            <span>H:<span className={displayCandle.close >= displayCandle.open ? "text-accent-green font-bold ml-0.5" : "text-accent-red font-bold ml-0.5"}>{displayCandle.high.toFixed(2)}</span></span>
            <span>L:<span className={displayCandle.close >= displayCandle.open ? "text-accent-green font-bold ml-0.5" : "text-accent-red font-bold ml-0.5"}>{displayCandle.low.toFixed(2)}</span></span>
            <span>C:<span className={displayCandle.close >= displayCandle.open ? "text-accent-green font-bold ml-0.5" : "text-accent-red font-bold ml-0.5"}>{displayCandle.close.toFixed(2)}</span></span>
            <span className={displayCandle.change >= 0 ? "text-accent-green font-bold ml-1" : "text-accent-red font-bold ml-1"}>
              {displayCandle.change >= 0 ? "+" : ""}{displayCandle.change.toFixed(2)} ({displayCandle.changePercent >= 0 ? "+" : ""}{displayCandle.changePercent.toFixed(2)}%)
            </span>
            {showSMC && (
              <>
                <span className="w-[1px] h-3 bg-border hidden sm:inline" />
                <span>SMC:<span className={`font-bold ml-0.5 uppercase ${
                  serverSmc?.source === "engine" ? "text-accent-green" :
                  serverSmc?.source === "heuristic" ? "text-blue-400" : "text-text-muted"
                }`}>
                  {serverSmc?.source || (candlesRef.current.length > 30 ? "client" : "loading")}
                </span></span>
              </>
            )}
          </div>
        )}

        {/* 2. Settled Funding Rate HUD */}
        {showFundingRate && displayFunding !== null && (
          <div className="absolute top-[58%] left-3 z-10 font-mono text-[9px] bg-bg-elevated/90 px-2 py-1 border border-border flex items-center gap-1.5 text-text-muted select-none">
            <span>Aggregated Funding Rate (Settled):</span>
            <span className={`font-bold ${displayFunding >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              {displayFunding >= 0 ? "+" : ""}{displayFunding.toFixed(5)}%
            </span>
          </div>
        )}

        {/* 3. Predicted Funding Rate HUD */}
        {showFundingRate && displayPredicted !== null && (
          <div className="absolute top-[79%] left-3 z-10 font-mono text-[9px] bg-bg-elevated/90 px-2 py-1 border border-border flex items-center gap-1.5 text-text-muted select-none">
            <span>Predicted Funding Rate (Real-time):</span>
            <span className={`font-bold ${displayPredicted >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              {displayPredicted >= 0 ? "+" : ""}{displayPredicted.toFixed(5)}%
            </span>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-bg-elevated/90 p-6 text-center">
            <p className="text-text-primary text-sm font-mono max-w-md">{error}</p>
            <button
              onClick={() => {
                setError(null);
                setActiveSymbol((s) => s); // Force reload
              }}
              className="mt-4 border border-border hover:border-text-secondary text-text-primary px-4 py-2 text-xs font-mono transition-colors"
            >
              Retry Connection
            </button>
          </div>
        )}

        <div ref={chartContainerRef} className="w-full h-full" />
      </div>
    </div>
  );
}
