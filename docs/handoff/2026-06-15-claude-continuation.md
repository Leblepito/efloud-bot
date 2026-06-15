# 🔵 Claude — Devam Konuşması Kickoff (sonraki oturum, 2026-06-15 akşam)

> Bu dosya yeni bir Claude Code oturumunu temiz başlatmak için. Memory `efloud_state`
> RESUME point'i her oturum otomatik yüklenir; bu dosya o pointer'ın repo-kopyası +
> "ilk aksiyon" listesi (feedback: wrapup-repo-copy).

## Durum (master `7c19873`)

efloud-bot canlı mainnet, sorunsuz. Bu oturumda master'a inen: #199 #200 #196 #197 #170
#201(T-018 müşteri Telegram) #202(Hermes P-003 W2/W-R docs). #194 kapatıldı. **Açık PR yok.**

**Stratejik bağlam:** indicator-as-premium pivot (Wave-1 STRATEGY NO-GO → indicator premium;
Wave-2 redesign R&D backlog). W2 monetizasyon UNBLOCKED. Detay: memory `efloud_state` RESUME.

## ⚠️ Multi-session protokolü (ZORUNLU)

Gemini + Hermes paralel çalışıyor. Paylaşılan working-tree (`C:/Users/utkuc/Downloads/efloud-bot`)
başka oturumun checkout'unda OLABİLİR (Gemini detached HEAD'e çevirmişti). Bu yüzden:
- Merge'ler `gh pr merge` (server-side). Review'lar read-only `git diff`/`gh pr diff`.
- Kod yazımı/PATCH apply → İZOLE worktree (`git worktree add ... origin/master`), paylaşılan tree'de
  checkout YAPMA. Worktree dir-silme IDE-lock'a takılabilir (zararsız; deregister yeterli).
- Spesifik `git add`, `git add -A` YOK, destructive-op YOK.

## İlk aksiyonlar (öncelik sırası)

1. **Gemini entry-slippage backtest sonucunu kontrol et.** Hâlâ sürüyordu. Çıktı: `comparison.json`
   + `docs/handoff/2026-06-15-entry-slippage-backtest-results.md` (branch/patch). Geldiyse **gate'e göre
   review et:** Mode B adverse slippage'ı DÜŞÜRMELİ **VE** PF Mode A'nın ~%5'i içinde; inverted SL/TP
   yok, RR<min yok. PASS → testnet shadow (ayrı gate). FAIL → flag-flip RED. Prompt: `2026-06-15-gemini-entry-slippage-resume.md`.
2. **Hermes sıradaki teslimatını bekle/review et.** Prompt: `2026-06-15-hermes-next-tasks.md`
   (T-015 entitlements migration → T-011 server.js consent → T-016 webhook prep → T-017). Geldiğinde:
   `scp efloud-bot:/tmp/<patch>` → sha256 doğrula → izole worktree `git am` → review → push+PR+merge.
3. **Operatör hatırlatmaları (Claude değil, takip et):** F drill (`2026-06-15-efloud-t020-drill-runbook.md`,
   PASS→T-020 DONE+G-P3-6) · B.1-B.4 kararları (`p003-task-b-checklist.md`) · E UptimeRobot (5dk).

## Yapma

- Canlı config/compose/.env DOKUNMA (`configs/config.phase2_1k.yaml` = gerçek prod, dry_run:false MAINNET;
  root `config.yaml` inert). `pine/efloud_signals.pine` (SMC v2) ASLA ezilme; Wave-1 → `pine/u2algo/`.
- T-016'yı B teyidi olmadan CANLI açma. T-018 müşteri Telegram'ı T-016+legal sign-off olmadan aktive etme.
