"use client";

import { useEffect, useRef } from "react";

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

export function useWebSocket(onEvent: Listener) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
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
