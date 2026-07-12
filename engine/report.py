"""
Efloud Report Engine — Doğal Dilde Analiz Raporu
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Efloud'un raporlarının yapısı:

  # {SYMBOL} | {TF} Update
  
  Merhabalar,
  
  ## Güncel Durum
  - HTF bias: {bias}
  - Şu an {price} seviyelerinde, {zone} bölgesinde.
  
  ## Seviye Hiyerarşisi
  - Direnç: {RH}, {WO}, {stacked_zones}
  - Destek: {EQ}, {WO}, {RL}
  
  ## Pozisyon Durumu
  - Ana long %50 realize edildi, %50 devam.
  - Hedge short zararsız kapandı.
  
  ## Senaryolar
  Ana plan: {main}
  Bozulma:  {invalidation}
  Plan B:   {plan_b}
  
  ## Aksiyonlar
  - ...
"""

from typing import List
from datetime import datetime, timezone
import logging

log = logging.getLogger("efloud.report")


class ReportEngine:
    """Analiz sonuçlarını Efloud tarzı rapor haline getirir."""

    def generate(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        htf_bias: str,
        levels: list,
        stacked_zones: list,
        intent,  # IntentScore
        signals: list,
        scenarios: list,
        positions: list,
        range_info=None,
    ) -> str:
        """Tam rapor üret."""
        now = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M UTC")

        lines = []
        lines.append(f"# {symbol} | {timeframe.upper()} Update")
        lines.append(f"*Generated: {now}*")
        lines.append("")
        lines.append("Merhabalar,")
        lines.append("")

        # ── Güncel Durum ──
        lines.append("## Güncel Durum")
        zone_str = ""
        if range_info:
            zone_str = "PREMIUM bölgesi" if range_info.premium else "DISCOUNT bölgesi"
        bias_emoji = "🟢" if htf_bias == "BULL" else "🔴" if htf_bias == "BEAR" else "⚪"
        lines.append(f"- **HTF Bias:** {bias_emoji} {htf_bias}")
        lines.append(f"- **Fiyat:** {current_price:,.2f} ({zone_str})")
        lines.append(f"- **Momentum:** {intent.label} ({intent.score}/100)")
        lines.append(f"  - Body: {intent.body_ratio:.2f} | Volume: {intent.volume_ratio:.1f}x | "
                     f"Streak: {intent.consecutive}")
        lines.append("")

        # ── Seviye Hiyerarşisi ──
        if levels:
            above = sorted([l for l in levels if l.price > current_price],
                           key=lambda l: l.price)[:5]
            below = sorted([l for l in levels if l.price < current_price],
                           key=lambda l: l.price, reverse=True)[:5]

            lines.append("## Seviye Hiyerarşisi")
            lines.append("")
            lines.append("**Üstte (dirençler):**")
            for l in reversed(above):
                marker = "★" * min(l.strength, 3)
                dist_pct = (l.price - current_price) / current_price * 100
                lines.append(f"- `{l.price:>10,.2f}` — {l.name:<15} {marker} "
                             f"*(+{dist_pct:.1f}%)*")
            lines.append("")
            lines.append(f"**Fiyat:** `{current_price:>10,.2f}`")
            lines.append("")
            lines.append("**Altta (destekler):**")
            for l in below:
                marker = "★" * min(l.strength, 3)
                dist_pct = (current_price - l.price) / current_price * 100
                lines.append(f"- `{l.price:>10,.2f}` — {l.name:<15} {marker} "
                             f"*(-{dist_pct:.1f}%)*")
            lines.append("")

        # ── Stacked Zones ──
        if stacked_zones:
            lines.append("## Yığılmış Seviyeler (Güçlü Bölgeler)")
            for z in sorted(stacked_zones, key=lambda z: z.strength, reverse=True)[:5]:
                lines.append(f"- **{z.bottom:,.2f} – {z.top:,.2f}**: {z.label} "
                             f"({z.strength} seviye ★{'★' * (z.strength - 2)})")
            lines.append("")

        # ── Pozisyon Durumu ──
        open_positions = [p for p in positions if p.is_open]
        closed_positions = [p for p in positions if not p.is_open]

        if open_positions or closed_positions:
            lines.append("## Pozisyon Durumu")

            if open_positions:
                lines.append("")
                lines.append("**Açık pozisyonlar:**")
                for p in open_positions:
                    emoji = "🟢" if p.direction == "LONG" else "🔴"
                    pnl = p.unrealized_pnl(current_price)
                    pnl_pct = (pnl / (p.avg_entry_price * p.remaining_size)) * 100 \
                              if p.avg_entry_price > 0 else 0
                    realized = f" (realized ${p.realized_pnl:+.2f})" if p.tp1_hit else ""

                    lines.append(f"- {emoji} **{p.direction}** {p.symbol} @ avg {p.avg_entry_price:,.2f}")
                    lines.append(f"  - Size: {p.remaining_size:.4f} / {p.total_size_entered:.4f} "
                                 f"({(p.remaining_size/p.total_size_entered)*100:.0f}% remaining)")
                    lines.append(f"  - Unrealized PnL: ${pnl:+.2f} ({pnl_pct:+.2f}%){realized}")
                    # tp2=None is a valid SMC v2 single-target marker (PR #S5.5).
                    tp2_str = "NONE(single-target)" if p.tp2 is None else f"{p.tp2:,.2f}"
                    lines.append(f"  - SL: {p.sl:,.2f} | TP1: {p.tp1:,.2f} | TP2: {tp2_str}")
                    if p.sl_moved_to_be:
                        lines.append(f"  - 🛡 SL at break-even")
                    if p.hedge_id:
                        lines.append(f"  - 🔒 Hedge active: {p.hedge_id}")

            if closed_positions:
                lines.append("")
                total_pnl = sum(p.realized_pnl for p in closed_positions)
                win_count = sum(1 for p in closed_positions if p.realized_pnl > 0)
                lines.append(f"**Kapalı pozisyonlar:** {len(closed_positions)} işlem | "
                             f"Win: {win_count}/{len(closed_positions)} | "
                             f"Total PnL: ${total_pnl:+.2f}")
            lines.append("")

        # ── Senaryolar ──
        active_scenarios = [s for s in scenarios if s.state in ("ACTIVE", "PENDING", "TRIGGERED")]
        if active_scenarios:
            lines.append("## Senaryolar")
            for s in active_scenarios:
                kind_emoji = {"main": "🎯", "invalidation": "⚠️", "plan_b": "🔄"}.get(s.kind, "•")
                state_emoji = {"ACTIVE": "🟢", "PENDING": "⏳", "TRIGGERED": "⚡"}.get(s.state, "")
                lines.append(f"")
                lines.append(f"### {kind_emoji} {s.kind.replace('_', ' ').title()} — {state_emoji} {s.state}")
                lines.append(f"**{s.name}**")
                lines.append(f"- {s.note}")
                lines.append(f"- Entry zone: `{s.entry_zone_bottom:,.2f} – {s.entry_zone_top:,.2f}`")
                lines.append(f"- SL: `{s.sl:,.2f}` | TP1: `{s.tp1:,.2f}` | TP2: `{s.tp2:,.2f}`")
                lines.append(f"- R:R TP1: **{s.rr_tp1:.2f}**")
            lines.append("")

        # ── Sinyaller ──
        if signals:
            latest = signals[-1]
            lines.append("## Güncel Sinyal")
            emoji = "🟢" if latest.direction == "LONG" else "🔴"
            lines.append(f"")
            lines.append(f"{emoji} **{latest.direction}** @ {latest.entry:,.2f}")
            lines.append(f"- Confluence: **{latest.confluence}/100**")
            lines.append(f"- SL: `{latest.sl:,.2f}` | TP1: `{latest.tp1:,.2f}` | TP2: `{latest.tp2:,.2f}`")
            lines.append(f"- R:R: {latest.rr1:.2f} / {latest.rr2:.2f}")
            lines.append(f"- Flags: "
                         f"{'OTE✓ ' if latest.in_ote else ''}"
                         f"{'OB✓ ' if latest.in_ob else ''}"
                         f"{'SFP✓ ' if latest.has_sfp else ''}"
                         f"Zone={latest.zone}")
            if latest.reasons:
                lines.append(f"- Gerekçeler:")
                for r in latest.reasons:
                    lines.append(f"  - {r}")
            lines.append("")

        # ── Aksiyon Önerisi ──
        lines.append("## Öneri")
        suggestions = self._build_suggestions(
            current_price, htf_bias, intent, signals, active_scenarios,
            open_positions, stacked_zones
        )
        for s in suggestions:
            lines.append(f"- {s}")
        lines.append("")

        lines.append("---")
        lines.append("*Efloud SMC Bot — Not financial advice. DYOR.*")

        return "\n".join(lines)

    def _build_suggestions(self, price, bias, intent, signals, scenarios,
                             open_positions, stacked_zones) -> list:
        """Efloud tarzı kısa öneri cümleleri."""
        out = []

        if intent.is_strong and signals:
            out.append(f"**{intent.label}** momentum tespit edildi, "
                       f"son sinyal {signals[-1].direction} @ {signals[-1].entry:,.2f}.")

        if intent.is_weak and open_positions:
            out.append("⚠️ Momentum zayıflıyor, açık pozisyonlarda kısmi kapama düşünülebilir.")

        if stacked_zones:
            nearest = min(stacked_zones, key=lambda z: abs(z.center - price))
            dist_pct = (nearest.center - price) / price * 100
            direction = "üstünde" if nearest.center > price else "altında"
            out.append(f"En yakın güçlü bölge **{nearest.bottom:,.2f}–{nearest.top:,.2f}** "
                       f"({nearest.label}, fiyatın %{abs(dist_pct):.1f} {direction}).")

        main_scen = next((s for s in scenarios if s.kind == "main"), None)
        if main_scen and main_scen.state == "ACTIVE":
            out.append(f"🎯 Ana plan: {main_scen.name}")

        inv_scen = next((s for s in scenarios if s.kind == "invalidation"), None)
        if inv_scen and inv_scen.state == "PENDING":
            out.append(f"⚠️ Bozulma durumunda plan: {inv_scen.name}")

        if not out:
            out.append("Şu aşamada belirgin bir setup yok, izlemeye devam.")

        return out
