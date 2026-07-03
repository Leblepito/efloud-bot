# 2026-07-03 — Merge, Hata Ayıklama ve Kalıcı Repo Revizyonları

## Yapılanlar (bu session, Cowork/Claude)

1. **Merge:** `master` = origin/master (22 commit) + `feat/v2-nipio-dashboard` (9 commit).
   Çakışma yok. Merge commit: `908d601`.
2. **Hata ayıklama (11 kırık test, 2 kök neden):**
   - Pullback detection (`d03378e`) eski zone-touch spec'iyle çelişiyordu.
     Operatör kararı: pullback davranışı korundu; 5 eski test yeni state
     machine'e göre güncellendi (`663e504`, `8485134`).
   - SL/TP precision hardening (`27e0d74`) sonrası bare `MagicMock()` exchange
     fixture'ları `float(MagicMock()) == 1.0` üretip 8 testi bozuyordu; 6 dosyaya
     identity `price_to_precision`/`amount_to_precision` mock'ları eklendi (`d7fa78f`).
   - `safe_orchestrator.py`'den 4 adet `[DEBUG] print()` kalıntısı silindi.
3. **Kalıcı repo revizyonları:**
   - `state/ai_sentiment_registry.json` git takibinden çıkarıldı (runtime state,
     `state/` zaten gitignore'da; canlı state'in commit'lenme riski kapandı) (`a7a52cf`).
   - `u2algo-site/.gitignore`: `.env.*` kuralı `.env.example`'ı da yutuyordu;
     `!.env.example` negasyonu eklendi (`a7a52cf`).
   - 58 merged local branch silindi (içerikleri master'da); bunları kilitleyen
     stale worktree kayıtları kaldırıldı.
   - `.git/config` sync hasarıyla boşalmıştı; origin/vps remote'ları ve
     `core.autocrlf=true` ile yeniden inşa edildi.

## Operatörün Windows'ta çalıştırması gerekenler

```bash
cd /c/Users/utkuc/Downloads/efloud-bot
git fsck --no-dangling        # bütünlük kontrolü
git push origin master        # 15 commit'i kalıcılaştır (sandbox'ta credential yok)
git worktree prune -v         # kalan stale worktree kayıtları (Windows'ta doğru tespit edilir)
```

`.kilo/worktrees/`, `.claude/worktrees/`, `.worktrees/` klasörleri artık bağlantısız
kopyalardır; içlerinde ihtiyacın olan bir şey yoksa silinebilirler.

## Test durumu (merge sonrası doğrulama)

- `tests/`: 508 passed, 6 skipped
- `backend/tests/` (smc_v2 hariç): 1335+ passed, 0 gerçek hata
- `backend/tests/smc_v2/`: 149 passed
- Yavaş testler (CI'da uzun timeout ister): `test_backtest_engine_single.py`
  (`test_engine_deterministic` ~40s), `test_backtest_engine_portfolio.py` (~41s).

## Cowork/sandbox sync uyarısı (gelecek sessionlar için)

Cowork sandbox'ının mount senkron katmanı bu session'da üç kez git metadata'sını
bozdu: `.git/index` (2x, null-byte imzası), `.git/config` (tamamen boşaldı),
ayrıca Windows tarafında yapılan dosya edit'leri Linux mount'unda gecikmeli/kesik
göründü. Sandbox'tan çalışırken:
- Commit öncesi `GIT_INDEX_FILE=/tmp/...` ile sandbox-local index kullan.
- Dosya yazımlarını tek seferde, deterministik yap (git içeriği + replace).
- Her git hatasında önce `python3 -c "print(open('.git/<dosya>','rb').read().count(b'\x00'))"` ile null-byte kontrolü yap.

## Ek — Açık işlerin ele alınması (aynı gün, devam session'ı)

- **SEC-1** ✅ zaten kapalıydı (PR #238, `backend/auth.py` fail-closed + testler).
  Kalan tek adım operasyonel: VPS prod `.env`'de `ENV=production` ve gerçek bir
  `SESSION_SECRET` set olduğunu doğrula (yoksa backend fail-closed başlamaz —
  bu kasıtlı).
- **H2/H3/H4** ✅ kod tarafı zaten uygulanmıştı (shadow default True,
  `reject_wide_sl` toggle, drift guard fail-closed). Eksik olan H3 test kapsamı
  eklendi: `backend/tests/test_position_guard_wide_sl.py` (4 test, `1b99415`).
  H3'ü canlıda aktive etmek için: config `safety.reject_wide_sl: true`
  (risk-ops onayıyla; reject oranını önce shadow'da izle).
- **Edge Measurement Core** ✅ master'a merge edildi (`ea372f7`, additive,
  `signal_ledger.enabled: false`). C4/H1/H7/M1/M2 için zorunlu NET-cost gate'in
  altyapısı artık master'da. Aktivasyon: config'de `signal_ledger.enabled: true`
  + resolver cadence; detay branch handoff'unda
  (`docs/handoff/2026-06-19-edge-measurement-core-handoff.md`).
- **C4 / M1 / M2** ⏳ GATED — kod-only merge sözleşme ihlali olur. Sıra:
  (1) signal_ledger'ı canlıda aç, (2) yeterli N sinyal biriktir,
  (3) `edge_report` NET-cost çıktısıyla conf-threshold sweep (C4),
  is_discovery düzeltmesi (M1) ve confluence attribution (M2) kararlarını ver.

## Ek 2 — Branch kararları (2026-07-03, oturum sonu)

74 unmerged local branch salt-okunur analizle karara bağlandı (`git cherry` +
kod karşılaştırma ile doğrulama): **hiçbirinde master'da olmayan iş yoktu** —
16 fix/* branch'inin tamamı dahil ~74 branch silindi (origin kopyaları duruyor).

**PARK edilen 7 branch (gate/karar bekliyor):**
- `feat/smc-sl-tp-redesign` — flag-gated SL/TP deneyi; backtest DIRECTIONAL
  NO-GO, rigorous RERUN gate'i geçmeden merge YASAK.
- `feat/audit-remediation` — C1-C3/H2-H4/M3-M4 remediasyonu; master follow-up'ı
  ile satır satır karşılaştırma + risk-ops gerek.
- `config/per-mode-sizing` — tiered sizing (scalp 3x/50 · mid 5x/80 · long
  10x/100); canlı risk parametresi → risk-ops + operatör onayı şart.
- `clarity-action` — BotRunner crash-loop safety; master bot_runner ile
  örtüşme kontrolü gerek.
- `feat/track1-premium-launch` — LemonSqueezy ürün-mapping + entitlements;
  premium launch gündeme gelince değerlendir.
- `feat/slippage-telemetry`, `feat/async-review-hardening` — düşük öncelik.

Cherry-pick adayları (branch silindi, commit SHA'lar origin'de):
overseer'ın "healthz HALTED→200 suspended" fix'i · t021 uptimerobot-as-code.

**Kalan local branch'ler:** master, main + yukarıdaki 7 PARK. Remote temizliği
(origin'deki ~110 stale branch) istenirse ayrı bir oturumda `git push origin
--delete` toplu komutuyla yapılabilir.
