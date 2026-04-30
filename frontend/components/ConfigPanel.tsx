"use client";

import { useState } from "react";
import { useConfig } from "@/hooks/useConfig";

function flatten(obj: unknown, prefix = ""): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  if (obj == null) return out;
  if (typeof obj !== "object") return [[prefix, String(obj)]];
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (Array.isArray(v)) {
      out.push([key, v.join(", ")]);
    } else if (typeof v === "object" && v !== null) {
      out.push(...flatten(v, key));
    } else {
      out.push([key, String(v)]);
    }
  }
  return out;
}

export function ConfigPanel() {
  const [open, setOpen] = useState(false);
  const { data } = useConfig();
  const rows = data ? flatten(data) : [];

  return (
    <div className="border border-border bg-bg-elevated">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full px-5 py-3 flex items-center justify-between text-left hover:bg-bg-surface transition-colors"
      >
        <span className="text-[10px] uppercase tracking-widest text-text-secondary font-mono">
          Config (read-only)
        </span>
        <span className="text-text-muted font-mono text-xs">
          {open ? "[ collapse ]" : "[ expand ]"}
        </span>
      </button>
      {open && (
        <div className="border-t border-border max-h-96 overflow-y-auto">
          <table className="w-full text-[11px] font-mono">
            <tbody>
              {rows.length === 0 && (
                <tr><td className="px-5 py-4 text-text-muted">no config loaded</td></tr>
              )}
              {rows.map(([k, v]) => (
                <tr key={k} className="border-b border-border last:border-b-0">
                  <td className="px-5 py-1.5 text-text-secondary w-1/2">{k}</td>
                  <td className="px-3 py-1.5 text-text-primary tabular-nums">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
