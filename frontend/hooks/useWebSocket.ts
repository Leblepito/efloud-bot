"use client";

import { useEffect, useRef } from "react";
import { getMockState, saveMockState } from "@/lib/api";

export type WsEvent = {
  type:
    | "hello"
    | "cycle_start"
    | "cycle_end"
    | "position_opened"
    | "position_closed"
    | "tp1_hit"
    | "breaker_change"
    | "bot_started"
    | "bot_stopped"
    | "error";
  payload: Record<string, unknown>;
  ts: string;
};

type Listener = (evt: WsEvent) => void;
type StatusListener = (open: boolean) => void;

export function useWebSocket(onEvent: Listener, onStatus?: StatusListener) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;
  const statusRef = useRef(onStatus);
  statusRef.current = onStatus;

  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem("efloud_demo_mode") === "true") {
      statusRef.current?.(true);
      // Mock event loop for demo mode
      const onMockEvent = (e: Event) => {
        const customEvt = e as CustomEvent<WsEvent>;
        handlerRef.current(customEvt.detail);
      };
      window.addEventListener("efloud_ws_mock", onMockEvent);

      // Periodically trigger background cycle start / end
      const interval = setInterval(() => {
        // Dispatch cycle_start
        handlerRef.current({
          type: "cycle_start",
          payload: {},
          ts: new Date().toISOString()
        });

        // 1.5 seconds later, dispatch cycle_end
        setTimeout(() => {
          handlerRef.current({
            type: "cycle_end",
            payload: { duration_ms: Math.floor(150 + Math.random() * 200) },
            ts: new Date().toISOString()
          });
        }, 1500);

        // Randomly simulate a new position or close position
        const rand = Math.random();
        const state = getMockState();
        if (state && state.running) {
          if (rand > 0.8 && state.positions.length < 4) {
            const sym = Math.random() > 0.5 ? "ETHUSDT" : "AVAXUSDT";
            // Check if position already exists
            if (!state.positions.some((p: any) => p.symbol === sym)) {
              const dir = Math.random() > 0.5 ? "LONG" : "SHORT";
              const entry = sym === "ETHUSDT" ? 3500 : 80;
              const newPos = {
                symbol: sym,
                direction: dir,
                entry: entry,
                sl: dir === "LONG" ? entry * 0.98 : entry * 1.02,
                tp1: dir === "LONG" ? entry * 1.02 : entry * 0.98,
                tp2: dir === "LONG" ? entry * 1.05 : entry * 0.95,
                size: sym === "ETHUSDT" ? 0.5 : 20,
                current_price: entry,
                unrealized_pct: 0,
                unrealized_usdt: 0,
                tp1_hit: false,
                opened_at: new Date().toISOString()
              };
              state.positions.push(newPos);
              saveMockState(state);
              handlerRef.current({
                type: "position_opened",
                payload: { symbol: sym, direction: dir },
                ts: new Date().toISOString()
              });
            }
          } else if (rand < 0.25 && state.positions.length > 0) {
            // Close one position
            const p = state.positions.pop();
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
              reason: "Take Profit Hit",
              opened_at: p.opened_at,
              closed_at: new Date().toISOString(),
              confluence: Math.floor(60 + Math.random() * 25)
            });
            saveMockState(state);
            handlerRef.current({
              type: "position_closed",
              payload: { symbol: p.symbol, direction: p.direction, pnl_usdt: p.unrealized_usdt },
              ts: new Date().toISOString()
            });
          }
        }
      }, 8000);

      return () => {
        window.removeEventListener("efloud_ws_mock", onMockEvent);
        clearInterval(interval);
      };
    }

    let socket: WebSocket | null = null;
    let cancelled = false;
    let reconnectDelay = 1000;

    const connect = () => {
      if (cancelled) return;
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/ws`;
      socket = new WebSocket(url);

      socket.onopen = () => {
        reconnectDelay = 1000;
        statusRef.current?.(true);
      };

      socket.onmessage = (msg) => {
        try {
          const evt: WsEvent = JSON.parse(msg.data);
          handlerRef.current(evt);
        } catch {
          // ignore malformed
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        statusRef.current?.(false);
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 1.6, 15000);
      };

      socket.onerror = () => {
        try { socket?.close(); } catch {}
      };
    };

    connect();

    return () => {
      cancelled = true;
      try { socket?.close(); } catch {}
    };
  }, []);
}
