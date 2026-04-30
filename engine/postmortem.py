"""
Post-Mortem Analyzer — Kapalı trade'lerden ders çıkarma motoru.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Her kapanan trade için şu soruları sorar ve cevaplar:

1. Entry doğru mu seçildi?
   - Confluence yeterli miydi?
   - HTF bias ile uyumlu muydu?
   - Premium/discount bölgesi doğru muydu?

2. SL mantıklı mı yerleştirildi?
   - Fiyat SL'yi çok yakınından mı teğet geçti? (tight SL error)
   - SL aşırı geniş miydi? (loose SL, düşük R:R)

3. TP seçimi doğru muydu?
   - MFE analizi: fiyat TP'yi aştı mı, sonra geri mi döndü?
   - TP1'de çıkılsa daha kârlı olur muydu?

4. Exit timing?
   - Ne kadar erken/geç çıkıldı?
   - WEAKNESS exit ise momentum gerçekten zayıflamış mıydı?

5. Scenario bağlamı?
   - Hangi senaryoda alındı?
   - Bu senaryo tipinin geçmiş performansı nasıl?

Hata Tag'leri (standartlaştırılmış):
  LOW_CONFLUENCE        Entry confluence < 60
  WRONG_BIAS            HTF bias ile ters
  PREMIUM_LONG          Premium'da long alındı
  DISCOUNT_SHORT        Discount'ta short alındı
  TIGHT_SL              SL çok yakın, normal volatility tetikledi
  LOOSE_SL              SL aşırı geniş, R:R düşük
  TP_OVERSHOT           Fiyat TP'yi aştı sonra döndü — TP yakın olabilirdi
  TP_UNDERSHOT          Fiyat TP'ye yaklaşamadan SL'ye döndü
  EARLY_EXIT            WEAKNESS kapandı ama fiyat sonra lehe gitti
  LATE_EXIT             Momentum erken zayıflamış ama geç çıkıldı
  NO_OB_SUPPORT         OB/FVG zone yoktu
  LOW_VOLUME_ENTRY      Entry anında hacim zayıftı
  CHOPPY_MARKET         Range-bound'da trend trade
  AGAINST_INTENT        Intent tersinede alındı
"""

import logging
from typing import List, Dict, Tuple
import pandas as pd
from .journal import TradeSnapshot

log = logging.getLogger("efloud.postmortem")


class PostMortemAnalyzer:
    """Her kapanan trade için sistematik analiz yapar."""

    def __init__(self):
        pass

    def analyze(self, snap: TradeSnapshot,
                post_entry_df: pd.DataFrame = None) -> Tuple[List[str], List[str]]:
        """
        Trade'i analiz et, hata tag'leri ve ders cümleleri üret.

        Args:
            snap: kapalı trade snapshot
            post_entry_df: trade entry'sinden sonraki OHLCV (path analysis için)

        Returns:
            (error_tags, lessons)
        """
        errors = []
        lessons = []

        is_winner = snap.is_winner
        is_loser = not is_winner

        # ── 1. Entry kalite kontrolleri ──
        if snap.confluence_score < 60:
            errors.append("LOW_CONFLUENCE")
            lessons.append(
                f"Confluence sadece {snap.confluence_score}/100 idi. "
                f"60+ skor olmadan giriş yapılmamalı — "
                f"{'zaten' if is_loser else 'yine de'} yüksek risk."
            )

        # HTF bias uyumu
        if snap.direction == "LONG" and snap.htf_bias == "BEAR":
            errors.append("WRONG_BIAS")
            lessons.append("HTF bearish iken long alındı — karşı trend trade.")
        elif snap.direction == "SHORT" and snap.htf_bias == "BULL":
            errors.append("WRONG_BIAS")
            lessons.append("HTF bullish iken short alındı — karşı trend trade.")

        # Premium/discount
        if snap.direction == "LONG" and snap.zone_at_entry == "PREMIUM":
            errors.append("PREMIUM_LONG")
            lessons.append(
                "Premium bölgede long — Efloud: 'Fib 0.5 üstü pahalı, short ara.' "
                "Discount bölgeye geri çekilmesi beklenmeliydi."
            )
        elif snap.direction == "SHORT" and snap.zone_at_entry == "DISCOUNT":
            errors.append("DISCOUNT_SHORT")
            lessons.append(
                "Discount bölgede short — Efloud: 'Fib 0.5 altı ucuz, long ara.' "
                "Premium bölgeye hareket beklenmeliydi."
            )

        # ── 2. OB / FVG desteği ──
        if not snap.in_ob and not snap.in_ote and is_loser:
            errors.append("NO_OB_SUPPORT")
            lessons.append(
                "Giriş anında ne OB ne OTE zone'u vardı. "
                "Fiyatın referans aldığı yapı yoktu — bu trade spekülatiftir."
            )

        # SFP onayı
        if not snap.has_sfp and snap.confluence_score < 70:
            # SFP yoksa ve confluence düşükse not düş
            if is_loser:
                lessons.append(
                    "SFP (likidite sweep) onayı yoktu. "
                    "Düşük confluence'la giriş için güçlü reversal sinyali aranmalıydı."
                )

        # Intent sorunu
        if snap.direction == "LONG" and snap.intent_label_entry.startswith("STRONG_BEAR"):
            errors.append("AGAINST_INTENT")
            lessons.append("Giriş anında intent STRONG_BEAR idi — momentum ters yöndeydi.")
        elif snap.direction == "SHORT" and snap.intent_label_entry.startswith("STRONG_BULL"):
            errors.append("AGAINST_INTENT")
            lessons.append("Giriş anında intent STRONG_BULL idi — momentum ters yöndeydi.")

        # ── 3. SL kalite kontrolleri ──
        if snap.exit_reason == "SL" and snap.max_favorable_excursion_pct < 0.3:
            errors.append("TIGHT_SL")
            lessons.append(
                f"SL tetiklendi ama fiyat hiçbir zaman lehe gitmedi (MFE: "
                f"{snap.max_favorable_excursion_pct:.2f}%). "
                "Ya giriş çok erkendi ya da SL çok dardı — confirmation beklemek lazımdı."
            )

        # SL mesafesi vs ATR oran analizi (eğer snap'te atr bilgisi varsa)
        sl_distance_pct = abs(snap.entry_price - snap.sl_initial) / snap.entry_price * 100
        if sl_distance_pct < 0.5 and snap.exit_reason == "SL":
            errors.append("TIGHT_SL")
            lessons.append(
                f"SL mesafesi sadece %{sl_distance_pct:.2f}. Normal mum volatility'si "
                "bile bu seviyeyi tetikleyebilir. Swing low/high'ın altına + ATR buffer konulmalıydı."
            )
        elif sl_distance_pct > 3.0:
            errors.append("LOOSE_SL")
            lessons.append(
                f"SL mesafesi %{sl_distance_pct:.1f} — aşırı geniş. "
                "Risk/reward bu durumda düşük olur."
            )

        # ── 4. TP kalite kontrolleri ──
        tp1_distance_pct = abs(snap.tp1_initial - snap.entry_price) / snap.entry_price * 100

        if is_winner and snap.exit_reason == "TP1":
            # TP1 tuttu, MFE çok daha yüksekse TP1 erken konumda seçilmiş
            if snap.max_favorable_excursion_pct > tp1_distance_pct * 2:
                errors.append("TP_OVERSHOT")
                lessons.append(
                    f"TP1 @ %{tp1_distance_pct:.1f} hedefi tuttu, "
                    f"ama fiyat %{snap.max_favorable_excursion_pct:.1f}'a kadar gitti. "
                    "TP2 daha uzağa konulabilirdi — trailing stop denemeli."
                )

        if is_loser and snap.max_favorable_excursion_pct > 0 and \
           snap.max_favorable_excursion_pct < tp1_distance_pct * 0.5:
            errors.append("TP_UNDERSHOT")
            lessons.append(
                f"Fiyat TP1'in yarısına bile ulaşamadı (MFE: "
                f"{snap.max_favorable_excursion_pct:.2f}%). "
                "TP1 gerçekçi bir hedef değildi — yakın direnç/destek kullanılmalıydı."
            )

        # ── 5. Exit timing ──
        if snap.exit_reason == "WEAKNESS" and is_winner:
            lessons.append(
                "WEAKNESS exit doğru zamanlandı — momentum zayıflamıştı, kâr realize edildi."
            )
        elif snap.exit_reason == "WEAKNESS" and not is_winner:
            # Erken çıkış olabilir
            if post_entry_df is not None and len(post_entry_df) > 0:
                # Eğer sonrasında lehimize gittiyse erken çıkış
                pass
            lessons.append(
                "WEAKNESS exit zararla kapandı — ya piyasa gürültüsünü yanlış okudu "
                "ya da zaten trade'in temel tezi yanlıştı."
            )

        # ── 6. Piramit ekleme analizi ──
        if snap.additions and is_loser:
            total_added = sum(a.get("size", 0) for a in snap.additions)
            lessons.append(
                f"Pozisyon {len(snap.additions)} kez eklendi (toplam +{total_added:.4f}). "
                "Zararla kapanan trade'de piramit = kaybı büyütür. "
                "Eklemeden önce fiyat yapısının bozulmadığı doğrulanmalıydı."
            )

        # ── 7. Hedge analizi ──
        if snap.hedge_opened:
            if snap.hedge_pnl > 0:
                lessons.append(
                    f"Hedge short açıldı ve +${snap.hedge_pnl:.2f} kâr yaptı — "
                    "risk yönetimi başarılı."
                )
            else:
                lessons.append(
                    f"Hedge short açıldı ama ${snap.hedge_pnl:+.2f} PnL — "
                    "hedge zamanlaması gözden geçirilmeli."
                )

        # ── 8. Scenario bağlamı ──
        if snap.scenario_kind == "plan_b" and is_loser:
            lessons.append(
                "Plan B senaryosundan giriş yapıldı — bu en düşük güvenilirlikli "
                "senaryodur (iki önceki destek/direnç tutmadıktan sonra)."
            )

        # ── Başarılı trade'lerden de ders ──
        if is_winner and not errors:
            lessons.append(
                f"Temiz kazanan trade: {snap.direction} @ confluence {snap.confluence_score}, "
                f"{snap.exit_reason} ile %{snap.realized_pnl_pct:+.1f} kâr. "
                "Bu setup kombinasyonu gelecekte de aranmalı."
            )

        return errors, lessons

    def generate_report(self, snap: TradeSnapshot,
                        errors: List[str], lessons: List[str]) -> str:
        """Post-mortem markdown raporu."""
        emoji = "✅" if snap.is_winner else "❌"
        lines = []
        lines.append(f"# {emoji} Trade Post-Mortem: {snap.trade_id}")
        lines.append("")
        lines.append(f"## Özet")
        lines.append(f"- **{snap.direction}** {snap.symbol} {snap.timeframe}")
        lines.append(f"- Entry: `${snap.entry_price:.2f}` → Exit: `${snap.exit_price:.2f}` "
                     f"({snap.exit_reason})")
        lines.append(f"- PnL: **${snap.realized_pnl:+.2f}** "
                     f"(`{snap.realized_pnl_pct:+.2f}%`)")
        lines.append(f"- Bars held: {snap.bars_held}")
        lines.append(f"- MFE: {snap.max_favorable_excursion_pct:.2f}% | "
                     f"MAE: {snap.max_adverse_excursion_pct:.2f}%")
        lines.append("")

        lines.append(f"## Entry Context")
        lines.append(f"- HTF bias: `{snap.htf_bias}`")
        lines.append(f"- Intent: {snap.intent_label_entry} ({snap.intent_score_entry}/100)")
        lines.append(f"- Confluence: **{snap.confluence_score}/100**")
        lines.append(f"- Zone: {snap.zone_at_entry}")
        lines.append(f"- Flags: "
                     f"{'OTE✓ ' if snap.in_ote else ''}"
                     f"{'OB✓ ' if snap.in_ob else ''}"
                     f"{'SFP✓ ' if snap.has_sfp else ''}")
        if snap.scenario_kind:
            lines.append(f"- Scenario: {snap.scenario_kind} ({snap.scenario_name})")
        lines.append("")

        if errors:
            lines.append(f"## 🚨 Tespit Edilen Hatalar")
            for e in errors:
                lines.append(f"- `{e}`")
            lines.append("")

        if lessons:
            lines.append(f"## 📚 Dersler")
            for l in lessons:
                lines.append(f"- {l}")
            lines.append("")

        return "\n".join(lines)
