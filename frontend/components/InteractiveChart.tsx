"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, LineStyle, IChartApi, ISeriesApi, CandlestickSeries, createSeriesMarkers } from "lightweight-charts";
import { usePositions } from "@/hooks/usePositions";
import { useOrders } from "@/hooks/useOrders";
import { useConfig } from "@/hooks/useConfig";
import { useHistory } from "@/hooks/useHistory";
import { n } from "@/lib/format";

// TradingView-style Long/Short Position Drawing Overlay Primitive
class PositionOverlayPrimitive {
  private _series: any = null;
  private _chart: any = null;
  private _paneView: any;

  constructor(
    private entryPrice: number,
    private slPrice: number,
    private tpPrice: number,
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
            const tpY = this.tpPrice ? this._series.priceToCoordinate(this.tpPrice) : null;

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
              if (tpY !== null) {
                profitHeight = entryY - tpY;
                profitYStart = tpY;
              }
            } else {
              if (slY !== null) {
                lossHeight = entryY - slY;
                lossYStart = slY;
              }
              if (tpY !== null) {
                profitHeight = tpY - entryY;
                profitYStart = entryY;
              }
            }

            context.save();

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
            const profitPct = this.entryPrice ? Math.abs(((this.tpPrice - this.entryPrice) / this.entryPrice) * 100) : 0;

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

            // Take Profit Line
            if (tpY !== null) {
              context.strokeStyle = "rgba(16, 185, 129, 0.4)";
              context.beginPath();
              context.moveTo(entryX, tpY);
              context.lineTo(rectEndX, tpY);
              context.stroke();

              drawPriceTag(tpY, `TP: ${this.tpPrice.toFixed(4)} (+${profitPct.toFixed(2)}%)`, "rgba(5, 150, 105, 0.85)");
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
                drawBadge(middleX, profitYStart + profitHeight / 2, `TP: +${profitPct.toFixed(2)}%`, "rgba(5, 150, 105, 0.75)", "#ffffff");
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
  const markersPluginRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const { data: positions } = usePositions();
  const { data: orders } = useOrders();
  const { data: config } = useConfig();
  const { data: history } = useHistory(200);

  const [activeSymbol, setActiveSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("15m");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Sync with external selected symbol from page/table selection
  useEffect(() => {
    if (selectedSymbol) {
      // Normalize from CCXT format "BTC/USDT" or "TRX/USDT" to "BTCUSDT" or "TRXUSDT"
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

      // Calculate timestamps in seconds
      const openedSec = Math.floor(new Date(selectedTrade.opened_at).getTime() / 1000);
      const closedSec = selectedTrade.closed_at
        ? Math.floor(new Date(selectedTrade.closed_at).getTime() / 1000)
        : Math.floor(Date.now() / 1000);

      // Centered focus with margin (e.g. 15 candles on each side)
      // 15m candle = 900 seconds
      const margin = 15 * 900;

      // Small timeout to allow the chart to fetch historical candles first
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

  // Extract config symbols to populate dropdown, dynamically adding symbols with active positions or orders
  const symbolOptions = Array.from(
    new Set([
      "BTCUSDT",
      "ETHUSDT",
      "SOLUSDT",
      "TRXUSDT",
      "XRPUSDT",
      ...(config?.symbols?.map((s) => s.replace("/", "").replace(":", "").replace("USDT", "")) ?? []),
      ...(positions?.map((p) => p.symbol.replace("/", "").replace(":", "").replace("USDT", "")) ?? []),
      ...(orders?.map((o) => o.symbol.replace("/", "").replace(":", "").replace("USDT", "")) ?? []),
    ])
  ).map((sym) => `${sym}USDT`);

  // Re-fetch data and re-initialize chart when symbol or timeframe changes
  useEffect(() => {
    if (!chartContainerRef.current) return;
    setIsLoading(true);
    setError(null);

    // 1. Initialize Lightweight Chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#09090b" }, // %100 Dark Mode background
        textColor: "#a1a1aa", // zinc-400
        fontSize: 11,
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { color: "#18181b" }, // zinc-900 border lines
        horzLines: { color: "#18181b" },
      },
      crosshair: {
        mode: 1, // Magnet-like crosshair
        vertLine: {
          color: "#3f3f46", // zinc-700
          labelBackgroundColor: "#18181b",
        },
        horzLine: {
          color: "#3f3f46",
          labelBackgroundColor: "#18181b",
        },
      },
      rightPriceScale: {
        borderColor: "#27272a", // zinc-800
        autoScale: true,
      },
      timeScale: {
        borderColor: "#27272a",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // 2. Add Candlestick Series using v5 Series API
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#00FF88", // Emerald Green for up candles
      downColor: "#FF4D4D", // Vivid Rose/Red for down candles
      borderUpColor: "#00FF88",
      borderDownColor: "#FF4D4D",
      wickUpColor: "#00FF88",
      wickDownColor: "#FF4D4D",
    });
    candleSeriesRef.current = candleSeries;
    markersPluginRef.current = createSeriesMarkers(candleSeries);

    // 3. Handle responsive resizing smoothly
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !entries[0]) return;
      const { width, height } = entries[0].contentRect;
      chart.resize(width, height);
    });
    resizeObserver.observe(chartContainerRef.current);

    // 4. Fetch Historical Candlesticks from Binance Futures public REST API
    const controller = new AbortController();
    const fetchHistory = async () => {
      try {
        const res = await fetch(
          `https://fapi.binance.com/fapi/v1/klines?symbol=${activeSymbol}&interval=${timeframe}&limit=200`,
          { signal: controller.signal }
        );
        if (!res.ok) throw new Error(`Binance returned HTTP ${res.status}`);
        const data = await res.json();
        
        const cdata = data.map((d: any) => ({
          time: Math.floor(d[0] / 1000) as any,
          open: parseFloat(d[1]),
          high: parseFloat(d[2]),
          low: parseFloat(d[3]),
          close: parseFloat(d[4]),
        }));

        candleSeries.setData(cdata);
        chart.timeScale().fitContent();
        setIsLoading(false);
      } catch (err: any) {
        if (err.name !== "AbortError") {
          console.error("Failed to fetch klines from Binance:", err);
          setError("Failed to fetch historical chart data from Binance Futures.");
          setIsLoading(false);
        }
      }
    };

    fetchHistory();

    // 5. Connect to Live Binance Futures Websocket for real-time tick stream
    const wsUrl = `wss://fstream.binance.com/ws/${activeSymbol.toLowerCase()}@kline_${timeframe}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

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
        }
      } catch (e) {
        console.error("Error processing websocket message:", e);
      }
    };

    ws.onerror = (e) => {
      console.warn("Binance WebSocket encountered an error:", e);
    };

    ws.onclose = () => {
      // Optional auto-reconnect logic or logging
    };

    // 6. Cleanup connections, chart instance, and observers on unmount or dependency shift
    return () => {
      controller.abort();
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      resizeObserver.disconnect();
      chart.removeSeries(candleSeries);
      chart.remove(); // v5 cleanup method is chart.remove()
      chartRef.current = null;
      candleSeriesRef.current = null;
      markersPluginRef.current = null;
    };
  }, [activeSymbol, timeframe]);

  // 7. Render dynamic price level overlays (Entry, TP, SL) matching active positions, orders, or selected historical trade
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries) return;

    // Reset/clear any previous price lines before drawing new ones
    const activeLines: any[] = [];
    let positionPrimitive: any = null;

    // Find if we have an active position for the current symbol
    const activePos = positions?.find(
      (p) => p.symbol.replace("/", "").replace(":", "") === activeSymbol
    );

    // Or check if we have a selected historical trade for the current symbol
    const histTrade = selectedTrade && selectedTrade.symbol.replace("/", "").replace(":", "") === activeSymbol ? selectedTrade : null;

    const displayPos = activePos || histTrade;

    if (displayPos) {
      // Attach Position Overlay Primitive (Shaded rectangles)
      const isLong = displayPos.direction === "LONG";
      const rawEntryTime = Math.floor(new Date(displayPos.opened_at).getTime() / 1000);
      const rawExitTime = displayPos.closed_at ? Math.floor(new Date(displayPos.closed_at).getTime() / 1000) : null;
      
      const entryTime = alignTimestampToTimeframe(rawEntryTime, timeframe);
      const exitTime = rawExitTime ? alignTimestampToTimeframe(rawExitTime, timeframe) : null;
      
      const targetTp = displayPos.tp2 || displayPos.tp1;

      if (entryTime && displayPos.entry) {
        positionPrimitive = new PositionOverlayPrimitive(
          displayPos.entry,
          displayPos.sl,
          targetTp,
          entryTime,
          exitTime,
          isLong
        );
        (candleSeries as any).attachPrimitive(positionPrimitive);
      }
    }

    // Find and draw active open orders for the current symbol (Limit Orders)
    const activeOrders = orders?.filter(
      (o) => o.symbol.replace("/", "").replace(":", "") === activeSymbol && o.price
    );

    activeOrders?.forEach((order) => {
      if (order.price) {
        const orderLine = candleSeries.createPriceLine({
          price: order.price,
          color: "#6366F1", // indigo-500
          lineWidth: 2, // LineWidth must be a strict integer (1, 2, 3, or 4)
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: `${order.side.toUpperCase()} ${order.type.toUpperCase()}: ${n(order.price, 4)}`,
        });
        activeLines.push(orderLine);
      }
    });

    // Cleanup active lines when dependencies change
    return () => {
      activeLines.forEach((line) => {
        try {
          candleSeries.removePriceLine(line);
        } catch (e) {
          // Safe fail if already cleaned up
        }
      });
      if (positionPrimitive) {
        try {
          (candleSeries as any).detachPrimitive(positionPrimitive);
        } catch (e) {
          // Safe fail if already cleaned up
        }
      }
    };
  }, [positions, orders, activeSymbol, selectedTrade, isLoading]);

  // 8. Render historical trade markers (ENTRY/EXIT arrows & circles) on candles
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries || !history) return;

    const markers: any[] = [];

    // Filter recent trades that belong to the currently active symbol
    const symbolTrades = history.filter(
      (t) => t.symbol.replace("/", "").replace(":", "") === activeSymbol
    );

    symbolTrades.forEach((t) => {
      const entryTime = Math.floor(new Date(t.opened_at).getTime() / 1000);
      const isLong = t.direction === "LONG";

      // Entry Marker (Green Up Arrow for Long, Red Down Arrow for Short)
      markers.push({
        time: entryTime as any,
        position: isLong ? "belowBar" : "aboveBar",
        shape: isLong ? "arrowUp" : "arrowDown",
        color: isLong ? "#00FF88" : "#FF4D4D",
        text: `${isLong ? "L" : "S"} Entry: ${t.entry}`,
      });

      // Exit Marker (Circle)
      if (t.closed_at) {
        const exitTime = Math.floor(new Date(t.closed_at).getTime() / 1000);
        const pnl = t.pnl_usdt ?? 0;
        const profit = pnl >= 0;

        markers.push({
          time: exitTime as any,
          position: isLong ? "aboveBar" : "belowBar",
          shape: "circle",
          color: profit ? "#00FF88" : "#FF4D4D",
          text: `Exit: ${t.reason ?? "RECONCILED"} (${t.pnl_pct != null ? (t.pnl_pct >= 0 ? "+" : "") + t.pnl_pct.toFixed(2) : "—"}%)`,
        });
      }
    });

    // Sort markers chronologically (Lightweight Charts requirement!)
    markers.sort((a, b) => a.time - b.time);

    if (markersPluginRef.current) {
      markersPluginRef.current.setMarkers(markers);
    }
  }, [history, activeSymbol, isLoading]);

  const handleSymbolChange = (symbol: string) => {
    setActiveSymbol(symbol);
    if (onSelectSymbol) {
      // Pass back in default format (add slash for page component sync if necessary)
      onSelectSymbol(symbol);
    }
  };

  return (
    <div className="border border-border bg-bg-elevated p-6 flex flex-col h-[500px]">
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
        </div>

        <div className="text-right flex items-center gap-3">
          {isLoading && (
            <div className="text-[11px] text-accent-green animate-pulse flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-green"></span>
              loading binance klines…
            </div>
          )}
          {!isLoading && (
            <div className="text-[11px] text-text-muted flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-green animate-ringExpand"></span>
              Binance live feed connected
            </div>
          )}
        </div>
      </div>

      {/* Main Chart Container */}
      <div className="relative flex-1 min-h-0 w-full rounded-sm overflow-hidden border border-border">
        {error && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-bg-elevated/90 p-6 text-center">
            <span className="text-accent-red text-2xl mb-2">⚠️</span>
            <p className="text-text-primary text-sm font-mono max-w-md">{error}</p>
            <button
              onClick={() => {
                setError(null);
                setActiveSymbol((s) => s); // Force reload
              }}
              className="mt-4 border border-border hover:border-text-secondary text-text-primary px-4 py-2 text-xs font-mono rounded-sm transition-colors"
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
