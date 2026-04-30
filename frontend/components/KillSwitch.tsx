"use client";

import { useEffect, useRef, useState } from "react";
import { mutate } from "swr";
import { postJson } from "@/lib/api";

const HOLD_MS = 1500;

export function KillSwitch() {
  const [holding, setHolding] = useState(false);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState<number | null>(null);
  const startedAt = useRef<number | null>(null);
  const rafId = useRef<number | null>(null);

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
    try {
      const r = await postJson<{ ok: boolean; closed: number }>("/api/kill-switch");
      setClosed(r.closed);
      mutate("/api/positions");
      mutate("/api/status");
    } catch (e) {
      console.error("kill switch failed", e);
    } finally {
      setBusy(false);
      setProgress(0);
      startedAt.current = null;
    }
  };

  const onPress = () => {
    if (busy) return;
    setHolding(true);
    startedAt.current = Date.now();
    rafId.current = requestAnimationFrame(tick);
  };

  const onRelease = () => {
    if (rafId.current) cancelAnimationFrame(rafId.current);
    rafId.current = null;
    if (progress < 1) {
      setHolding(false);
      setProgress(0);
      startedAt.current = null;
    }
  };

  useEffect(() => () => {
    if (rafId.current) cancelAnimationFrame(rafId.current);
  }, []);

  // Reset success message after a few seconds
  useEffect(() => {
    if (closed != null) {
      const t = setTimeout(() => setClosed(null), 4000);
      return () => clearTimeout(t);
    }
  }, [closed]);

  return (
    <div className="flex items-center gap-3">
      {closed != null && (
        <span className="text-[10px] tracking-widest text-accent-red font-mono">
          {closed} POSITION{closed === 1 ? "" : "S"} CLOSED
        </span>
      )}
      <button
        onMouseDown={onPress}
        onMouseUp={onRelease}
        onMouseLeave={onRelease}
        onTouchStart={onPress}
        onTouchEnd={onRelease}
        disabled={busy}
        className="
          relative overflow-hidden
          h-10 px-5
          border border-accent-red
          bg-bg
          font-mono text-[11px] tracking-widest text-accent-red
          uppercase select-none
          transition-colors
          hover:bg-accent-red/10
          disabled:opacity-50 disabled:cursor-wait
          group
        "
        aria-label="Hold to activate kill switch"
      >
        {/* corner cuts via clip-path */}
        <span className="relative z-10">
          {busy ? "Halting…" : holding ? `Hold ${Math.ceil((1 - progress) * (HOLD_MS / 1000) * 10) / 10}s` : "⬢ Kill Switch"}
        </span>
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 bg-accent-red/30 transition-none"
          style={{ width: `${progress * 100}%` }}
        />
      </button>
    </div>
  );
}
