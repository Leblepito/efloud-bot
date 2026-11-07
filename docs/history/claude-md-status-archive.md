# CLAUDE.md status archive

The dated status notes that lived in `CLAUDE.md` until 2026-11-07, moved verbatim when CLAUDE.md
became constitution-only (spec `docs/superpowers/specs/2026-11-07-operator-decisions-and-backtest-restore-design.md`
§1 #4). This is history: the live state is `collab/STATUS.md`. Some facts below are known to be
stale (for example the Supabase "PGRST205" note and the Railway URL); see #329.

## From the CLAUDE.md header line (as of 2026-10-02)

**Son çalışma (2026-10-02, operatör revizyonları):** BOS kırılımları da setup üretiyor (`658a905` — CHoCH ile aynı pullback giriş akışı), acil bakiye HALTI kaldırıldı (`b2154c5` — emergency_balance_threshold=0), v1 MARKET girişi v2 canlı sembolde susturuldu (`b2154c5`), bölge aşım toleransı 0.5→2.0 ATR + volatil rejim girişleri açıldı (`228382d`). **v2 AKTİF:** `smc_version=v2`, `smc_v2_symbols` dolu, `smc_v2_shadow=false`. *(Önceki: 2026-08-12 audit-fixes — 10 bayat test onarıldı, sızmış kimlik bilgileri env'e taşındı, birleşik panel Faz 2, backend event-loop + login rate-limit, /api/equity şema birleştirmesi.)*

## Son Durum & Güncel Gelişmeler (as of 2026-07-26)

1. **Social Publishing Pipeline (YENİ)**:
   - Bot sinyallerinden otomatik chart + video + caption üretimi: `scripts/daily_social_run.py`
   - Chart renderer: `scripts/chart_render.py` (OHLCV cache → markalı PNG, ENTRY/SL/TP seviyeli)
   - Video renderer: `scripts/video_render.py` (chart PNG → MP4, ffmpeg default)
   - Platform bundle'lar: `scripts/lane_g_social.py` (X/IG/Reels/YT)
   - Yayın dispatch: `scripts/lane_g_publish.py` (3-gate safety)
   - Higgsfield adapter: `scripts/higgsfield_adapter.py` (opt-in, ⚠️ fiyat etiketlerini bozuyor)
   - Kalıcı doküman: `skills/social-publishing/SKILL.md` — tüm AI modelleri için
   - Bug fix: Instagram `render_promo_card` import hatası, YouTube `video_path=None`
   - Test: 229 test, sıfır regresyon

2. **u2algo-site & Railway Servisi** (Railway root dir `/u2algo-site`; bu repoda KALMALI):
   - Statik HTML + Node.js 20 `server.js` (Railway NIXPACKS, `startCommand: node server.js`) pazarlama sayfası; `u2algo-site` servisi.
   - Canlı URL: `https://u2algo.com` (`www` → apex 301, #324). Eski `u2algo-site-production.up.railway.app` adresi 404 döner (2026-11-07).

2. **Supabase REST & Fallback Entegrasyonu**:
   - `server.js` backend katmanı 3'lü veritabanı korumasıyla güncellendi:
     1. `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` varsa Supabase REST API ile kayıt. (Canlıda şu an bu aktif!).
     2. `DATABASE_URL` veya `SUPABASE_DATABASE_URL` varsa doğrudan PostgreSQL (`pg` driver) ile kayıt ve otomatik tablo migrasyonu (`ensureWaitlistTable`).
     3. Her iki DB bağlantısı koptuğunda veya erişilemez olduğunda `local-jsonl` (`data/waitlist_leads.jsonl`) fallback korumasıyla kesintisiz `200 OK` yanıtı.
   - **Mevcut Canlı Durum (2026-11-07 doğrulandı)**: `GET https://u2algo.com/api/waitlist/health` → `database: ready, backend: supabase`. Waitlist kayıtları Supabase'e yazılıyor; yerel JSONL yalnız yedek (Railway dosya sistemi her deploy'da sıfırlanır).

3. **Hermes MCP Postgres Sunucusu**:
   - Local makinede `supabase_postgres` MCP server kuruldu (7 tool: `health`, `list_tables`, `table_columns`, `ensure_waitlist_leads`, `waitlist_count`, `waitlist_list`, `waitlist_insert`).
