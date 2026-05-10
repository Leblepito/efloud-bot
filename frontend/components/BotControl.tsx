"use client";

import { useState } from "react";
import { mutate } from "swr";
import { postJson } from "@/lib/api";
import { useStatus } from "@/hooks/useStatus";
import { ConfirmDialog } from "./ConfirmDialog";

type ControlResult = {
  ok: boolean;
  running?: boolean;
  already_running?: boolean;
  last_error?: string | null;
};

type Action = "start" | "stop" | "restart";

export function BotControl() {
  const { data } = useStatus();
  const running = !!data?.running;
  const [busy, setBusy] = useState<null | Action>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);

  const performAction = async (action: Action) => {
    if (busy) return;
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

  const onStopClick = () => {
    if (busy || !running) return;
    setConfirmStop(true);
  };

  const onConfirmStop = () => {
    setConfirmStop(false);
    void performAction("stop");
  };

  return (
    <div className="flex items-center gap-2">
      {flash && (
        <span
          role="status"
          aria-live="polite"
          className="text-[10px] tracking-widest font-mono text-text-muted"
        >
          {flash}
        </span>
      )}
      <button
        type="button"
        onClick={() => performAction("start")}
        disabled={busy !== null || running}
        aria-busy={busy === "start"}
        aria-disabled={busy !== null || running}
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
        type="button"
        onClick={onStopClick}
        disabled={busy !== null || !running}
        aria-busy={busy === "stop"}
        aria-disabled={busy !== null || !running}
        aria-haspopup="dialog"
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
        type="button"
        onClick={() => performAction("restart")}
        disabled={busy !== null}
        aria-busy={busy === "restart"}
        aria-disabled={busy !== null}
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
      <ConfirmDialog
        open={confirmStop}
        title="Bot durdurulsun mu?"
        description="Bot trade döngüsü duracak. Açık pozisyonlar borsada kalır — bunları kapatmak için Kill Switch farklı bir aksiyondur."
        confirmLabel="Durdur"
        cancelLabel="Vazgeç"
        destructive={true}
        onConfirm={onConfirmStop}
        onCancel={() => setConfirmStop(false)}
      />
    </div>
  );
}
