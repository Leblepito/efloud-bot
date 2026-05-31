# Design Spec: Trade-Horizon Profiles (Timeframe Bundles)
Date: 2026-05-31
Status: APPROVED

This specification details the implementation of **Trade-Horizon Profiles** (Timeframe Bundles) for Efloud SMC Trade Bot v2.1. It establishes a robust, single-source-of-truth framework for timeframe configurations to eliminate operator error, ensure fail-fast startup safety, and synchronize TradingView Pine Script v6 visual analysis with the Python bot's execution logic.

---

## 📖 Rationale & Price Action Alignment

Based on the canonical **Efloud Course Notes** (`Efloud Notları.md`), price action analysis must follow a systematic top-down approach (*Tümegelim*):
1. **HTF (High Timeframe):** Identifies institutional order flow, primary trend direction, major HTF Order Blocks, and range constraints. As noted: *"Smart money monthly, weekly, daily zaman dilimlerinde işlem alır."*
2. **MTF (Medium Timeframe):** Measures retracement depth (Equilibrium / OTE), identifies Indecision Candles (IC), Breaker Blocks (BB), and mitigation zones.
3. **LTF (Low Timeframe / Entry):** Pinpoints precise execution zones with low risk and tight stop-loss placement, detecting Swing Failure Patterns (SFP) and local OTE clusters. As noted: *"HTF'de pahalılık bölgesini belirledikten sonra, LTF'de de alanlar belirleyerek, az riskli işlem oluşturulur."*

The defined profiles perfectly reflect these principles.

---

## 📊 Canonical Profile Definitions

We define three canonical profiles. Timeframes are strictly monotonically increasing (`Entry < MTF < HTF`) to prevent target-inversion errors and repaint issues.

| Profile | Entry (LTF) | MTF (Medium) | HTF (High) | Zincir (Dk) | Rationale & Trade Type |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`scalp`** | `5m` | `1h` | `12h` | `5 < 60 < 720` | High-frequency intraday momentum scalping. |
| **`mid`** | `15m` | `1h` | `4h` | `15 < 60 < 240` | Standard multi-hour day trading. |
| **`long`** | `1h` | `8h` | `1w` | `60 < 480 < 10080` | Swing trading (2-3 months perspective) utilizing weekly institutional bias with 1h execution. Entry ladder (5m/15m/1h) preserved across profiles; weekly HTF reflects *"smart money weekly işlem alır"*. |

> **Karar notu (2026-05-31):** Kullanıcı `long` için `1h/8h/64h` belirtmişti. `64h` Binance-native değil. İki seçenek değerlendirildi: (a) `1h/8h/3d` (64h'e en yakın native), (b) `1h/8h/1w` (entry merdivenini korur + ders-notlarındaki haftalık kurumsal HTF). **Seçilen: (b) `1h/8h/1w`.** Reddedilen Gemini önerisi `15m/8h/1w` idi — `mid` ile entry çakışması (her ikisi de 15m grafik) horizon merdivenini bozuyordu.

---

## 🛠️ Implementation Plan

### Part 1: Bot Changes (Python Resolver)

1. **Config Schema (`configs/*.yaml`):**
   We introduce the `profile` key under the `timeframes` section:
   ```yaml
   timeframes:
     profile: mid       # scalp | mid | long | custom
     entry: 15m         # Fallback if profile is 'custom' or missing
     mtf: 1h
     htf: 4h
     kline_limit: 500
   ```

2. **Python Resolver (`data/timeframes.py`):**
   Add a validator and resolver function in `data/timeframes.py` to enforce monotonic integrity and fail-fast behavior:
   ```python
   PROFILES = {
       "scalp": ("5m", "1h", "12h"),
       "mid": ("15m", "1h", "4h"),
       "long": ("1h", "8h", "1w"),
   }

   def resolve_timeframes(cfg: dict) -> dict:
       tf_cfg = cfg.get("timeframes", {})
       profile = tf_cfg.get("profile")
       kline_limit = tf_cfg.get("kline_limit", 500)

       if not profile or profile == "custom":
           entry = tf_cfg.get("entry")
           mtf = tf_cfg.get("mtf")
           htf = tf_cfg.get("htf")
       elif profile in PROFILES:
           entry, mtf, htf = PROFILES[profile]
       else:
           raise ValueError(f"Unknown timeframe profile: {profile!r}")

       # Monotonic increasing assert guard
       from data.timeframes import tf_to_minutes
       if not (tf_to_minutes(entry) < tf_to_minutes(mtf) < tf_to_minutes(htf)):
           raise ValueError(
               f"Timeframe chain must be strictly monotonically increasing: "
               f"{entry} ({tf_to_minutes(entry)}m) >= {mtf} ({tf_to_minutes(mtf)}m) >= {htf} ({tf_to_minutes(htf)}m) is invalid!"
           )

       # Optimize kline_limit for weekly timeframes to save bandwidth and speed up processing
       if htf == "1w" and kline_limit > 250:
           kline_limit = 250  # Cap weekly history to ~4.8 years of data

       return {
           "entry": entry,
           "mtf": mtf,
           "htf": htf,
           "kline_limit": kline_limit,
           "profile": profile or "custom"
       }
   ```

3. **Integration — config-load anında, TÜM giriş noktaları için (DÜZELTİLDİ):**
   `cfg["timeframes"]`'i şu noktalar **doğrudan** okuyor: `main.py:379`, `backend/bot_runner.py:354` (FastAPI daemon — prod path), `backtest/cli.py` (×4), `scripts/run_phase_a.py`. Yalnızca `main.py`'yi yamalamak daemon'da **sessiz yanlış-TF** bug'ı yaratır (loglar "scalp" der, daemon mid TF okur).
   * **Çözüm:** `resolve_timeframes(cfg)` çözülmüş `entry/mtf/htf/kline_limit`'i **`cfg["timeframes"]` içine geri yazar (in-place mutate)**. `main.py:load_config()` içinde `yaml.safe_load` sonrası bir kez çağrılır → tüm aşağı tüketiciler çözülmüş değeri görür. `bot_runner.py`'nin kendi config yüklemesi de aynı çağrıyı yapar (ayrı yükleme path'i ise).
   * **`safe_orchestrator.py` DEĞİŞTİRİLMEZ** — orchestrator cfg timeframe'lerini okumuyor (`df_htf/df_mtf/df_entry` kendisine geçiriliyor). Güvenlik-kritik dosyaya gereksiz dokunuş YOK.
   * Startup log: `[INFO] Timeframe Profile Active: {profile} ({entry} → {mtf} → {htf})`

---

### Part 2: Pine Script Mirror

Dosya filename'leri: `efloud_signals_v1.pine`, `efloud_strategy_v1.pine` (V1 = 3-TF: htf+mtf+entry) ve `efloud_signals.pine`, `efloud_strategy.pine` (V2 = **2-TF: yalnızca htf+entry, mtf YOK**).

**V1 dosyaları (3-TF):** profil dropdown htf+mtf'i set eder; entry = grafik TF.
```pine
// ── Timeframe Profiles ──
profileMode = input.string("mid", "Timeframe Profile", options = ["scalp", "mid", "long", "custom"], group = "ZAMAN DİLİMLERİ")
customMtf   = input.timeframe("60",  "Custom MTF TF", group = "ZAMAN DİLİMLERİ")
customHtf   = input.timeframe("240", "Custom HTF TF", group = "ZAMAN DİLİMLERİ")

// entry = grafik TF (profile.entry yalnızca uyarı için karşılaştırılır)
profEntry = profileMode == "scalp" ? "5"   : profileMode == "mid" ? "15"  : profileMode == "long" ? "60"  : "" // "" = custom (uyarı yok)
mtfTf     = profileMode == "scalp" ? "60"  : profileMode == "mid" ? "60"  : profileMode == "long" ? "480" : customMtf
htfTf     = profileMode == "scalp" ? "720" : profileMode == "mid" ? "240" : profileMode == "long" ? "W"   : customHtf // '1w' → "W"
```
**V2 dosyaları (2-TF):** mtf satırı YOK; yalnızca `profEntry` + `htfTf` çözülür (`mtfTf` üretilmez). Aksi halde V2'ye kullanılmayan input enjekte edilir.

> Pine TF kodlaması: 12h="720", 8h="480", 4h="240", 1h="60", 15m="15", 5m="5", 1w="W". (`request.security` "simple string" ternary'sini kabul eder — derlenir.)

#### Warn on Incorrect Chart Timeframe
To ensure the operator places the indicator on the correct execution timeframe (Entry):
```pine
// profEntry == "" → custom profil, uyarı yok. Aksi halde grafik TF profil entry'siyle eşleşmeli.
var table warnTbl = table.new(position.top_right, 1, 1)
if barstate.islast and profEntry != "" and timeframe.period != profEntry
    table.cell(warnTbl, 0, 0, "⚠️ YANLIŞ ZAMAN DİLİMİ!\nGrafik TF'i " + profEntry + " olmalı (profil: " + profileMode + ")", bgcolor = color.new(color.red, 20), text_color = color.white, text_size = size.small)
```
> `var table` global scope'ta bir kez yaratılır (Pine repaint-safe); hücre yalnızca son barda + yanlış TF'de doldurulur.

---

## 🔒 Risk-Ops & Rollout Plan

1. **Flat Position Requirement:** Timeframe profile modifications must only be done when flat (no open positions) and followed by a bot restart. This avoids state disruption on existing position tracking threads.
2. **Default Backward Compatibility:** If `profile` is omitted, the bot defaults to the current hardcoded `15m`/`1h`/`4h` (`mid` configuration) to prevent regressions on active `config.phase2_1k.yaml` runs.
