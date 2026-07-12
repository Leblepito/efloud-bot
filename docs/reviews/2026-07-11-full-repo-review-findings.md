# 2026-07-11 Tam Repo Review — Bulgular ve Durum

4 paralel review ajanı (engine core / exchange+runner / smc_v2+backtest+data / pine)
+ manuel doğrulama. Operatör talimatı: tüm doğrulanan buglar düzeltildi.
Fix'ler: spec `docs/superpowers/specs/2026-07-11-tp-entry-anchored-targeting-and-bugfix-batch-design.md`.

## ✅ Bu batch'te DÜZELTİLDİ (testli)

| # | Yer | Özet |
|---|-----|------|
| TP | engine/signals.py + configs | v3.2 entry-anchored TP: RANGE_EQ (0.50) + MTF likidite blokları; mid'de smc_tp_targeting aktif |
| F1 | safe_orchestrator._check_leblep_limits | Var olmayan uppercase key'ler → v1 emir yolu ölüydü; gate artık feature-gated + nested/env okuma |
| F2 | safe_orchestrator._place_v2_entry_order | Canlı v2 open lifecycle'a mirror edilmiyordu → guard'lar + breaker kördü |
| F3 | exchange._move_sl_to_breakeven | "UNREACHABLE" sentineli SL id gibi saklanıyordu → yarım pozisyon stopsuz; şimdi fail-closed market-close |
| F4 | exchange SL_REPAIR | Aynı sentinel bugı → fiyat SL'yi geçmişken korumasız; şimdi market-close + loop copy fix |
| F5 | exchange._fallback_close | Başarısız close yutulup siblings iptal ediliyordu → çıplak pozisyon; şimdi abort + bool dönüş |
| F6 | exchange._fallback_close | TP1 sonrası full-size reduceOnly (-2022) → kalan miktar gönderiliyor |
| F7 | exchange.open_position | TP1/TP2 bağımsız truncate → dust; şimdi önce toplam round, TP2 = kalan |
| F8 | safe_orchestrator run_cycle | pause_new_entries reverse'ten SONRA değerlendiriliyordu → pozisyon flatten; şimdi önce |
| F9 | safe_orchestrator run_cycle | Exchange-open hatasında dedup kaydı kalıyordu → sinyal 1h yutuluyordu; şimdi pop+persist |
| F10 | pine/efloud_strategy(.pine/_v1) | position_size==0 reset'i entry barında state siliyordu → exitsiz pozisyon; transition-guard eklendi |
| F11 | backtest/engine.py | HTF/MTF/1d forming bar final OHLC ile dilimde → look-ahead; yalnız kapanmış barlar |
| F12 | engine/journal._load | Tek bozuk satır sonraki tüm trade'leri (kalıcı) siliyordu; satır-başına dayanıklılık |
| F13 | smc_v2/sl_calc | NaN/0 ATR → NaN SL; fail-closed setup reddi |
| F14 | preflight.py | dualSidePosition string normalize edilmiyordu → yanlış mode uyarısı |
| F15 | exchange.close_orphan + safety/orphan_protection | reduceOnly+positionSide / closePosition+reduceOnly → -1106; XOR pattern |
| F16 | safe_orchestrator STEP 7 | Canlıda exchange emirsiz pyramid → hayalet boyut; canlıda atlanıyor |
| F17 | .gitignore | .env.production ignore edilmiyordu (secret riski) |
| B1 | backtest/engine+metrics+comparison+cli | Batch-1 hijyen (2026-07-12): entry fill'lerine slippage (BT-4); stop_hunt_rate sim_closed_at ile canlandı (BT-7); step>1'de atlanan barlarda SL/TP taraması (BT-9); sim_close_ts fill barının damgası (BT-12); comparison negatif-v1 işaretli delta (BT-10); cli stale-cache uyarısı (BT-15) |
| B2 | engine/journal.update_adaptation | Adaptasyonlar (piramit/partial/hedge) artık _persist ediliyor — restart'ta kayıp bitti |
| B3 | engine/safety/guard.RateLimiter | weight>max fail-closed ValueError; boş-bucket IndexError + sonsuz bekleme öldü |

## ⏸ Bilinçli ERTELENDİ (ayrı operatör kararı / ayrı iş)

| Yer | Bulgu | Neden ertelendi |
|-----|-------|-----------------|
| safe_orchestrator:~1129 | Volatile-regime tighten-stops ölü gate (koşul unsatisfiable) + exchange amend yok | Davranış değişikliği — canlı SL yönetimine dokunuyor; backtest-gate ister |
| engine/intent.py:199 | check_weakness momentum-loss dalı ölü (analyze NEUTRAL zorluyor) | Canlı de-risk davranışını değiştirir; default-OFF flag + backtest ister |
| safety/breaker.record_trade_correction | Tail-recompute streak'i kısaltabilir (feature default-OFF) | Feature kapalı; açılmadan önce düzeltilmeli |
| exchange OrderManager.positions | Thread-lock yok (API event-loop vs bot thread) | Mimari değişiklik; ayrı tasarım |
| safe_orchestrator lease release | Erken return'lerde try/finally kapsamı | F9 en sık yolu kapattı; kapsamlı refactor ayrı PR |
| safe_orchestrator:1321 | Dedup key round(entry,2) sub-$1 coinlerde kaba | Davranış ayarı; sinyal sıklığını etkiler |
| exchange:1623 | BE-SL boyutu pos.size/2 (reconcile bn_size değil) | F3 fail-closed yolu ana riski kapattı; sizing iyileştirmesi ayrı |
| exchange._record_close | tp1_hit sonrası fallback PnL tek-leg tahmini | Muhasebe hijyeni; breaker'a etkisi audit'li ayrı iş |
| smc_v2/triggers:109 | trigger_idx LTF↔HTF eksen karışıklığı (anchor havuzu daralıyor) | Konservatif yönde bozuk; düzeltme SL seçimini değiştirir → backtest-gate |
| smc_v2/confirmation:59 | Stale engulfing onayı (geçmiş bar) | Entry davranışı değişir → backtest-gate |
| data/fetcher | Bar trim + gap detection kombinasyonu | Data pipeline değişikliği; cache yeniden doğrulama ister |
| pine satellites | publish/v1/wave1 dosyaları eski chain/ATR/repaint | Ayrı Pine senkron oturumu (PINE_SPEC §19) |

## Not
- Canlı etki için VPS'te container recreate gerekir (`docker compose up -d`).
- B1 (BT-4/BT-9) öncesi Python backtest sonuçları iyimserdir: entry slippage'sız
  ve step>1 koşularında atlanan barlardaki SL/TP fill'leri kayıp.
- F10 öncesi Pine strategy backtest sonuçları geçersizdir (exitsiz koşuyordu).
- F11 öncesi Python backtest sonuçları iyimserdir (MTF look-ahead).
