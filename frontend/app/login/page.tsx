"use client";

import { FormEvent, useState } from "react";
import { postJson } from "@/lib/api";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await postJson("/api/login", { password });
      window.location.href = "/";
    } catch (e) {
      const msg = e instanceof Error ? e.message : "login failed";
      setError(msg.includes("401") ? "Invalid password." : msg.includes("429") ? "Too many attempts. Try again later." : msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh flex items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="font-mono text-[11px] tracking-[0.32em] text-text-primary mb-12 text-center">
          E F L O U D
        </div>
        <form onSubmit={onSubmit} className="border border-border bg-bg-elevated p-6 space-y-5">
          <div>
            <label className="block text-[10px] uppercase tracking-widest text-text-secondary font-mono mb-2">
              Console Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              className="
                w-full bg-bg border border-border px-3 py-2.5
                font-mono text-sm text-text-primary tracking-wider
                focus:border-accent-green focus:outline-none transition-colors
              "
              placeholder="••••••••••••"
              required
            />
          </div>
          {error && (
            <div className="text-[11px] text-accent-red font-mono tracking-wider">{error}</div>
          )}
          <button
            type="submit"
            disabled={busy || !password}
            className="
              w-full h-10
              border border-accent-green
              bg-accent-green/5 hover:bg-accent-green/15
              disabled:opacity-40 disabled:cursor-not-allowed
              font-mono text-[11px] tracking-widest text-accent-green uppercase
              transition-colors
            "
          >
            {busy ? "Verifying…" : "Enter Console"}
          </button>
        </form>
        <p className="mt-6 text-[10px] tracking-widest font-mono text-text-muted text-center uppercase">
          Authorised personnel only
        </p>
      </div>
    </div>
  );
}
