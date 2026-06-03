"""Multi-Timeframe signal generation — Efloud setup akışı."""

import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from .smc import SMCEngine
from .confluence import calc_confluence
from .levels import Level
import pandas as pd
import httpx
import os
import json
from utils.cache import SentimentCache

log = logging.getLogger("efloud.signals")

# Global cache for structure validations
_struct_cache = SentimentCache()

def _normalize_symbol(symbol: str) -> str:
    """Canonicalize symbol form to `BASE/QUOTE` (with slash).

    Tolerates exchange-API forms like `ETHUSDT` (no slash) by inserting one
    before the quote currency. Must remain pure (no I/O) so it can be reused
    in tests.
    """
    if not symbol or "/" in symbol:
        return symbol
    # Default: assume the last 4 chars are the quote (USDT, BUSD, USDC).
    # Adjust if/when we trade against shorter-quote pairs.
    for quote in ("USDT", "USDC", "BUSD"):
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]
            return f"{base}/{quote}"
    return symbol


def resolve_min_confluence(
    symbol: Optional[str],
    global_min: int,
    symbol_overrides: Optional[Dict[str, int]],
) -> int:
    """Pick the effective confluence threshold for a given symbol.

    Lookup precedence: explicit per-symbol override > global default.
    Returns `global_min` if symbol is unknown/missing or overrides are empty.

    Symbol format is normalized so that `ETHUSDT` resolves the same as
    `ETH/USDT`. Override values of 0 (literally zero) are respected — only
    `None`/missing keys fall back.
    """
    if not symbol_overrides or symbol is None:
        return global_min
    canonical = _normalize_symbol(symbol)
    if canonical in symbol_overrides:
        return symbol_overrides[canonical]
    if symbol in symbol_overrides:
        return symbol_overrides[symbol]
    return global_min


def _format_score_histogram(buckets: Dict[int, int], top_n: int = 3) -> str:
    """Render a score-bucket histogram as `score×count` pairs, highest-score first.

    Returns an empty string when no buckets are populated. Used in the reject
    summary log so that calibration decisions can be made from observed
    confluence distribution rather than just the maximum.
    """
    if not buckets:
        return ""
    top = sorted(buckets.items(), key=lambda kv: kv[0], reverse=True)[:top_n]
    return " ".join(f"{score}×{count}" for score, count in top)


def _resolve_deviation_tp2(raw_tp2, tp1, min_tp, price, risk, is_long):
    """Range-deviation TP2'yi güvenli hedefe çöz.

    1) Karlı-taraf clamp: TP2 asla min R:R eşiğinin zarar tarafında olmasın
       (range ekstremi entry'nin yanlış tarafında kalabilir).
    2) TP2 > TP1 invariant: clamp sonrası TP2, TP1'e çökerse (dar range + geniş
       SL) discovery extension'a (2.618R) düş — aynı fiyatta çift TP emrini ve
       sessiz tek-hedef dejenerasyonunu önler.
    """
    tp2 = raw_tp2
    if is_long:
        if tp2 < min_tp:
            tp2 = min_tp
        if tp2 <= tp1:
            tp2 = price + risk * 2.618
    else:
        if tp2 > min_tp:
            tp2 = min_tp
        if tp2 >= tp1:
            tp2 = price - risk * 2.618
    return tp2


def _enforce_tp2_beyond_tp1(tp2, tp1, price, risk, is_long):
    """TP2'yi daima TP1'den DAHA UZAĞA zorla (target-inversion koruması, Y5).

    TP2, TP1'e eşit/daha yakın olursa borsa SHORT/LONG TP emrini "anında
    tetiklenir" (-2021) diye reddedebilir veya iki-aşamalı çıkış dejenere olur.
    Çözüm: TP2'yi en az TP1+0.5R kadar öteye, en uzak Fibonacci uzantısına
    (2.618R) çek. Davranış, generate_signals içindeki eski inline guard ile
    BİREBİR aynıdır.
    """
    if is_long:
        if tp2 <= tp1:
            tp2 = max(tp2, tp1 + risk * 0.5, price + risk * 2.618)
    else:
        if tp2 >= tp1:
            tp2 = min(tp2, tp1 - risk * 0.5, price - risk * 2.618)
    return tp2


@dataclass
class Signal:
    direction: str          # "LONG" | "SHORT"
    entry: float
    sl: float
    tp1: float              # Swing TP
    tp2: float              # Fib 1.618 TP
    rr1: float
    rr2: float
    confluence: int
    reasons: List[str] = field(default_factory=list)
    timestamp: str = ""
    in_ote: bool = False
    in_ob: bool = False
    has_sfp: bool = False
    zone: str = ""
    # Per-signal free-form metadata bag. The Runtime Agent Team (Part A
    # of the agent-team plan) writes its verdict here so downstream
    # code (journal, DB) can persist it without changing the schema.
    # Always a plain dict — never assume the key set; downstream readers
    # should use ``.get("agent_review")`` and tolerate ``None``.
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _df_to_compact_csv(df: pd.DataFrame, limit: int = 20) -> str:
    """Format the last N bars of a DataFrame into a compact CSV string.

    Production OHLCV data has open/high/low/close/volume columns, but several
    unit tests and defensive call paths use minimal candle frames. Gemini
    validation is a non-blocking enrichment layer, so missing optional columns
    must degrade to a usable compact representation instead of aborting signal
    generation.
    """
    if df is None or df.empty:
        return "No data available."
    sub_df = df.iloc[-limit:]
    lines = ["Time,Open,High,Low,Close,Vol"]
    for idx, row in sub_df.iterrows():
        ts_str = idx.strftime("%m-%d %H:%M") if isinstance(idx, pd.Timestamp) else str(idx)
        close = float(row.get("close", row.get("open", 0.0)))
        open_ = float(row.get("open", close))
        high = float(row.get("high", max(open_, close)))
        low = float(row.get("low", min(open_, close)))
        volume = int(row.get("volume", 0))
        lines.append(f"{ts_str},{open_:.4f},{high:.4f},{low:.4f},{close:.4f},{volume}")
    return "\n".join(lines)


def validate_signal_with_gemini(
    symbol: str,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    df_htf: pd.DataFrame,
    df_mtf: pd.DataFrame,
    df_entry: pd.DataFrame,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a trade signal's market structure using Gemini 1.5 Flash.

    Public signature is stable; the internal HTTP call is delegated to
    :class:`engine.agents.GeminiClient` (canonical A0 refactor). Behaviour
    is unchanged: missing key, timeout, or parse error → fall back to
    ``{"valid": True, "confidence": 1.0, ...}`` so downstream signal
    generation is not blocked.
    """
    # Provider + key are resolved by the shared LLM factory (default Claude,
    # gemini fallback via LLM_PROVIDER). A no-key / outage converges on the
    # pass-through fallback below — the deterministic signal is never blocked.

    # Format timeframes
    htf_csv = _df_to_compact_csv(df_htf, limit=20)
    mtf_csv = _df_to_compact_csv(df_mtf, limit=20)
    entry_csv = _df_to_compact_csv(df_entry, limit=20)

    prompt = f"""
You are a Senior Smart Money Concepts (SMC) Trading Expert.
Analyze the market structure for {symbol} to validate a potential {direction} setup:
- Entry Price: {entry}
- Stop Loss: {sl}
- Take Profit: {tp}

Timeframe Data (last 20 candles):
HTF (4h):
{htf_csv}

MTF (1h):
{mtf_csv}

Entry TF (15m):
{entry_csv}

SMC Validation Criteria:
1. Verify if the recent Break of Structure (BOS) or Change of Character (CHoCH) represents true institutional order flow (smart money entering) or if it is just a retail trap / liquidity sweep.
2. Confirm if the Stop Loss level is placed safely below/above key order blocks or liquidity pools.
3. Confirm if the overall higher-timeframe (4h) bias supports this entry direction.

Output ONLY a raw JSON structure matching exactly this template:
{{"valid": true, "confidence": 0.85, "reasoning": "Explain your key structural observation briefly (1-2 sentences)"}}
Do not include any markdown backticks or extra text, just the raw JSON.
"""

    # Check cache
    cached = _struct_cache.get(prompt)
    if cached:
        return cached

    # Delegate the HTTP call to the shared provider factory (default Claude).
    # Imported lazily to keep engine.signals importable in environments
    # where engine.agents is not on the path (legacy unit tests).
    from engine.agents.llm import make_llm_client

    # An explicit api_key is threaded as an override; otherwise the client
    # self-resolves its provider's key from env (never pass a Gemini key to
    # a Claude client — production leaves api_key unset here).
    client = make_llm_client({"api_key": api_key} if api_key else {})
    result = client.complete_json(prompt, timeout=10.0)

    if not result:
        # Fail-safe: no key, HTTP error, parse failure — all converge here.
        log.warning("Gemini signal validation unavailable — falling back to pass-through.")
        return {"valid": True, "confidence": 1.0,
                "reasoning": "Fallback due to API failure or timeout."}

    # Defensive: ensure the schema is what callers expect. If the LLM
    # returned something missing the keys, the SignalValidatorAgent
    # contract is "we don't know" — same fallback.
    if not all(k in result for k in ("valid", "confidence", "reasoning")):
        log.warning(f"Gemini validation returned unexpected schema: {result!r}")
        return {"valid": True, "confidence": 1.0,
                "reasoning": "Fallback due to unexpected LLM schema."}

    _struct_cache.set(prompt, result)
    return result


def generate_signals(
    engine: SMCEngine,
    df_htf: pd.DataFrame,
    df_mtf: pd.DataFrame,
    df_entry: pd.DataFrame,
    min_confluence: int = 50,
    min_rr: float = 1.5,
    fib_ext: float = 1.618,
    recency_bars: int = 20,
    df_daily: Optional[pd.DataFrame] = None,   # 4. TF — 1d filter (opsiyonel)
    daily_filter_strict: bool = False,          # True = 1d ters yön → reddet
    symbol: Optional[str] = None,               # NEW — for per-symbol threshold lookup
    symbol_confluence_overrides: Optional[Dict[str, int]] = None,  # NEW
    levels: Optional[List[Level]] = None,       # NEW — injected levels for PA confluence
    ai_sentiment: Optional[Dict[str, Any]] = None,  # NEW — async macro sentiment
) -> List[Signal]:
    """
    4-Timeframe Efloud akışı:
    1. Daily (1d) → makro yön filtresi (opsiyonel, +confluence puanı)
    2. HTF (4h)  → bias + POI
    3. MTF (1h)  → CHoCH onay
    4. Entry (15m) → giriş + SL/TP

    daily_filter_strict:
      False = 1d sadece +5 confluence puanı verir (yumuşak)
      True  = 1d ters yön ise sinyal tamamen reddedilir (sıkı)

    recency_bars: Sadece son N bar içinde oluşan break'leri sinyal olarak değerlendir.
    """
    # ── HTF analiz ──
    htf = engine.analyze(df_htf)
    htf_bias = htf["trend"]
    htf_bias_original = htf_bias
    htf_fvgs = htf["active_fvgs"]
    htf_obs = htf["active_obs"]

    if htf_bias == "UNDEF":
        # Fallback: Son 40 HTF bar'ının eğiminden trend çıkar
        # Eğer fiyat başlangıca göre >%2 yukarıdaysa BULL, <%-2 BEAR
        if len(df_htf) >= 40:
            recent_close = float(df_htf["close"].iloc[-1])
            past_close = float(df_htf["close"].iloc[-40])
            change_pct = (recent_close - past_close) / past_close * 100
            if change_pct > 2.0:
                htf_bias = "BULL"
                log.info(f"HTF fallback: +{change_pct:.1f}% slope → BULL")
            elif change_pct < -2.0:
                htf_bias = "BEAR"
                log.info(f"HTF fallback: {change_pct:.1f}% slope → BEAR")
            else:
                e_range = engine.range_info(df_entry)
                if e_range and (e_range.discount or e_range.premium):
                    htf_bias = "BULL" if e_range.discount else "BEAR"
                    log.info(f"HTF flat but Range active → trading range play ({htf_bias})")
                else:
                    log.info(f"HTF undefined, slope neutral ({change_pct:+.1f}%), and no active range — skipping")
                    return []
        else:
            log.info("HTF bias undefined and insufficient data — skipping")
            return []

    # ── Daily (1d) filter ── (opsiyonel — 4. TF)
    daily_bias = "UNDEF"
    if df_daily is not None and len(df_daily) >= 30:
        d_analysis = engine.analyze(df_daily)
        daily_bias = d_analysis["trend"]
        # UNDEF ise 30-bar slope fallback (1d için ~30 gün)
        if daily_bias == "UNDEF":
            d_close_now = float(df_daily["close"].iloc[-1])
            d_close_past = float(df_daily["close"].iloc[-30])
            d_change = (d_close_now - d_close_past) / d_close_past * 100
            if d_change > 5.0:
                daily_bias = "BULL"
            elif d_change < -5.0:
                daily_bias = "BEAR"
            log.info(f"Daily slope fallback: {d_change:+.1f}% → {daily_bias}")

        # Strict mode: daily ters yönde ise tamamen reddet
        if daily_filter_strict and daily_bias != "UNDEF" and daily_bias != htf_bias:
            log.info(f"📅 Daily filter STRICT: 1d={daily_bias} vs 4h={htf_bias} — skipping all signals")
            return []
        else:
            log.debug(f"📅 Daily bias: {daily_bias} (4h: {htf_bias})")

    # ── MTF analiz ──
    mtf_sh, mtf_sl = engine.swings(df_mtf)
    mtf_brks = engine.structure(df_mtf, mtf_sh, mtf_sl)
    mtf_chochs = [b for b in mtf_brks if b.kind == "CHoCH"]

    # ── Entry TF analiz ──
    e_sh, e_sl = engine.swings(df_entry)
    e_brks = engine.structure(df_entry, e_sh, e_sl)
    e_trend = e_brks[-1].direction if e_brks else "UNDEF"
    e_obs = engine.order_blocks(df_entry, e_sh, e_sl, e_trend)
    e_sfps = engine.sfps(df_entry, e_sh, e_sl)
    e_range = engine.range_info(df_entry)
    e_ote = engine.ote(e_sh, e_sl, e_trend)
    a_obs = [o for o in e_obs if not o.mitigated]

    signals = []
    last_bar_idx = len(df_entry) - 1
    recent_cutoff = last_bar_idx - recency_bars
    
    # Diagnostics: reject reasons
    aligned_triggers = 0  # CHoCH or BOS aligned with HTF bias + within recency
    reject_confluence = 0
    reject_rr = 0
    reject_tp_wrong_side = 0
    max_seen_score = 0
    max_seen_rr = 0.0
    score_buckets: Dict[int, int] = {}

    for brk in e_brks:
        # CHoCH (reversal) + BOS (continuation) — both must align with HTF bias.
        if brk.kind not in ("CHoCH", "BOS") or brk.direction != htf_bias:
            continue
        if brk.idx < recent_cutoff:
            continue
        # BOS events fire far more often than CHoCH; tighten the recency
        # window so we don't enter on stale continuation breaks.
        if brk.kind == "BOS" and brk.idx < (last_bar_idx - recency_bars // 2):
            continue
        aligned_triggers += 1

        is_long = brk.direction == "BULL"
        price = brk.price

        # Koşul kontrolleri
        in_htf_fvg = any(
            f.direction == htf_bias and f.bot <= price <= f.top
            for f in htf_fvgs
        )
        in_ote = False
        if e_ote:
            lo, hi = min(e_ote.top, e_ote.bot), max(e_ote.top, e_ote.bot)
            in_ote = lo <= price <= hi

        mtf_conf = any(m.direction == htf_bias for m in mtf_chochs[-5:])

        has_sfp = any(
            s.direction == brk.direction and abs(s.idx - brk.idx) < 10
            for s in e_sfps
        )

        in_ob, ob_ns, ob_eq = False, False, False
        matched_ob = None
        for ob in a_obs:
            if ob.direction == brk.direction:
                # Efloud retest: price is inside the OB, or within 2% of its boundary
                is_near = (ob.bot <= price <= ob.top * 1.02) if is_long else (ob.bot * 0.98 <= price <= ob.top)
                if is_near:
                    in_ob = True
                    ob_ns = ob.near_swing
                    ob_eq = abs(price - ob.eq) / max(ob.eq, 1e-10) < 0.003
                    matched_ob = ob
                    break

        # ── Efloud Pullback/Retest Entry Refinement (Low-risk Entry Opportunity) ──
        # "Orderblock veya Equilibrium noktasına bir geri çekilme, düşük risk ile işleme giriş fırsatı arama."
        if in_ob and matched_ob:
            if is_long:
                price = min(matched_ob.top, price)
            else:
                price = max(matched_ob.bot, price)
        elif in_ote and e_ote:
            if is_long:
                price = min(e_ote.top, price)
            else:
                price = max(e_ote.bot, price)

        correct_zone = (is_long and e_range.discount) or (not is_long and e_range.premium)
        has_dev = (is_long and e_range.dev_bull) or (not is_long and e_range.dev_bear)

        # Confluence
        score, reasons = calc_confluence(
            is_long, htf_bias, in_htf_fvg, in_ote, mtf_conf,
            has_sfp, in_ob, ob_ns, ob_eq, correct_zone, has_dev
        )

        # Gemini AI Macro Sentiment confluence bonus/penalty
        if ai_sentiment and "macro_sentiment" in ai_sentiment:
            macro = ai_sentiment["macro_sentiment"]
            if macro == "RISK_ON":
                if is_long:
                    score = min(100, score + 5)
                    reasons.append("Gemini AI Macro Sentiment is RISK_ON (+5)")
                else:
                    score = max(0, score - 5)
                    reasons.append("Gemini AI Macro Sentiment is RISK_ON (-5)")
            elif macro == "RISK_OFF":
                if not is_long:
                    score = min(100, score + 5)
                    reasons.append("Gemini AI Macro Sentiment is RISK_OFF (+5)")
                else:
                    score = max(0, score - 5)
                    reasons.append("Gemini AI Macro Sentiment is RISK_OFF (-5)")

        # Daily filter bonus — 1d ile aynı yönde ise +5 confluence
        if daily_bias != "UNDEF":
            if daily_bias == htf_bias:
                score = min(100, score + 5)
                reasons.append(f"Daily aligned ({daily_bias})")
            elif daily_bias != htf_bias:
                # Soft penalty: daily ters yönde, -5 puan
                score = max(0, score - 5)
                reasons.append(f"Daily diverging ({daily_bias} vs {htf_bias})")

        # ── Efloud Level-based Confluence Enhancements (User Price Action Notes) ──
        if levels:
            major_level_names = {"MO", "PMO", "WO", "PWO", "DO", "PDO", "MondayH", "MondayL"}
            for lvl in levels:
                # 1. Price near a Major Opening or Monday H/L level
                if lvl.name in major_level_names:
                    if abs(price - lvl.price) / lvl.price <= 0.003: # Within 0.3%
                        score = min(100, score + 5)
                        reasons.append(f"Price near major level {lvl.name} ({lvl.price:.2f})")
                
                # 2. Price in Stacked S/R Zone (3+ levels cluster)
                if lvl.strength >= 3:
                    if abs(price - lvl.price) / lvl.price <= 0.005: # Within 0.5%
                        score = min(100, score + 8)
                        reasons.append(f"Price in Stacked Zone level {lvl.name} ({lvl.price:.2f})")

        if score > max_seen_score:
            max_seen_score = score
        bucket = (score // 5) * 5
        score_buckets[bucket] = score_buckets.get(bucket, 0) + 1

        effective_threshold = resolve_min_confluence(
            symbol=symbol,
            global_min=min_confluence,
            symbol_overrides=symbol_confluence_overrides,
        )
        if score < effective_threshold:
            reject_confluence += 1
            continue

        # SL / TP
        # SL / TP
        # Spec §5.1 / User request: local structure invalidation Stop Loss.
        # Find the local minimum/maximum of the last 20 candles before the breakout
        # to ensure the SL is tight and professional (matches the red invalidation point),
        # instead of using very old swing highs/lows from before brk.idx which ruins R:R.
        # Plus a buffer of 0.5 * ATR(14) on the entry timeframe.
        
        # Simple true range ATR(14) calculation
        h_vals = df_entry["high"].values
        l_vals = df_entry["low"].values
        c_vals = df_entry["close"].values
        tr = [
            max(h_vals[i] - l_vals[i], abs(h_vals[i] - c_vals[i-1]), abs(l_vals[i] - c_vals[i-1])) 
            for i in range(1, len(df_entry))
        ]
        atr14 = float(pd.Series(tr).rolling(14).mean().iloc[-1]) if len(tr) >= 14 else (price * 0.005)
        
        # ── Dynamic ATR Invalidation Buffer (Volatility Alignment) ──
        # "Hiçbir konsept kesin doğrudur diye düşünülmemeli yanılma payı unutulmamalı, buna göre stop koyulmalıdır."
        buffer_mult = 0.5
        if len(df_entry) >= 14:
            high_low_spread = (df_entry["high"] - df_entry["low"]).rolling(14).mean().iloc[-1]
            close_spread = abs(df_entry["close"] - df_entry["close"].shift(14)).iloc[-1]
            if close_spread > 1.2 * high_low_spread:
                buffer_mult = 0.75  # Trend-aligned volatility buffer to prevent deviasyon sweeps
        buffer = buffer_mult * atr14

        if is_long:
            htf_above_targets = []
            sl_c = [s for s in e_sl if s.idx < brk.idx]
            local_lo = float(df_entry["low"].iloc[max(0, brk.idx - 20):brk.idx].min()) - buffer
            sl = sl_c[-1].price if sl_c else local_lo
            if sl < local_lo:
                sl = local_lo
            
            # Range deviation tight SL override
            if has_dev and e_range:
                sl = min(sl, e_range.lo - buffer)

            # Safety clamp: at least 0.1% below entry price
            sl = min(sl, price * 0.999)
            
            risk_tmp = abs(price - sl)
            min_tp_long = price + risk_tmp * min_rr
            
            # Prioritize Liquidity over Imbalance in ranging markets
            liquidity_targets = [s.price for s in htf["swing_highs"] if s.price >= min_tp_long]
            if "eq_highs" in htf:
                liquidity_targets += [eq["price"] for eq in htf["eq_highs"] if eq["price"] >= min_tp_long]
                
            if has_dev and e_range:
                # Efloud Range deviation play: target EQ for TP1, RH for TP2
                tp1 = e_range.eq
                if tp1 < min_tp_long:
                    tp1 = min_tp_long
            elif (htf_bias_original == "UNDEF") and liquidity_targets:
                # Ranging market: target liquidity pools
                tp1 = min(liquidity_targets)
            else:
                # Trending market: target FVG or liquidity pools
                htf_above_targets = [f.top for f in htf_fvgs
                                       if f.direction == "BULL" and f.top >= min_tp_long]
                htf_above_targets += liquidity_targets
                if htf_above_targets:
                    tp1 = min(htf_above_targets)
                else:
                    # ── Fibonacci price discovery targets (empty structures) ──
                    # "fiyat oluşmamış bir alanda hedef belirlemek için kullanılabilir. 1.272"
                    tp1 = price + risk_tmp * 1.272
        else:
            htf_below_targets = []
            sl_c = [s for s in e_sh if s.idx < brk.idx]
            local_hi = float(df_entry["high"].iloc[max(0, brk.idx - 20):brk.idx].max()) + buffer
            sl = sl_c[-1].price if sl_c else local_hi
            if sl > local_hi:
                sl = local_hi
            
            # Range deviation tight SL override
            if has_dev and e_range:
                sl = max(sl, e_range.hi + buffer)

            # Safety clamp: at least 0.1% above entry price
            sl = max(sl, price * 1.001)
            
            risk_tmp = abs(price - sl)
            min_tp_short = price - risk_tmp * min_rr
            
            # Prioritize Liquidity over Imbalance in ranging markets
            liquidity_targets = [s.price for s in htf["swing_lows"] if s.price <= min_tp_short]
            if "eq_lows" in htf:
                liquidity_targets += [eq["price"] for eq in htf["eq_lows"] if eq["price"] <= min_tp_short]
                
            if has_dev and e_range:
                # Efloud Range deviation play: target EQ for TP1, RL for TP2
                tp1 = e_range.eq
                if tp1 > min_tp_short:
                    tp1 = min_tp_short
            elif (htf_bias_original == "UNDEF") and liquidity_targets:
                # Ranging market: target liquidity pools
                tp1 = max(liquidity_targets)
            else:
                # Trending market: target FVG or liquidity pools
                htf_below_targets = [f.bot for f in htf_fvgs
                                       if f.direction == "BEAR" and f.bot <= min_tp_short]
                htf_below_targets += liquidity_targets
                if htf_below_targets:
                    tp1 = max(htf_below_targets)
                else:
                    # ── Fibonacci price discovery targets (empty structures) ──
                    # "fiyat oluşmamış bir alanda hedef belirlemek için kullanılabilir. 1.272"
                    tp1 = price - risk_tmp * 1.272

        risk = abs(price - sl)
        if risk == 0:
            continue
            
        # Target opposite range extreme for deviation play, else fib extension
        if has_dev and e_range:
            raw_tp2 = e_range.hi if is_long else e_range.lo
            tp2 = _resolve_deviation_tp2(
                raw_tp2, tp1,
                min_tp_long if is_long else min_tp_short,
                price, risk, is_long,
            )
        else:
            # If tp1 is our 1.272 Fibo target, tp2 targets 2.618 (or fib_ext if configured)
            is_discovery = False
            if is_long:
                if not htf_above_targets:
                    is_discovery = True
            else:
                if not htf_below_targets:
                    is_discovery = True
                    
            if not has_dev and is_discovery:
                tp2 = (price + risk * 2.618) if is_long else (price - risk * 2.618)
            else:
                tp2 = (price + risk * fib_ext) if is_long else (price - risk * fib_ext)
        # Target-inversion koruması (Y5): TP2 daima TP1'den uzakta olmalı.
        tp2 = _enforce_tp2_beyond_tp1(tp2, tp1, price, risk, is_long)

        rr1 = round(abs(tp1 - price) / risk, 2)
        rr2 = round(abs(tp2 - price) / risk, 2)

        # TP1 fiyatın yanlış tarafında olmamalı
        if is_long and tp1 <= price:
            reject_tp_wrong_side += 1
            continue
        if not is_long and tp1 >= price:
            reject_tp_wrong_side += 1
            continue

        if rr1 > max_seen_rr:
            max_seen_rr = rr1

        if rr1 < min_rr:
            reject_rr += 1
            continue

        sig = Signal(
            direction="LONG" if is_long else "SHORT",
            entry=round(price, 8), sl=round(sl, 8),
            tp1=round(tp1, 8), tp2=round(tp2, 8),
            rr1=rr1, rr2=rr2, confluence=score,
            reasons=reasons, timestamp=brk.ts,
            in_ote=in_ote, in_ob=in_ob, has_sfp=has_sfp,
            zone="DISCOUNT" if e_range.discount else "PREMIUM"
        )
        
        # SMC Structure Validation Layer (Phase 2.2)
        if symbol:
            val_res = validate_signal_with_gemini(
                symbol=symbol,
                direction=sig.direction,
                entry=sig.entry,
                sl=sig.sl,
                tp=sig.tp1,
                df_htf=df_htf,
                df_mtf=df_mtf,
                df_entry=df_entry
            )
            
            confidence = val_res.get("confidence", 1.0)
            is_valid = val_res.get("valid", True)
            reasoning = val_res.get("reasoning", "")
            
            log.info(f"SMC Structure Validation [{symbol}]: valid={is_valid}, confidence={confidence:.2f}, reasoning='{reasoning}'")

            # C8: advisory ONLY — annotate the signal, NEVER drop it. An external
            # LLM must not be a hard trade gate inside signal generation (the
            # agents layer is advisory; any gating lives in safe_orchestrator
            # behind agent_team.gating=false). A low-confidence/invalid verdict is
            # recorded for journal/dashboard, not used to suppress the trade.
            if isinstance(sig.meta, dict):
                sig.meta["gemini_structure_validation"] = {
                    "valid": bool(is_valid),
                    "confidence": float(confidence),
                    "reasoning": reasoning,
                    "advisory_only": True,
                }
            if not is_valid or confidence < 0.70:
                log.info(
                    f"⚠️ Gemini structure validation flagged {sig.direction} @ {sig.entry} "
                    f"(confidence={confidence:.2f}) — ADVISORY, signal NOT dropped"
                )

        signals.append(sig)
        log.info(f"Signal: {sig.direction} @ {sig.entry} | Conf={sig.confluence} | R:R={sig.rr1}/{sig.rr2}")

    # Diagnostic: reject reason breakdown
    if aligned_triggers > 0 and len(signals) == 0:
        effective_threshold = resolve_min_confluence(
            symbol=symbol,
            global_min=min_confluence,
            symbol_overrides=symbol_confluence_overrides,
        )
        prefix = f"[{symbol}] " if symbol else ""
        reasons = []
        if reject_confluence > 0:
            hist = _format_score_histogram(score_buckets)
            hist_part = f", hist: {hist}" if hist else ""
            reasons.append(
                f"conf<{effective_threshold} ({reject_confluence}×, max={max_seen_score}{hist_part})"
            )
        if reject_tp_wrong_side > 0:
            reasons.append(f"TP wrong side ({reject_tp_wrong_side}×)")
        if reject_rr > 0:
            reasons.append(f"R:R<{min_rr} ({reject_rr}×, max seen: {max_seen_rr:.2f})")
        log.info(f"📉 {prefix}{aligned_triggers} triggers, 0 signals. Rejects: {' | '.join(reasons)}")

    return signals
