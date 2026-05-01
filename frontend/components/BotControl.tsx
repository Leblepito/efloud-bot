"use client";

import { useState } from "react";
import { mutate } from "swr";
import { postJson } from "@/lib/api";
import { useStatus } from "@/hooks/useStatus";

type ControlResult = {
  ok: boolean;
  running?: boolean;
  already_running?: boolean;
  last_error?: string | null;
};

export function BotControl() {
  const { data } = useStatus();
  const running = !!data?.running;
  const [busy, setBusy] = useState<null | "start" | "stop" | "restart">(null);
  const [flash, setFlash] = useState<string | null>(null);

  const call = async (action: "start" | "stop" | "restart") => {
    if (busy) return;
    if (action === "stop") {
      const ok = window.confirm(
        "Bot duracak. Açık pozisyonlar borsada kalır (KillSwitch farklı bir aksiyondur). Devam edilsin mi?"
      );
      if (!ok) return;
    }
    setBusy(action);
    setFlash(null);
    try {
      const r = await postJson<ControlResult>(`/api/bot/${action}`);
      mutate("/api/status");
      if (action === "start" && r.last_error) {
        setFlash(`Başlatılamadı: ${r.last_error}`);
      } else if (action === "start" && r.already_running) {
        setFlash("Bot zaten çalışıyor");
      } else if (action === "start") {
        setFlash("Başlatıldı");
      } else if (action === "stop") {
        setFlash("Durduruldu");
      } else if (action === "restart") {
        setFlash(r.last_error ? `Restart sorunlu: ${r.last_error}` : "Yeniden başlatıldı");
      }
    } catch (e) {
      setFlash(`Hata: ${(e as Error).message}`);
    } finally {
      setBusy(null);
      setTimeout(() => setFlash(null), 4000);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {flash && (
        <span className="text-[10px] tracking-widest font-mono text-text-muted">
          {flash}
        </span>
      )}
      <button
        onClick={() => call("start")}
        disabled={busy !== null || running}
        className="
          h-10 px-4
          border border-accent-green
          bg-bg
          font-mono text-[11px] tracking-widest text-accent-green
          uppercase select-none
          transition-colors
          hover:bg-accent-green/10
          disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-bg
        "
        aria-label="Start bot"
      >
        {busy === "start" ? "..." : "▶ Start"}
      </button>
      <button
        onClick={() => call("stop")}
        disabled={busy !== null || !running}
        className="
          h-10 px-4
          border border-text-muted
          bg-bg
          font-mono text-[11px] tracking-widest text-text-muted
          uppercase select-none
          transition-colors
          hover:bg-text-muted/10 hover:text-text-primary
          disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-bg
        "
        aria-label="Stop bot"
      >
        {busy === "stop" ? "..." : "■ Stop"}
      </button>
      <button
        onClick={() => call("restart")}
        disabled={busy !== null}
        className="
          h-10 px-4
          border border-accent-amber
          bg-bg
          font-mono text-[11px] tracking-widest text-accent-amber
          uppercase select-none
          transition-colors
          hover:bg-accent-amber/10
          disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-bg
        "
        aria-label="Restart bot"
      >
        {busy === "restart" ? "..." : "↻ Restart"}
      </button>
    </div>
  );
}
