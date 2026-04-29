"""
Learning Memory — Hata Pattern Agregatörü
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Kapalı trade'lerdeki error_tag'leri biriktirir ve pattern çıkarır:

  "Son 20 trade'de LOW_CONFLUENCE 8 kez geçti → min_confluence'ı yükselt"
  "TIGHT_SL 5 kez → SL buffer'ını arttır"
  "PREMIUM_LONG 3 kez → zone filter aktif et"

Memory iki katmanlıdır:
  Short-term: son 20 trade (taktik adaptasyon)
  Long-term: tüm trade'ler (stratejik desen)
"""

import logging
from collections import Counter
from dataclasses import dataclass
from typing import List, Dict
from .journal import TradeJournal, TradeSnapshot

log = logging.getLogger("efloud.memory")


@dataclass
class Pattern:
    tag: str
    frequency: int
    recent_frequency: int       # son 20 trade içinde
    win_rate_when_present: float
    severity: str               # "CRITICAL" | "WARNING" | "INFO"
    suggested_action: str


class LearningMemory:
    """Trade journal'ı tarayıp tekrarlayan hataları bulur."""

    # Severity threshold'ları: son 20 trade'de kaç kez görüldüyse
    SEVERITY_THRESHOLDS = {
        "CRITICAL": 6,      # 6+ kez = sürekli hata
        "WARNING":  3,      # 3-5 kez = dikkat edilmeli
        "INFO":     1,      # 1-2 kez = izlenecek
    }

    # Hata → adaptasyon önerisi map
    ACTION_MAP = {
        "LOW_CONFLUENCE":   "Min confluence eşiğini yükselt (+5-10)",
        "WRONG_BIAS":       "HTF bias kontrolünü sıkılaştır — karşı trend girişini engelle",
        "PREMIUM_LONG":     "Zone filter aktif — long sadece discount'ta",
        "DISCOUNT_SHORT":   "Zone filter aktif — short sadece premium'da",
        "TIGHT_SL":         "SL ATR buffer'ını arttır (0.5→1.0)",
        "LOOSE_SL":         "SL ATR buffer'ını düşür (1.0→0.5)",
        "TP_OVERSHOT":      "TP2 hedef çarpanını büyüt (1.618→2.618)",
        "TP_UNDERSHOT":     "TP1 seçiminde daha yakın seviye kullan",
        "EARLY_EXIT":       "Weakness threshold'ı düşür (momentum kaybı daha belirgin olmalı)",
        "LATE_EXIT":        "Weakness threshold'ı yükselt (daha erken reaksiyon)",
        "NO_OB_SUPPORT":    "OB/FVG zone zorunlu — yoksa giriş iptal",
        "LOW_VOLUME_ENTRY": "Min volume ratio şartı ekle (>1.0x ortalama)",
        "CHOPPY_MARKET":    "Range-bound tespit ekle — ATR düşükken trade alma",
        "AGAINST_INTENT":   "Intent kontrolünü zorunlu yap",
    }

    def __init__(self, journal: TradeJournal, short_term_window: int = 20):
        self.journal = journal
        self.window = short_term_window

    def analyze_patterns(self) -> List[Pattern]:
        """Journal'ı tarayıp pattern'leri çıkar."""
        all_trades = self.journal.all_closed()
        if not all_trades:
            return []

        recent = all_trades[-self.window:] if len(all_trades) > self.window else all_trades

        # Tüm error tag'lerini topla
        all_tags = [tag for t in all_trades for tag in t.error_tags]
        recent_tags = [tag for t in recent for tag in t.error_tags]

        counter_all = Counter(all_tags)
        counter_recent = Counter(recent_tags)

        patterns = []
        for tag, count_recent in counter_recent.items():
            count_all = counter_all[tag]

            # Bu tag'i içeren trade'lerin kazanma oranı
            trades_with_tag = [t for t in all_trades if tag in t.error_tags]
            wins_with_tag = sum(1 for t in trades_with_tag if t.is_winner)
            win_rate = (wins_with_tag / len(trades_with_tag) * 100) if trades_with_tag else 0

            # Severity belirleme
            if count_recent >= self.SEVERITY_THRESHOLDS["CRITICAL"]:
                severity = "CRITICAL"
            elif count_recent >= self.SEVERITY_THRESHOLDS["WARNING"]:
                severity = "WARNING"
            else:
                severity = "INFO"

            patterns.append(Pattern(
                tag=tag,
                frequency=count_all,
                recent_frequency=count_recent,
                win_rate_when_present=round(win_rate, 1),
                severity=severity,
                suggested_action=self.ACTION_MAP.get(tag, "İzlemeye devam")
            ))

        # Severity + frequency sırala
        patterns.sort(key=lambda p: (
            {"CRITICAL": 0, "WARNING": 1, "INFO": 2}[p.severity],
            -p.recent_frequency
        ))
        return patterns

    def get_critical_patterns(self) -> List[Pattern]:
        """Sadece CRITICAL/WARNING pattern'ler — aktif adaptasyon gerektiriyor."""
        return [p for p in self.analyze_patterns()
                if p.severity in ("CRITICAL", "WARNING")]

    def summary_report(self) -> str:
        """Markdown formatında öğrenme özeti."""
        patterns = self.analyze_patterns()
        stats = self.journal.stats()

        if stats.get("trades", 0) == 0:
            return "# Learning Memory\n\nHenüz kapalı trade yok."

        lines = [
            "# 🧠 Learning Memory Report",
            "",
            f"## İstatistikler",
            f"- Toplam trade: **{stats['trades']}**",
            f"- Win rate: **{stats['win_rate']}%** ({stats['wins']}W / {stats['losses']}L)",
            f"- Toplam PnL: **${stats['total_pnl']:+.2f}**",
            f"- Profit factor: **{stats['profit_factor']}**",
            f"- Avg win: ${stats['avg_win']:+.2f} | Avg loss: ${stats['avg_loss']:+.2f}",
            "",
        ]

        if patterns:
            lines.append("## 🔍 Tespit Edilen Hata Pattern'leri")
            lines.append("")
            for p in patterns:
                emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}[p.severity]
                lines.append(
                    f"- {emoji} **{p.tag}** ({p.severity}) — "
                    f"son {self.window} trade'de {p.recent_frequency}x, "
                    f"toplam {p.frequency}x | WR: {p.win_rate_when_present}%"
                )
                lines.append(f"  - 💡 {p.suggested_action}")
                lines.append("")
        else:
            lines.append("## Temiz — tespit edilen sistemik hata yok.")

        return "\n".join(lines)
