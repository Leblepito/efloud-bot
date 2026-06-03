"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { mutate } from "swr";
import { postJson } from "@/lib/api";

const HOLD_MS = 1500;

export function KillSwitch() {
  const [holding, setHolding] = useState(false);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef<number | null>(null);
  const rafId = useRef<number | null>(null);

  const cancelHold = () => {
    if (rafId.current) cancelAnimationFrame(rafId.current);
    rafId.current = null;
    setHolding(false);
    setProgress(0);
    startedAt.current = null;
  };

  const tick = () => {
    if (startedAt.current == null) return;
    const elapsed = Date.now() - startedAt.current;
    const p = Math.min(1, elapsed / HOLD_MS);
    setProgress(p);
    if (p >= 1) {
      activate();
      return;
    }
    rafId.current = requestAnimationFrame(tick);
  };

  const activate = async () => {
    setHolding(false);
    setBusy(true);
    setError(null);
    try {
      const r = await postJson<{ ok: boolean; closed: number }>("/api/kill-switch");
      setClosed(r.closed);
      mutate("/api/positions");
      mutate("/api/status");
    } catch (e) {
      setError((e as Error).message || "Kill switch failed");
    } finally {
      setBusy(false);
      setProgress(0);
      startedAt.current = null;
    }
  };

  const onPress = () => {
    if (busy || holding) return;
    setError(null);
    setHolding(true);
    startedAt.current = Date.now();
    rafId.current = requestAnimationFrame(tick);
  };

  const onRelease = () => {
    if (progress < 1) cancelHold();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.repeat) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      onPress();
    }
  };

  const onKeyUp = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      onRelease();
    }
  };

  // Cleanup on unmount + reset success/error toast after a few seconds.
  useEffect(() => () => {
    if (rafId.current) cancelAnimationFrame(rafId.current);
  }, []);

  useEffect(() => {
    if (closed != null) {
      const t = setTimeout(() => setClosed(null), 4000);
      return () => clearTimeout(t);
    }
  }, [closed]);

  useEffect(() => {
    if (error != null) {
      const t = setTimeout(() => setError(null), 5000);
      return () => clearTimeout(t);
    }
  }, [error]);

  return (
    <div className="flex items-center gap-3">
      {closed != null && (
        <span
          role="status"
          aria-live="polite"
          className="text-[10px] tracking-widest text-accent-red font-mono"
        >
          {closed} POSITION{closed === 1 ? "" : "S"} CLOSED
        </span>
      )}
      {error != null && (
        <span
          role="alert"
          aria-live="assertive"
          className="text-[10px] tracking-widest text-accent-amber font-mono"
        >
          KILL FAILED: {error}
        </span>
      )}
      <button
        type="button"
        onMouseDown={onPress}
        onMouseUp={onRelease}
        onMouseLeave={onRelease}
        onTouchStart={onPress}
        onTouchEnd={onRelease}
        onKeyDown={onKeyDown}
        onKeyUp={onKeyUp}
        onBlur={onRelease}
        disabled={busy}
        aria-disabled={busy}
        aria-pressed={holding}
        aria-busy={busy}
        aria-keyshortcuts="Space Enter"
        aria-describedby="killswitch-help"
        aria-label={
          busy
            ? "Kill switch activating, please wait"
            : "Hold to activate kill switch and close all open positions"
        }
        className="
          relative overflow-hidden
          h-10 px-5
          border border-accent-red
          bg-bg
          font-mono text-[11px] tracking-widest text-accent-red
          uppercase select-none
          transition-all duration-150 ease-out active:scale-[0.97]
          hover:bg-accent-red/10
          disabled:opacity-50 disabled:cursor-wait
          group
        "
      >
        {/* corner cuts via clip-path */}
        <span className="relative z-10 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-red dot-breathe" />
          {busy
            ? "Halting…"
            : holding
            ? `Hold ${Math.ceil((1 - progress) * (HOLD_MS / 1000) * 10) / 10}s`
            : "⬢ Kill Switch"}
        </span>
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 bg-accent-red/30 transition-none"
          style={{ width: `${progress * 100}%` }}
        />
      </button>
      <span id="killswitch-help" className="sr-only">
        Hold the Kill Switch button (mouse, touch, Space, or Enter) for{" "}
        {(HOLD_MS / 1000).toFixed(1)} seconds to immediately close all open positions on the
        exchange. Releasing or moving focus away before completion cancels the action.
      </span>
    </div>
  );
}
