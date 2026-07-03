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
