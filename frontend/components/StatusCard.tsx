"use client";

import { ReactNode } from "react";

type Tone = "neutral" | "good" | "warn" | "bad";

const dotClass: Record<Tone, string> = {
  neutral: "bg-text-muted",
  good: "bg-accent-green",
  warn: "bg-accent-amber",
  bad: "bg-accent-red",
};

const valueClass: Record<Tone, string> = {
  neutral: "text-text-primary",
  good: "text-accent-green",
  warn: "text-accent-amber",
  bad: "text-accent-red",
};

export function StatusCard({
  label,
  value,
  sub,
  tone = "neutral",
  pulse = false,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  pulse?: boolean;
}) {
  return (
    <div className="border border-border bg-bg-elevated p-5 relative">
      <div className="flex items-center gap-2.5 mb-3">
        <span
          aria-hidden
          className={`relative inline-block w-1.5 h-1.5 ${dotClass[tone]}`}
        >
          {pulse && tone === "good" && (
            <span className={`absolute inset-0 ${dotClass[tone]} animate-pulse`} />
          )}
        </span>
        <span className="text-[10px] uppercase tracking-widest text-text-secondary font-mono">
          {label}
        </span>
      </div>
      <div className={`font-mono text-2xl tabular-nums ${valueClass[tone]}`}>
        {value}
      </div>
      {sub && (
        <div className="mt-2 text-[11px] text-text-muted font-mono tabular-nums">
          {sub}
        </div>
      )}
    </div>
  );
}
