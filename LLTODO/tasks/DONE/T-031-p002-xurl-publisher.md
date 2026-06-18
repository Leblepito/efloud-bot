# T-031 — P-002 M1 publisher: xurl CLI Adapter (Lane E)

Epic: P-002
Claimed by: @hermes
branch: feat/p002-m6-templates (renderer PR'a merge edilecek)
claimed_at: 2026-06-19T19:00:00Z
status: DONE (push bekliyor)

## Goal
xurl Go binary üzerinden X/Twitter'a yayın. Default OFF (config.xurl.enabled
= false → noop). Single-tweet + thread reply chain.

## Scope
- `scripts/lane_e/publishers/xurl.py` — XurlPublisher (Publisher protocol)
- `scripts/lane_e/tests/test_xurl_publisher.py` — 13 hermetic test (subprocess mock)
- Default OFF (`enabled=False`), binary yoksa error, subprocess timeout/error yakalanır

## Acceptance
- [x] 8/8 LLTODO lint PASS
- [x] 13 unit test PASS (disabled + enabled + binary missing + thread + reply + timeout + called-process-error)
- [x] Lane topology: publisher research lane'e (backend/social) dokunmaz
- [x] Defense in depth: compliance gate LaneEPublisher'da; publisher tekrar kontrol etmez
- [x] PublishResult.ok=False error path'lerde, error mesajı içeride

## Out of scope
- LaneEPublisher orchestration (multi-publisher dispatch) — sonraki sprint
- Retry/backoff policy — operatör kararı
- Telegram approval adapter (callback_data'yı consume eden) — T-032
