"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, LineStyle, IChartApi, ISeriesApi, CandlestickSeries } from "lightweight-charts";
import { usePositions } from "@/hooks/usePositions";
import { useOrders } from "@/hooks/useOrders";
import { useConfig } from "@/hooks/useConfig";
import { n } from "@/lib/format";

type InteractiveChartProps = {
  selectedSymbol?: string;
  onSelectSymbol?: (symbol: string) => void;
};

export function InteractiveChart({ selectedSymbol, onSelectSymbol }: InteractiveChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const { data: positions } = usePositions();
  const { data: orders } = useOrders();
  const { data: config } = useConfig();

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
    };
  }, [activeSymbol, timeframe]);

  // 7. Render dynamic price level overlays (Entry, TP, SL) matching active positions and orders
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    if (!candleSeries) return;

    // Reset/clear any previous price lines before drawing new ones
    // Lightweight charts price lines don't have a clear all, so we manage them dynamically
    // The easiest and cleanest way in React wrapper is to store lines in a ref and delete them,
    // or let the series destroy/recreate handle it. Since we re-run this effect when positions/orders change:
    const activeLines: any[] = [];

    // Find if we have an active position for the current symbol
    const activePos = positions?.find(
      (p) => p.symbol.replace("/", "").replace(":", "") === activeSymbol
    );

    if (activePos) {
      // Entry Line (Yellow Dotted)
      const entryLine = candleSeries.createPriceLine({
        price: activePos.entry,
        color: "#F59E0B", // amber-500
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `ENTRY: ${n(activePos.entry, 4)}`,
      });
      activeLines.push(entryLine);

      // Stop Loss Line (Red Solid)
      if (activePos.sl) {
        const slLine = candleSeries.createPriceLine({
          price: activePos.sl,
          color: "#FF4D4D",
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: `SL: ${n(activePos.sl, 4)}`,
        });
        activeLines.push(slLine);
      }

      // Take Profit 1 (Green Solid)
      if (activePos.tp1) {
        const tp1Line = candleSeries.createPriceLine({
          price: activePos.tp1,
          color: "#00FF88",
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: `TP1: ${n(activePos.tp1, 4)} ${activePos.tp1_hit ? "(HIT)" : ""}`,
        });
        activeLines.push(tp1Line);
      }

      // Take Profit 2 (Green Solid)
      if (activePos.tp2) {
        const tp2Line = candleSeries.createPriceLine({
          price: activePos.tp2,
          color: "#059669", // emerald-600
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: `TP2: ${n(activePos.tp2, 4)}`,
        });
        activeLines.push(tp2Line);
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
    };
  }, [positions, orders, activeSymbol, isLoading]);

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
