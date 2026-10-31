"use client";

import { useEffect, useState } from "react";
import { TrendingUp, UserPlus, Bot, Trophy, Zap } from "lucide-react";

interface Notification {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  text: string;
  accent: string;
  time: string;
}

const NOTIFICATIONS: Notification[] = [
  { icon: UserPlus, text: "Ali K. upgraded to Pro", accent: "#00f0ff", time: "2m ago" },
  { icon: Bot, text: "Bot #2847 closed +$127.50 profit", accent: "#00ff88", time: "3m ago" },
  { icon: Trophy, text: "MoonTrader reached Level 15", accent: "#FFD700", time: "5m ago" },
  { icon: TrendingUp, text: "BTC signal: 92% confidence BUY", accent: "#00ff88", time: "1m ago" },
  { icon: Zap, text: "New strategy published: SMC Reversal Pro", accent: "#a855f7", time: "4m ago" },
  { icon: UserPlus, text: "Sarah L. joined from London", accent: "#00f0ff", time: "6m ago" },
  { icon: Bot, text: "Bot #1923 opened LONG ETH @ $3,452", accent: "#00f0ff", time: "30s ago" },
  { icon: Trophy, text: "CryptoWolf won prediction: +500 u2coin", accent: "#FFD700", time: "7m ago" },
  { icon: TrendingUp, text: "SOL signal: 87% confidence BUY", accent: "#00ff88", time: "2m ago" },
  { icon: UserPlus, text: "Dmitri K. upgraded to Premium", accent: "#a855f7", time: "8m ago" },
];

export function SocialProofTicker() {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIndex((prev) => (prev + 1) % NOTIFICATIONS.length);
        setVisible(true);
      }, 400);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const notif = NOTIFICATIONS[index];
  const Icon = notif.icon;

  return (
    <div className="fixed bottom-20 sm:bottom-6 left-4 z-30 pointer-events-none">
      <div
        className={`pointer-events-auto flex items-center gap-2.5 px-4 py-2.5 rounded-xl border border-white/[0.08] bg-black/80 backdrop-blur-xl shadow-2xl shadow-black/40 transition-all duration-400 ${
          visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
        }`}
        style={{ maxWidth: 340 }}
      >
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ backgroundColor: `${notif.accent}15`, border: `1px solid ${notif.accent}25` }}
        >
          <Icon className="w-3.5 h-3.5" style={{ color: notif.accent }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[12px] text-slate-200 truncate">{notif.text}</p>
          <p className="text-[9px] text-slate-400">{notif.time}</p>
        </div>
        <div className="w-1.5 h-1.5 rounded-full animate-pulse shrink-0" style={{ backgroundColor: notif.accent }} />
      </div>
    </div>
  );
}
