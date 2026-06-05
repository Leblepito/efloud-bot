// API types and fetcher.

export type Status = {
  running: boolean;
  cycle_count: number;
  last_cycle_at: string | null;
  last_cycle_duration_ms: number;
  breaker_state: "OPEN" | "TRIPPED" | "HALTED" | "UNKNOWN";
  open_positions: number;
  config_path: string;
  testnet: boolean;
  dry_run: boolean;
  last_error: string | null;
};

export type OpenPosition = {
  symbol: string;
  direction: "LONG" | "SHORT";
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  size: number;
  current_price: number;
  unrealized_pct: number;
  unrealized_usdt: number;
  tp1_hit: boolean;
  opened_at: string;
};

export type OpenOrder = {
  id: string;
  symbol: string;
  type: string;          // "market" | "limit" | "stop_market" | "take_profit_market" | ...
  side: string;          // "buy" | "sell"
  price: number | null;
  stop_price: number | null;
  amount: number | null;
  filled: number | null;
  remaining: number | null;
  reduce_only: boolean;
  status: string;        // "open" | "closed" | ...
  timestamp: number | null;  // ms epoch
};

export type Trade = {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  entry: number;
  exit: number | null;
  sl: number;
  tp1: number;
  tp2: number;
  size: number;
  pnl_usdt: number | null;
  pnl_pct: number | null;
  reason: string | null;
  opened_at: string;
  closed_at: string | null;
  confluence: number | null;
  kronos_comment?: string;
  kronos_confidence?: number;
};

export type EquityPoint = {
  ts: string;
  balance: number;
  open_positions_count: number;
};

export type ConfigSnapshot = {
  config_path: string;
  exchange: { testnet: boolean; leverage: number; margin_mode: string; market_type: string };
  operation: { dry_run: boolean; check_interval_sec: number };
  risk: Record<string, unknown>;
  safety: Record<string, unknown>;
  symbols: string[];
};

export function getMockState() {
  if (typeof window === "undefined") return null;
  let stateStr = localStorage.getItem("efloud_mock_state");
  if (!stateStr) {
    const initialState = {
      running: true,
      cycle_count: 8421,
      last_cycle_at: new Date(Date.now() - 2000).toISOString(),
      last_cycle_duration_ms: 245,
      breaker_state: "OPEN" as const,
      open_positions: 2,
      config_path: "configs/config.yaml",
      testnet: true,
      dry_run: true,
      last_error: null,
      positions: [
        {
          symbol: "BTCUSDT",
          direction: "LONG" as const,
          entry: 67450.0,
          sl: 66500.0,
          tp1: 68800.0,
          tp2: 71000.0,
          size: 0.24,
          current_price: 68120.5,
          unrealized_pct: 0.99,
          unrealized_usdt: 160.92,
          tp1_hit: false,
          opened_at: new Date(Date.now() - 3600000 * 4).toISOString(),
        },
        {
          symbol: "SOLUSDT",
          direction: "SHORT" as const,
          entry: 164.2,
          sl: 168.5,
          tp1: 158.0,
          tp2: 150.0,
          size: 45.0,
          current_price: 161.85,
          unrealized_pct: 1.43,
          unrealized_usdt: 105.75,
          tp1_hit: false,
          opened_at: new Date(Date.now() - 3600000 * 2).toISOString(),
        }
      ],
      orders: [
        {
          id: "ord_1",
          symbol: "BTCUSDT",
          type: "limit",
          side: "sell",
          price: 68800.0,
          stop_price: null,
          amount: 0.12,
          filled: 0,
          remaining: 0.12,
          reduce_only: true,
          status: "open",
          timestamp: Date.now() - 14400000,
        },
        {
          id: "ord_2",
          symbol: "SOLUSDT",
          type: "limit",
          side: "buy",
          price: 158.0,
          stop_price: null,
          amount: 22.5,
          filled: 0,
          remaining: 22.5,
          reduce_only: true,
          status: "open",
          timestamp: Date.now() - 7200000,
        }
      ],
      trades: [
        {
          id: "tr_1",
          symbol: "BTCUSDT",
          direction: "LONG" as const,
          entry: 67100,
          exit: 68800,
          sl: 66200,
          tp1: 68800,
          tp2: 70500,
          size: 0.15,
          pnl_usdt: 255.00,
          pnl_pct: 2.53,
          reason: "TP1 Hit",
          opened_at: new Date(Date.now() - 3600000 * 12).toISOString(),
          closed_at: new Date(Date.now() - 3600000 * 10).toISOString(),
          confluence: 75,
          kronos_comment: "Kronos model forecast trajectory for BTCUSDT suggests a high-probability swing towards $70,500. Clear displacement verified above 4H market structure shift.",
          kronos_confidence: 88
        },
        {
          id: "tr_2",
          symbol: "ETHUSDT",
          direction: "SHORT" as const,
          entry: 3840,
          exit: 3750,
          sl: 3910,
          tp1: 3750,
          tp2: 3620,
          size: 1.5,
          pnl_usdt: 135.00,
          pnl_pct: 2.34,
          reason: "TP1 Hit",
          opened_at: new Date(Date.now() - 3600000 * 8).toISOString(),
          closed_at: new Date(Date.now() - 3600000 * 7).toISOString(),
          confluence: 68,
          kronos_comment: "ETHUSDT daily timeframe shows critical resistance at $3,900. Model identifies sell-side liquidity pools below $3,700, expecting short-term downside extension.",
          kronos_confidence: 82
        },
        {
          id: "tr_3",
          symbol: "LINKUSDT",
          direction: "LONG" as const,
          entry: 18.2,
          exit: 17.5,
          sl: 17.5,
          tp1: 19.5,
          tp2: 21.0,
          size: 150,
          pnl_usdt: -105.00,
          pnl_pct: -3.85,
          reason: "Stop Loss",
          opened_at: new Date(Date.now() - 3600000 * 6).toISOString(),
          closed_at: new Date(Date.now() - 3600000 * 5).toISOString(),
          confluence: 58,
          kronos_comment: "LINKUSDT entry had sub-optimal confluence. The model correctly flagged a high probability of stop loss hunting below $17.8, which was realized shortly after entry.",
          kronos_confidence: 65
        }
      ],
      config: {
        config_path: "configs/config.yaml",
        exchange: { testnet: true, leverage: 10, margin_mode: "cross", market_type: "future" },
        operation: { dry_run: true, check_interval_sec: 5 },
        risk: { max_risk_pct: 2.0, max_positions: 4 },
        safety: { max_daily_drawdown_pct: 5.0, breaker_cooldown_min: 30 },
        symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT"]
      },
      equity: [] as any[]
    };

    // Prepopulate equity points
    const equity = [];
    let balance = 10000;
    for (let i = 7; i >= 0; i--) {
      const ts = new Date(Date.now() - i * 24 * 3600 * 1000).toISOString();
      balance += i === 0 ? 0 : (Math.random() > 0.35 ? 1 : -1) * (200 + Math.random() * 300);
      equity.push({ ts, balance, open_positions_count: Math.floor(Math.random() * 3) });
    }
    initialState.equity = equity;

    localStorage.setItem("efloud_mock_state", JSON.stringify(initialState));
    return initialState;
  }
  return JSON.parse(stateStr);
}

export function saveMockState(state: any) {
  if (typeof window !== "undefined") {
    localStorage.setItem("efloud_mock_state", JSON.stringify(state));
  }
}

export function getMockData(url: string): any {
  const state = getMockState();
  if (!state) return null;

  if (url.startsWith("/api/status")) {
    if (state.running) {
      state.cycle_count += 1;
      state.last_cycle_at = new Date().toISOString();
      state.last_cycle_duration_ms = Math.floor(150 + Math.random() * 200);
      
      // Simulate small price changes in positions
      state.positions = state.positions.map((p: any) => {
        const change = (Math.random() - 0.49) * 0.002 * p.current_price;
        const newPrice = p.current_price + change;
        const pnlPct = p.direction === "LONG" 
          ? ((newPrice - p.entry) / p.entry) * 100 
          : ((p.entry - newPrice) / p.entry) * 100;
        const pnlUsdt = pnlPct * p.size * p.entry * 0.01;
        return {
          ...p,
          current_price: newPrice,
          unrealized_pct: pnlPct,
          unrealized_usdt: pnlUsdt
        };
      });
      saveMockState(state);
    }
    
    return {
      running: state.running,
      cycle_count: state.cycle_count,
      last_cycle_at: state.last_cycle_at,
      last_cycle_duration_ms: state.last_cycle_duration_ms,
      breaker_state: state.breaker_state,
      open_positions: state.positions.length,
      config_path: state.config_path,
      testnet: state.testnet,
      dry_run: state.dry_run,
      last_error: state.last_error,
    };
  }
  
  if (url.startsWith("/api/positions")) {
    return state.positions;
  }
  
  if (url.startsWith("/api/orders")) {
    return state.orders;
  }
  
  if (url.startsWith("/api/history")) {
    return state.trades;
  }
  
  if (url.startsWith("/api/config")) {
    return state.config;
  }
  
  if (url.startsWith("/api/equity")) {
    return state.equity;
  }
  
  if (url.includes("/api/ai/sentiment")) {
    return {
      last_updated: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
      macro_sentiment: "RISK_ON",
      confidence_score: 0.85,
      fear_and_greed: 74,
      bitcoin_trend: "BULLISH",
      reasoning: "Bitcoin has cleared major liquidity pools at $67,200 and reclaimed the 4-hour market structure shift zone. Funding rates remain flat, suggesting that the move is driven by spot buying rather than excessive leverage. Smart Money Concept bias remains bullish across medium and high timeframes."
    };
  }

  if (url.includes("/api/social/feeds")) {
    return {
      telegram: [
        {
          id: "t1",
          source: "telegram",
          author: "Efloud Public Channel",
          content: "BTC 4H structure shift confirmed on spot. Clear displacement on the breakout bar. Looking for a return to the Daily FVG at $68,100 to establish long positions. High timeframe bias is bullish.",
          timestamp: new Date(Date.now() - 45 * 60 * 1000).toISOString()
        },
        {
          id: "t2",
          source: "telegram",
          author: "Efloud VIP",
          content: "SOL has swept the equal lows at $161.5. Sub-15m displacement is starting. TP1 set at $168.0, stop loss placed below swing low. Manage risk carefully.",
          timestamp: new Date(Date.now() - 120 * 60 * 1000).toISOString()
        }
      ],
      twitter: [
        {
          id: "x1",
          source: "twitter",
          author: "@efloud_algo",
          content: "Market structure remains bullish for key majors. Liquidity sweeps on intraday timeframes are consistently being bought up. High confluence setups forming on majors. #SMC #Bitcoin",
          timestamp: new Date(Date.now() - 180 * 60 * 1000).toISOString()
        }
      ]
    };
  }

  if (url.includes("/api/social/research-snapshot")) {
    return {
      archive_count: 142,
      research_only: true,
      doctrine: [
        {
          feed_id: "doc_1",
          source: "telegram",
          symbols: ["BTCUSDT", "SOLUSDT"],
          timeframes: ["4h", "1d"],
          bias: "bullish",
          structure_terms: ["MSB", "BOS", "HH"],
          zones: ["FVG", "Order Block"],
          liquidity_terms: ["liquidity_sweep"],
          risk_terms: ["risk_management"],
          levels: [68100, 161.5],
          setup_recipe: ["market_structure_shift", "pullback", "fvg_reaction"],
          confidence: 0.82
        }
      ],
      hypotheses: [
        {
          id: "hyp_btc_fvg_rebound",
          title: "4H FVG Rebound Strategy",
          rationale: "Intraday displacement above swing highs with high volume, followed by a limit buy entry inside the 50% equilibrium level of the 4H FVG zone.",
          doctrine_tags: ["MSB", "FVG", "pullback"],
          candidate_config_patch: {
            risk: { "max_risk_pct": 2.5 },
            safety: { "breaker_cooldown_min": 15 }
          },
          metrics_to_watch: ["win_rate", "profit_factor"],
          risk: "MEDIUM_RISK"
        }
      ],
      research_runs: {
        hyp_btc_fvg_rebound: {
          verdict: "PASS",
          gates: {
            max_drawdown_gate: "PASSED",
            sharpe_ratio_gate: "PASSED"
          },
          doctrine_tags: ["MSB", "FVG"],
          run_dir: "runs/hyp_btc_fvg_rebound_20260602",
          run_date: "2026-06-02",
          deltas: { "max_risk_pct": 2.5 }
        }
      }
    };
  }

  if (url.includes("/api/market/funding-rates")) {
    return [
      {
        symbol: "BTCUSDT",
        funding_rate: 0.0001,
        mark_price: state.positions.find((p: any) => p.symbol === "BTCUSDT")?.current_price || 68120.5,
        index_price: (state.positions.find((p: any) => p.symbol === "BTCUSDT")?.current_price || 68120.5) - 5,
        next_funding_time: Date.now() + 3600000 * 4
      },
      {
        symbol: "ETHUSDT",
        funding_rate: 0.00015,
        mark_price: 3810.2,
        index_price: 3809.5,
        next_funding_time: Date.now() + 3600000 * 4
      },
      {
        symbol: "SOLUSDT",
        funding_rate: -0.00005,
        mark_price: state.positions.find((p: any) => p.symbol === "SOLUSDT")?.current_price || 161.85,
        index_price: (state.positions.find((p: any) => p.symbol === "SOLUSDT")?.current_price || 161.85) + 0.05,
        next_funding_time: Date.now() + 3600000 * 4
      },
      {
        symbol: "LINKUSDT",
        funding_rate: 0.00025,
        mark_price: 18.15,
        index_price: 18.1,
        next_funding_time: Date.now() + 3600000 * 4
      }
    ];
  }

  if (url.includes("/api/market/open-interest")) {
    const match = url.match(/[?&]symbol=([^&]+)/);
    const sym = match ? match[1] : "BTCUSDT";
    const basePrice = sym === "BTCUSDT" 
      ? (state.positions.find((p: any) => p.symbol === "BTCUSDT")?.current_price || 68120.5)
      : sym === "SOLUSDT"
      ? (state.positions.find((p: any) => p.symbol === "SOLUSDT")?.current_price || 161.85)
      : 100;
      
    return {
      symbol: sym,
      history: [
        { "timestamp": Date.now() - 3600 * 1000 * 5, "open_interest": 12500, "open_interest_value": 850000000, "price": basePrice * 0.99 },
        { "timestamp": Date.now() - 3600 * 1000 * 4, "open_interest": 12800, "open_interest_value": 870000000, "price": basePrice * 0.993 },
        { "timestamp": Date.now() - 3600 * 1000 * 3, "open_interest": 13100, "open_interest_value": 890000000, "price": basePrice * 0.996 },
        { "timestamp": Date.now() - 3600 * 1000 * 2, "open_interest": 13300, "open_interest_value": 910000000, "price": basePrice * 0.998 },
        { "timestamp": Date.now() - 3600 * 1000 * 1, "open_interest": 13600, "open_interest_value": 930000000, "price": basePrice }
      ],
      trend: "LONG_BUILDUP",
      trend_description: "Price and Open Interest are increasing simultaneously, indicating strong buying momentum.",
      trend_color: "emerald"
    };
  }

  return null;
}

export function handleMockPost(url: string, body?: any): any {
  const state = getMockState();
  if (!state) return { ok: false, success: false };

  if (url.includes("/api/bot/start")) {
    const already_running = state.running;
    state.running = true;
    state.last_error = null;
    saveMockState(state);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("efloud_ws_mock", { detail: { type: "bot_started", payload: {}, ts: new Date().toISOString() } }));
    }
    return { ok: true, running: true, already_running };
  }
  
  if (url.includes("/api/bot/stop")) {
    state.running = false;
    saveMockState(state);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("efloud_ws_mock", { detail: { type: "bot_stopped", payload: {}, ts: new Date().toISOString() } }));
    }
    return { ok: true, running: false };
  }

  if (url.includes("/api/bot/restart")) {
    state.running = true;
    state.last_error = null;
    saveMockState(state);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("efloud_ws_mock", { detail: { type: "bot_started", payload: {}, ts: new Date().toISOString() } }));
    }
    return { ok: true, running: true };
  }
  
  if (url.includes("/api/kill-switch")) {
    const closedCount = state.positions.length;
    state.running = false;
    state.positions.forEach((p: any) => {
      state.trades.unshift({
        id: "tr_" + Math.random().toString(36).substr(2, 9),
        symbol: p.symbol,
        direction: p.direction,
        entry: p.entry,
        exit: p.current_price,
        sl: p.sl,
        tp1: p.tp1,
        tp2: p.tp2,
        size: p.size,
        pnl_usdt: p.unrealized_usdt,
        pnl_pct: p.unrealized_pct,
        reason: "Kill Switch Triggered",
        opened_at: p.opened_at,
        closed_at: new Date().toISOString(),
        confluence: 70
      });
    });
    state.positions = [];
    state.orders = [];
    saveMockState(state);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("efloud_ws_mock", { detail: { type: "bot_stopped", payload: {}, ts: new Date().toISOString() } }));
    }
    return { ok: true, closed: closedCount };
  }
  
  if (url.includes("/api/config")) {
    if (body) {
      state.config = {
        ...state.config,
        ...body
      };
      saveMockState(state);
    }
    return { ok: true, success: true, config: state.config };
  }

  return { ok: true, success: true };
}

export async function jsonFetcher<T>(url: string): Promise<T> {
  if (typeof window !== "undefined" && localStorage.getItem("efloud_demo_mode") === "true") {
    return getMockData(url) as unknown as T;
  }
  const r = await fetch(url, { credentials: "include" });
  if (r.status === 401) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("unauthorized");
  }
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as T;
}

export async function postJson<T>(url: string, body?: unknown): Promise<T> {
  if (typeof window !== "undefined" && localStorage.getItem("efloud_demo_mode") === "true") {
    return handleMockPost(url, body) as unknown as T;
  }
  const r = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => "");
    throw new Error(`HTTP ${r.status}: ${txt}`);
  }
  return (await r.json()) as T;
}

// Global fetch override for High-Fidelity Demo Mode
if (typeof window !== "undefined") {
  if (!(window as any).__efloud_fetch_mocked) {
    (window as any).__efloud_fetch_mocked = true;
    const originalFetch = window.fetch;
    window.fetch = async function (input, init) {
      if (localStorage.getItem("efloud_demo_mode") === "true") {
        const url = typeof input === "string" 
          ? input 
          : input instanceof URL 
          ? input.toString() 
          : (input as Request).url;
          
        if (url.includes("/api/")) {
          // Find path slice starting with /api/
          const apiIndex = url.indexOf("/api/");
          const apiPath = url.substring(apiIndex);
          
          let data;
          if (init?.method === "POST") {
            let body;
            if (init.body) {
              try {
                body = JSON.parse(init.body as string);
              } catch (e) {}
            }
            data = handleMockPost(apiPath, body);
          } else {
            data = getMockData(apiPath);
          }
          
          return new Response(JSON.stringify(data), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          });
        }
      }
      return originalFetch.apply(this, arguments as any);
    };
  }
}
