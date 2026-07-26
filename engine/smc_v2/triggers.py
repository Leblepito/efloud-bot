"""Trigger phase for SMC v2: CHoCH detection → SetupCandidate emission.

Per spec §4.3 step 3:
  For each new CHoCH on LTF (15m) aligned with HTF (4h) bias:
    1. select_htf_swing_anchor → structural SL reference
    2. build_pullback_zones → target zone (HTF FVG priority, OTE fallback)
    3. Emit SetupCandidate(state=AWAITING_PULLBACK, bars_waited=0)

Pure function. Returns list of new candidates. Caller (orchestrator) appends
to SetupStateStore — store.add() enforces per-symbol cap.

Scope limited to CHoCH events (BOS deferred — matches v1 signals.py
recency-tighter BOS handling, see signals.py:200-204).
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

from engine.smc import StructBreak, Swing, FVG
from engine.smc_v2.setup_state import SetupCandidate
from engine.smc_v2.swing_anchor import select_htf_swing_anchor
from engine.smc_v2.zones import build_pullback_zones


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
) -> List[SetupCandidate]:
    """Emit SetupCandidate instances for new aligned CHoCH events.

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

    Returns:
        List of new SetupCandidate instances (state=AWAITING_PULLBACK,
        bars_waited=0). Caller must add each to SetupStateStore.add()
        which applies per-symbol cap.
    """
    if htf_bias == "UNDEF":
        return []

    out: List[SetupCandidate] = []
    for brk in ltf_structure_breaks:
        # PR #S3c-1 emits only for CHoCH (reversal). BOS (continuation)
        # deferred — v1 signals.py handles BOS with a tighter recency
        # window (signals.py:200-204).
        if brk.kind != "CHoCH":
            continue

        # Aligned with HTF bias only
        if brk.direction != htf_bias:
            continue

        # Recency filter
        if brk.idx < ltf_trigger_idx_min:
            continue

        # Map BULL → LONG, BEAR → SHORT
        direction = "LONG" if brk.direction == "BULL" else "SHORT"

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

        # Build pullback zone (HTF FVG priority, OTE fallback)
        zone = build_pullback_zones(
            htf_fvgs=htf_fvgs,
            ote_band=ote_band,
            direction=direction,
            trigger_price=brk.price,
        )

        # Skip degenerate OTE fallback (e.g. ote_band=(0,0) when HTF analyze()
        # has no OTE level). Such a zone has zero width, is_price_in_zone
        # would never trigger, and the candidate would just sit in
        # AWAITING_PULLBACK eating cap slots until timeout. Better to drop.
        if zone.source == "OTE" and zone.low == zone.high:
            continue

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
            confluence_score=0,  # PR #S3c-2 may add confluence scoring
            reasons=[f"CHoCH {brk.direction} aligned with HTF {htf_bias}"],
        ))

    return out
