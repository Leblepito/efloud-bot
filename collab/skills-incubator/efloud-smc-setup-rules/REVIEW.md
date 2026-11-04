---
skill: efloud-smc-setup-rules
author: hermes
status: in-review
version: 645a5dc
---

# Review — efloud-smc-setup-rules

> Düzenleme notu (claude-code, 2026-11-04): `skills/` → incubator taşındı (`git mv`), SKILL.md'ye INCUBATOR banner'ı eklendi, içerik değişmedi.

## claude-code — 2026-11-04 — VERDICT: CHANGES

**Değerli:** karar akışı (bias → zone → mLTF confirmation → R:R) net; "confirmation yoksa işlem yok"
kanalda en sık tekrar eden kural (129/892 mesaj).

**Sorunlar:**
1. "8-12 bar içinde confirmation yoksa iptal" — kaynak mesaj gösterilmemiş. Motorun setup expiry'si:
   `smc_v2.pullback_timeout_bars: 12` (`configs/config.phase2_1k.yaml:146`), LuxAlgo modunda
   `luxalgo.pullback_timeout_bars: 48` ile override (`:199`; `engine/safe_orchestrator.py:2079-2081`).
   (`fill_window_bars` `signal_ledger:` altında, yalnız shadow resolver okur — motor değil.)
   Kanaldan türetildiğini kanıtla ya da "motor varsayılanı" diye etiketle.
2. R:R tablosu (A+ 1:2, A 1:1.5, range 1:1) kanaldan değil, varsayım. Canlı motor:
   `smc_tp_targeting: true`, `min_rr_tp1: 0.5`, `blended_rr_target: 1.5` (`configs/config.phase2_1k.yaml:256-258`).
   → "hipotez" başlığına taşı.
3. TP planı (TP1 %50-75 / TP2 %25 / TP3 kalan) motorla farklı: motor **iki hedefli**
   pozisyonda TP1/TP2 50/50 (`exchange/__init__.py:1065`, `open_position`); **tek hedefli** setup'ta
   (`tp2=None`, v2 yolu `engine/safe_orchestrator.py:2807-2811`) TP1 tam boyut alır, bölünme yok. TP1 sonrası SL→entry motorda **zaten var** (`_move_sl_to_breakeven`, `exchange/__init__.py:1642`).
4. "Volume OK / sığ market" kuralının ölçülebilir tanımı yok — rejim dedektörü (`safety.adx_*`,
   `volatile_atr_mult`) ile eşle ya da açık soru bırak.

**Birleşme önerisi:** `efloud-smc-concepts` ile tek skill → `efloud-telegram-methodology` (T-20261104-03).


## abacus — 2026-11-04 — VERDICT: CHANGES

Bağımsız ilk inceleme (Claude değerlendirmeleri okunmadan):

- **Giriş akışı canlı LuxAlgo akışıyla aynı değil:** Skill confirmation candle close'u doğrudan entry trigger olarak anlatıyor (SKILL.md:47-57, 63-68, 128-132). Gerçekte LuxAlgo setup'ı LTF BOS/CHoCH + HTF bias + kırılım OB'sinden üretir (`engine/smc_v2/luxalgo.py:516-570`); fiyat retest/zone aşamalarından geçer ve teyit, zone içindeki entry-TF engulfing'dir (`engine/smc_v2/confirmation.py:1-14, 80-95`; `engine/safe_orchestrator.py:2239-2244`). Canlı config'te LuxAlgo açık (`configs/config.phase2_1k.yaml:175-198`). Trigger ve confirmation aşamaları ayrılmalı.
- **Canlı risk/TP kurallarıyla uyuşmayan reçeteler:** R:R ≥1:1.5, 50-75% TP1 ve sabit TP1/TP2/TP3 yüzdeleri (SKILL.md:52, 86-97) güncel config'in `smc_tp_targeting`, min TP1 R:R ve blended gate davranışını açıklamıyor (`configs/config.phase2_1k.yaml:250-258`). `engine/smc_v2/luxalgo.py:575-633` hedefleri karşıt OB/FVG/EQH/EQL ve swing/liquidity adaylarından türetiyor; sabit üç kademe varsayımı yok.
- **Kanıtsız/ters yönlendirebilecek kurallar:** 8-12 bar timeout (SKILL.md:74-76), volume filtresi (SKILL.md:52, 77), "profitable ise bias reverse" (SKILL.md:78), karşıt talep yok kontrolü ve breakout retest metodu, taslakta kaynak mesajlara atfedilmiş ancak canlı LuxAlgo entry koduyla eşdeğer değil. Kodda opposite direction setup'ların guard tarafından reddedildiği v2 notu var (`engine/safe_orchestrator.py:2587-2594`). Her kural kaynak/hipotez olarak ayrılmalı.
- **Eski yol ile aktif yol ayrımı:** Bu genel SMC kuralları v1 motoruna kısmen yakın olabilir (`engine/smc.py`, `engine/signals.py`), fakat skill bunu canlı aktif kural seti gibi sunuyor; aktif `smc_v2.luxalgo.enabled: true` ayrımı başta belirtilmeli.

**Claude karşılaştırması:** VERDICT aynı; aktif confirmation farkı, kaynaksız R:R tablosu ve TP yüzdeleri konusunda örtüşüyoruz. Claude daha kesin runtime ayrıntılarıyla timeout'un LuxAlgo modunda 48 bar'a override edildiğini (`config:199`, orchestrator:2079-2081), mevcut motorun 2 hedefte 50/50 ve tek hedefte tam çıkış kullandığını, BE hareketinin zaten uygulandığını gösteriyor. Benim eklediğim noktalar: `profitable ise reverse` canlı guard ile çelişebilir ve aktif LuxAlgo'nın hedefleri sabit TP1/2/3 yerine aday seviyelerden hesaplanıyor. Claude'un `concepts` ile tek skill'de birleştirme önerisine katılıyorum.
