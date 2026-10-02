"""Trigger phase for SMC v2: CHoCH/BOS detection → SetupCandidate emission.

Per spec §4.3 step 3:
  For each new CHoCH or BOS on LTF (15m) aligned with HTF (4h) bias:
    1. select_htf_swing_anchor → structural SL reference
    2. build_pullback_zones → target zone (HTF FVG priority, OTE fallback)
    3. Emit SetupCandidate(state=AWAITING_PULLBACK, bars_waited=0)

Pure function. Returns list of new candidates. Caller (orchestrator) appends
to SetupStateStore — store.add() enforces per-symbol cap.

OPERATOR (2026-10-02): BOS (continuation) breaks are now ALSO emitted, not
just CHoCH (reversal). Previously BOS was deferred to v1 signals.py, but v1
is muted while v2 owns the symbol — so BOS setups never entered at all and
big-pump continuations were missed. Both kinds now wait for the pullback
into the OB/BB block and enter from the retest, SL at the liquidity line.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

from engine.smc import StructBreak, FVG, OrderBlock, SFP
from engine.smc_v2.setup_state import SetupCandidate
from engine.smc_v2.swing_anchor import select_htf_swing_anchor
from engine.smc_v2.zones import build_pullback_zones, build_ob_bb_zone


def _bar_ts_to_ms(ts: str) -> int:
    """Convert a StructBreak's bar timestamp string to ms-epoch.

    C6: ``SetupCandidate.trigger_bar_ts`` feeds ``confirm_entry``'s ``since_ts``,
    which is compared against ``df_15m`` bar timestamps in ms-epoch. The trigger
    bar's ms must be captured at creation time (stable across later windowing) —
    storing the bar ordinal made the "only AFTER the trigger" guard dead code
    (ordinal << ms always → never skipped). ``brk.ts`` is the bar's index string
    (real ISO in production); round-tripping it via ``pd.Timestamp`` yields the
    same ms ``confirm_entry`` computes. Returns 0 on an unparseable/empty ts
    (degenerate; confirm_entry then simply does not skip).
    """
    try:
        return int(pd.Timestamp(ts).timestamp() * 1000)
    except (ValueError, TypeError):
        return 0


@dataclass
class HtfBar:
    """Bar shape for select_htf_swing_anchor consumption.

    Orchestrator wraps each HTF DataFrame row in this; tests use it directly.
    `.ordinal` is an int bar position (NOT timestamp). See spec §10 #1 contract.

    W2/C1 (2026-07-18): opsiyonel `ts_ms` (bar açılış zamanı, ms-epoch) —
    LTF kırılım zamanının HTF ordinal eksenine haritalanması için
    (`anchor_time_axis` toggle'ı). None → haritalama yapılamaz, legacy yol.
    """
    ordinal: int
    high: float
    low: float
    ts_ms: Optional[int] = None


def _htf_cutoff_for_break(brk_ms: int, htf_bars: list) -> Optional[int]:
    """W2/C1 (2026-07-18): LTF kırılım anını (ms) HTF ordinal cutoff'una haritala.

    select_htf_swing_anchor `swing.idx < trigger_idx` (HTF ekseni) filtreler;
    triggers eskiden buraya brk.idx'i (LTF ordinali!) geçiriyordu — LTF
    ordinalleri aynı duvar-saati için kat kat büyük olduğundan filtre fiilen
    herkesi geçiriyordu: tetikten SONRA oluşan HTF swing'i de SL çapası
    olabiliyordu (lookahead; "don't anchor SL on future structure" ihlali).

    Dönüş: kırılımı kapsayan ya da öncesindeki SON HTF barın ordinali —
    exclusive filtre kapsayan barın swing'ini de eler (intra-bar oluşum sırası
    bilinemez → muhafazakâr dışlama). Kırılım tüm pencereden önceyse 0
    (hiçbir swing bilinmiyor → çapa None → aday atlanır). Haritalanamazsa
    (brk_ms<=0 ya da herhangi bir barda ts_ms yok) None döner → çağıran
    legacy brk.idx yoluna düşer (ts'siz eski fikstürler kırılmaz)."""
    if brk_ms <= 0 or not htf_bars:
        return None
    if any(getattr(b, "ts_ms", None) is None for b in htf_bars):
        return None
    eligible = [b.ordinal for b in htf_bars if b.ts_ms <= brk_ms]
    if not eligible:
        return 0
    return max(eligible)


def _find_causing_ob(
    ltf_order_blocks: List[OrderBlock],
    brk: StructBreak,
) -> Optional[OrderBlock]:
    """Find the OrderBlock / BreakerBlock that launched the structure break.

    Price action doctrine: a CHoCH/BOS break is the impulsive move that starts
    from the last opposite-direction block. For a BULL break (price broke
    above the last swing high) the launch block is the most recent BEAR OB
    formed before the break, sitting below the break price. For a BEAR break
    it is the most recent BULL OB above the break. A mitigated OB is a
    Breaker Block — still the retest zone, flagged via became_breaker.

    Returns None when no block qualifies (caller falls back to the
    FVG/OTE pullback path).
    """
    if not ltf_order_blocks:
        return None
    candidates = [
        ob for ob in ltf_order_blocks
        if ob.idx < brk.idx
        and (
            (brk.direction == "BULL" and ob.direction == "BEAR" and ob.top < brk.price)
            or (brk.direction == "BEAR" and ob.direction == "BULL" and ob.bot > brk.price)
        )
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda ob: ob.idx)


def _sfp_confluence(ltf_sfps, brk) -> tuple:
    """SFP confluence bonusu (0/10) + reason. Efloud notları: "Old low/high
    likidite temizliği olursa SFP aranmalı ve tekrar pozisyon inşasında
    bulunulmalıdır". SFP yönü CHoCH yönüyle aynı ve kırılımdan önce olmalı."""
    if not ltf_sfps:
        return 0, None
    for sfp in ltf_sfps:
        if sfp.idx < brk.idx and sfp.direction == brk.direction:
            return 10, f"SFP aligned (sweep {sfp.sweep_level} → {sfp.price})"
    return 0, None


def _rsi_confluence(rsi_value, direction) -> tuple:
    """RSI confluence bonusu (0/5) + reason. Efloud notları: "RSI oversold
    veya overbolda yakınsa OTE çalışabilir". LONG: RSI<=40, SHORT: RSI>=60."""
    if rsi_value is None:
        return 0, None
    if direction == "LONG" and rsi_value <= 40:
        return 5, f"RSI {rsi_value:.1f} oversold-near (LONG)"
    if direction == "SHORT" and rsi_value >= 60:
        return 5, f"RSI {rsi_value:.1f} overbought-near (SHORT)"
    return 0, None


def generate_setup_candidates(
    symbol: str,
    htf_bias: str,
    ltf_structure_breaks: List[StructBreak],
    htf_swings: dict,
    htf_bars: list,
    htf_fvgs: List[FVG],
    ote_band: Tuple[float, float],
    ltf_trigger_idx_min: int,
    anchor_time_axis: bool = False,
    ltf_order_blocks: Optional[List[OrderBlock]] = None,
    df_entry: Optional[pd.DataFrame] = None,
    ltf_sfps: Optional[List[SFP]] = None,
    eq_price: Optional[float] = None,
    rsi_value: Optional[float] = None,
) -> List[SetupCandidate]:
    """Emit SetupCandidate instances for new aligned CHoCH/BOS events.

    Args:
        symbol: trading pair
        htf_bias: "BULL" | "BEAR" | "UNDEF" — HTF directional bias
        ltf_structure_breaks: LTF (15m) structure breaks (CHoCH/BOS) from
            SMCEngine.structure() on df_15m
        htf_swings: {"swing_highs": [...], "swing_lows": [...]} for SL anchor
        htf_bars: HTF OHLC bars with .ordinal/.high/.low (for swing_anchor
            unbroken check). Caller enumerates df_htf to produce these.
        htf_fvgs: unmitigated HTF FVGs for build_pullback_zones priority
        ote_band: (low, high) of HTF OTE 0.618-0.786 fib region (fallback zone)
        ltf_trigger_idx_min: int — only consider breaks with idx >= this
            (recency filter; mirrors v1 signals.py:198 recency_cutoff)
        anchor_time_axis: W2/C1 (2026-07-18, default False). True iken SL
            çapası seçiminde LTF kırılım ZAMANI HTF ordinal eksenine
            haritalanır (_htf_cutoff_for_break) — tetik sonrası HTF swing'i
            (lookahead) elenmiş olur. False → legacy brk.idx (eksen hatası)
            birebir korunur; NET-cost gate Windows'ta koşulup operatör
            config'te (`smc_v2.anchor_time_axis: true`) açana kadar canlı
            davranış değişmez. Haritalama yapılamazsa (ts'siz bar fikstürü)
            toggle ON olsa da legacy'ye düşülür.
        ltf_order_blocks: LTF (15m) OrderBlock listesi (SMCEngine.order_blocks).
            Verilirse CHoCH kırılımını yapan OB/BB hedef zone olur (FVG/OTE
            yerine) ve SL çapası bloğun bir önceki mumu (origin) olur.
            None → legacy FVG/OTE yolu.
        df_entry: LTF DataFrame — OB origin mumunun low/high'ını okumak için.
            ltf_order_blocks verilirken zorunlu; yoksa OB/BB yolu atlanır.
        ltf_sfps: LTF (15m) SFP listesi (SMCEngine.sfps). Verilirse CHoCH
            kırılımı bir SFP (swing failure pattern — likidite temizliği
            sonrası başarısız kırılım) ile hizalanınca confluence bonusu
            eklenir (Efloud notları: "Old low/high likidite temizliği olursa
            SFP aranmalı ve tekrar pozisyon inşasında bulunulmalıdır").
        eq_price: range EQ (midpoint) — deviasyon sonrası EQ retest zone'u
            için (Efloud notları: "Deviasyon sonrası range içine giren fiyat
            öncesinde EQ'yu test etmeye meraklıdır. retestle girilebilir").
        rsi_value: LTF RSI(14) — OTE yakınsama confluence'ı için (Efloud
            notları: "RSI oversold veya overbolda yakınsa OTE çalışabilir").

    Returns:
        List of new SetupCandidate instances (state=AWAITING_PULLBACK,
        bars_waited=0). Caller must add each to SetupStateStore.add()
        which applies per-symbol cap.
    """
    if htf_bias == "UNDEF":
        return []

    out: List[SetupCandidate] = []
    for brk in ltf_structure_breaks:
        # OPERATOR (2026-10-02): BOTH CHoCH (reversal) and BOS (continuation)
        # breaks emit setups. v1 signals.py is muted while v2 owns the symbol,
        # so deferring BOS to v1 meant BOS setups never entered — big-pump
        # continuations were missed. The HTF-bias alignment filter below keeps
        # BOS trend-aligned by construction (BOS is already in trend direction).

        # Aligned with HTF bias only
        if brk.direction != htf_bias:
            continue

        # Recency filter
        if brk.idx < ltf_trigger_idx_min:
            continue

        # Map BULL → LONG, BEAR → SHORT
        direction = "LONG" if brk.direction == "BULL" else "SHORT"

        # ── OB/BB entry path (price action doctrine) ──
        # CHoCH kırılımını yapan OrderBlock/BreakerBlock varsa hedef zone o
        # bloktur; SL çapası bloğun BİR ÖNCEKİ mumudur (origin mum). Böylece
        # işleme CHoCH çizgisinden değil, kırılımı başlatan bloktan girilir
        # ve stop, bloğun altındaki/üstündeki origin mumuna dayanır.
        causing_ob = _find_causing_ob(ltf_order_blocks, brk) if ltf_order_blocks else None
        if causing_ob is not None and df_entry is not None and causing_ob.idx - 1 >= 0:
            zone = build_ob_bb_zone(causing_ob)
            origin = df_entry.iloc[causing_ob.idx - 1]
            # LONG: SL origin mumun LOW'unun altına; SHORT: HIGH'inin üstüne.
            # calc_sl min(zone.low, anchor) / max(zone.high, anchor) yaptığı
            # için anchor'ı origin mumun uç fiyatı olarak vermek yeterli.
            anchor = float(origin["low"]) if direction == "LONG" else float(origin["high"])
            # SFP + RSI confluence (Efloud notları) — OB/BB yolunda da geçerli.
            sfp_bonus, sfp_reason = _sfp_confluence(ltf_sfps, brk)
            rsi_bonus, rsi_reason = _rsi_confluence(rsi_value, direction)
            out.append(SetupCandidate(
                symbol=symbol,
                direction=direction,
                trigger_bar_ts=_bar_ts_to_ms(brk.ts),
                trigger_price=brk.price,
                htf_bias=htf_bias,
                target_zone=zone,
                htf_swing_anchor=anchor,
                bars_waited=0,
                state="AWAITING_PULLBACK",
                confluence_score=sfp_bonus + rsi_bonus,
                reasons=[f"CHoCH {brk.direction} aligned with HTF {htf_bias}",
                         f"entry from {zone.source} retest (origin candle {causing_ob.idx - 1})"]
                + ([sfp_reason] if sfp_reason else [])
                + ([rsi_reason] if rsi_reason else []),
            ))
            continue

        # Select structural SL anchor (most-recent-unbroken HTF swing).
        # W2/C1: trigger_idx HTF ordinal ekseninde olmalı; legacy brk.idx
        # LTF ordinaliydi (lookahead açığı). Toggle ON + haritalanabilir →
        # zaman-eksenli cutoff; aksi halde birebir eski davranış.
        trigger_cutoff = brk.idx
        if anchor_time_axis:
            mapped = _htf_cutoff_for_break(_bar_ts_to_ms(brk.ts), htf_bars)
            if mapped is not None:
                trigger_cutoff = mapped
        anchor = select_htf_swing_anchor(
            htf_swings=htf_swings,
            direction=direction,
            trigger_idx=trigger_cutoff,
            htf_bars=htf_bars,
        )
        if anchor is None:
            # No valid HTF anchor → can't compute structural SL → skip
            continue

        # Build pullback zone (HTF FVG priority, EQ retest, OTE fallback)
        zone = build_pullback_zones(
            htf_fvgs=htf_fvgs,
            ote_band=ote_band,
            direction=direction,
            trigger_price=brk.price,
            eq_price=eq_price,
        )

        # Skip degenerate OTE fallback (e.g. ote_band=(0,0) when HTF analyze()
        # has no OTE level). Such a zone has zero width, is_price_in_zone
        # would never trigger, and the candidate would just sit in
        # AWAITING_PULLBACK eating cap slots until timeout. Better to drop.
        if zone.source == "OTE" and zone.low == zone.high:
            continue

        # SFP confluence (Efloud notları): CHoCH bir SFP ile hizalanırsa
        # (likidite temizliği sonrası başarısız kırılım → pozisyon inşası)
        # confluence bonusu eklenir. SFP yönü CHoCH yönüyle aynı olmalı ve
        # kırılımdan önce oluşmuş olmalı (lookahead yok).
        sfp_bonus, sfp_reason = _sfp_confluence(ltf_sfps, brk)

        # RSI confluence (Efloud notları): RSI oversold/overbought'a yakınsa
        # OTE çalışabilir. LONG için RSI <= 40 (oversold yakını), SHORT için
        # RSI >= 60 (overbought yakını) → +5 bonus.
        rsi_bonus, rsi_reason = _rsi_confluence(rsi_value, direction)

        out.append(SetupCandidate(
            symbol=symbol,
            direction=direction,
            # C6: store the CHoCH bar's ms-epoch (confirm_entry.since_ts axis),
            # NOT the ordinal. swing_anchor gets brk.idx directly above (line ~92),
            # so it is unaffected by this.
            trigger_bar_ts=_bar_ts_to_ms(brk.ts),
            trigger_price=brk.price,
            htf_bias=htf_bias,
            target_zone=zone,
            htf_swing_anchor=anchor,
            bars_waited=0,
            state="AWAITING_PULLBACK",
            confluence_score=sfp_bonus + rsi_bonus,
            reasons=[f"CHoCH {brk.direction} aligned with HTF {htf_bias}"]
            + ([sfp_reason] if sfp_reason else [])
            + ([rsi_reason] if rsi_reason else []),
        ))

    return out
