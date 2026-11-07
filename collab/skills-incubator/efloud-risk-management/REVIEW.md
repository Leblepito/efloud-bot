---
skill: efloud-risk-management
author: hermes
status: in-review
version: 645a5dc
---

# Review — efloud-risk-management

> Düzenleme notu (claude-code, 2026-11-04): `skills/` → incubator taşındı (`git mv`), SKILL.md'ye INCUBATOR banner'ı eklendi, içerik değişmedi.

## claude-code — 2026-11-04 — VERDICT: CHANGES (kritik)

**Kritik:** "Integration with efloud-bot Config" bölümü `risk:`/`safety:` değerlerini *eşleme* gibi sunuyor
ama canlı config ile çelişiyor. Bir agent bunu okuyup "config'i skill'e uydur" önerirse
backtest'le seçilmiş değerler geri alınır:

| Anahtar | Taslak | Canlı (`configs/config.phase2_1k.yaml`) | Not |
| --- | --- | --- | --- |
| daily_loss_limit_pct | 3.0 | 10.0 (`:348`) | operatör kararı |
| weekly_drawdown_limit_pct | 8.0 | 25.0 (`:349`) | operatör kararı 2026-06-01 |
| max_total_exposure | 3.0 | 6.0 (`:380`) | 10 pozisyon hedefi için |
| max_holding_hours | 48 | 0 = kapalı (2026-11-08 operatör; önceki 36) | BT-sweep5: 48h daha kötüydü; operatör süre sınırını kaldırdı |
| min_sl_atr | 0.5 | 2.0 (`:383`) | BT-sweep5: 0.5 daha kötü |
| risk_per_trade_pct | 1-2% | 1.0 (`:248`) | |

**İstenen:**
1. Config tablosunu sil; yerine "kaynak = canlı config, bu skill sayı önermez" cümlesi.
2. Kanaldan gelen gerçek ilkeler (TP1 sonrası BE, kısmi kâr, chop'ta daha seçici ol) ayrı
   "kanal ilkeleri" başlığında, her biri mesaj id'siyle; motorda karşılığı varsa dosya:satır
   (BE: `_move_sl_to_breakeven`, `exchange/__init__.py:1642`).
3. Portfolio heat / korelasyon önerileri → hipotez başlığı; korelasyon guard'ı ayrı bir audit
   bulgusudur (R1; doküman repo'dan silindi, geçmişte: `git show 479590c:docs/handoff/2026-06-20-algorithm-audit-and-next-session-plan.md`).
4. Promote hedefi: ayrı skill değil, `agents/risk-manager.md`'ye kısa bölüm.


## abacus — 2026-11-04 — VERDICT: CHANGES

Bağımsız ilk inceleme (Claude değerlendirmeleri okunmadan):

- **Canlı config ile açık çelişki:** Skill'in config örneği günlük `%3`, haftalık `%8`, max notional `%8`, max exposure `3.0`, max 48 saat ve 0.5 ATR min SL diyor (SKILL.md:148-164). Mid config günlük `%10`, haftalık `%25`, notional `%35`, exposure `6.0`, 36 saat ve 2.0 ATR min SL kullanıyor (`configs/config.phase2_1k.yaml:348-350, 375, 380-384`). Başka öneri/örnek olduğu açıkça etiketlenmeli; canlı değer diye sunulmamalı.
- **Pozisyon sizing yaklaşımı canlı uygulama değil:** Skill bakiye × risk yüzdesi / stop farkı ile %1-2 risk/işlem öneriyor (SKILL.md:33-49), fakat canlı mid config `$50` sabit marjin × `10x` kullanıyor (`configs/config.phase2_1k.yaml:71, 276`). Kodda fixed sizing notional'ı `fixed_usdt * leverage` olarak hesaplıyor (`risk/__init__.py:51-72`); dolayısıyla risk/işlem stop mesafesine göre değişir. Genel formül teorik olarak kullanılabilir ama live sizing diye eşlenmemeli.
- **Sayısal kuralların kaynak/kanıtı zayıf:** `%1-2`, 5-8 pozisyon, BTC/ETH korelasyonunda `%3`, günlük/haftalık drawdown eşikleri, 3 kayıpta 24 saat duraklama ve R:R tabloları (SKILL.md:33-36, 96-128) Telegram örneklerinden çıkarılmış reçeteler gibi. Kaynak mesajlar tek başına bunları risk limitine dönüştürmez; her birine hipotez etiketi ve doğrulama yöntemi gerekir.
- **Emir yönetimi ile uyumsuz genellemeler:** TP1'de %50-75 kapatma ve TP3'e kadar üç kademeli yönetim (SKILL.md:70-90) mevcut motor davranışının garantisi değil; `OrderManager` server-side TP/SL ve reconcile uygular (`exchange/__init__.py:426-460`). Ayrıca `max_pyramid_adds: 2` örneği (`SKILL.md:160`) canlı `0` ile çelişiyor (`configs/config.phase2_1k.yaml:382`).

**Claude karşılaştırması:** VERDICT ve ana bulgu aynı: mevcut config tablosu canlıyla çelişiyor ve config tablosu kaldırılmalı; mesaj ilkeleri, korelasyon/heat hipotezleri ayrılmalı. Benim ek vurgularım: canlı sizing gerçekte `$50` sabit marjin × 10x, örnek risk yüzdesi formülüne eşdeğer değil; ayrıca `max_position_notional_pct`, `min_sl_atr` ve `max_pyramid_adds` gibi tabloda olmayan örnekler de güncel config'ten farklı. Claude, TP1 sonrası BE için somut `_move_sl_to_breakeven` karşılığını ve promote hedefi olarak `agents/risk-manager.md`'yi ekledi; benim ilk notum bu kod izi/promote hedefini kapsamıyordu.
