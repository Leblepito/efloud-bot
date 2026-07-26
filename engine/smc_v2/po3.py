"""Po3 (Power of Three) faz tespiti + manipulation gate — MPA/1.

Kaynak: Efloud (@EfloudTheSurfer) kanal transkript analizi (2026-07-26,
25 video). Po3 ICT kökenli; Wyckoff accumulation / manipulation (spring) /
distribution şemasıyla eşdeğer kabul ediliyor:

  ACCUMULATION  — yatay birikim penceresi (seans/gün/hafta açılışı),
                  düşük volatilite, destek-direnç burada şekillenir.
  MANIPULATION  — birikim aralığının ekstremumu süpürülür (stop avı,
                  sahte kırılım) ama henüz yön teyidi (displacement)
                  YOKTUR.
  DISTRIBUTION  — süpürme SONRASI displacement geldi; asıl trend hareketi.

SERT KURAL (kaynakta defalarca tekrarlanıyor): manipulation fazında işlem
AÇILMAZ. Bu bir HARD GATE'tir — confluence puanı ne olursa olsun girişi
bloklar. Gate setup'ı ÖLDÜRMEZ, GECİKTİRİR: displacement gelince faz
DISTRIBUTION'a döner ve kapı açılır.

Saf fonksiyon — I/O yok, log yok. Çağıran (orchestrator) toggle'ı kontrol
eder; `smc_v2.po3_gate: false` varsayılanıyla bu modül hiç çağrılmaz,
dolayısıyla V1/V2/V3 canlı botlarının davranışı birebir korunur.

UNDEFINED faz BLOKLAMAZ (bilinçli karar): yetersiz veri "manipülasyon var"
demek değildir. Bloklasaydı toggle açıldığı anda veri penceresi kısa olan
her sembolde sinyal sessizce sıfırlanırdı. Bkz. `po3_blocks_entry`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

PHASE_ACCUMULATION = "ACCUMULATION"
PHASE_MANIPULATION = "MANIPULATION"
PHASE_DISTRIBUTION = "DISTRIBUTION"
PHASE_UNDEFINED = "UNDEFINED"


@dataclass
class Po3State:
    """Bir Po3 penceresinin (varsayılan: günlük) anlık durumu."""

    phase: str
    acc_high: Optional[float] = None
    acc_low: Optional[float] = None
    swept_side: Optional[str] = None   # "UP" | "DOWN" | None
    sweep_idx: Optional[int] = None
    confirm_idx: Optional[int] = None  # distribution'ı doğrulayan displacement barı
    reason: str = ""


def _body_ref(df: pd.DataFrame, ref_len: int) -> pd.Series:
    """BODY_REF = SMA(high-low, ref_len). engine/smc.py OB filtresiyle aynı taban."""
    return (df["high"] - df["low"]).rolling(ref_len, min_periods=1).mean()


def classify_po3_phase(
    df: pd.DataFrame,
    acc_start_hour: int = 0,
    acc_end_hour: int = 8,
    disp_mult: float = 1.5,
    body_ref_len: int = 20,
    min_acc_bars: int = 2,
) -> Po3State:
    """Son bara ait Po3 fazını sınıflandır.

    Args:
        df: DatetimeIndex (UTC) + [open, high, low, close] sütunlu intraday
            DataFrame. Accumulation penceresi bu index'in saatlerinden okunur,
            dolayısıyla index tz-aware UTC veya naive-UTC olmalıdır.
        acc_start_hour / acc_end_hour: birikim penceresi [start, end) — UTC saat.
            Varsayılan 00:00-08:00, günlük mumun ilk 1/3'ü (kripto 24s seans
            varsayımı). Kaynak bu saatleri vermiyor; pencere seçimi çıkarımdır
            ve backtest'te taranmalıdır.
        disp_mult: displacement eşiği; |close-open| >= disp_mult * BODY_REF.
        body_ref_len: BODY_REF periyodu.
        min_acc_bars: birikim aralığını geçerli saymak için gereken min bar.

    Returns:
        Po3State. Veri yetersizse phase=UNDEFINED (bloklamaz).
    """
    if df is None or len(df) == 0 or not isinstance(df.index, pd.DatetimeIndex):
        return Po3State(phase=PHASE_UNDEFINED, reason="empty or non-datetime index")

    hours = df.index.hour
    dates = df.index.normalize()
    session = dates[-1]

    in_session = dates == session
    in_acc = in_session & (hours >= acc_start_hour) & (hours < acc_end_hour)

    acc = df[in_acc]
    if len(acc) < min_acc_bars:
        return Po3State(
            phase=PHASE_UNDEFINED,
            reason=f"accumulation bars {len(acc)} < {min_acc_bars}",
        )

    acc_high = float(acc["high"].max())
    acc_low = float(acc["low"].min())

    # Pencere sonrası barların ORDİNALLERİ. Ordinal eksen df'in kendi konum
    # indeksidir (swing_anchor.py ile aynı sözleşme: ms-epoch DEĞİL, 0..N-1
    # bar konumu). Konumu maskeden türetiyoruz — `index.get_loc` yinelenen
    # timestamp'te slice döndürüp sessizce yanlış sonuç üretebilirdi.
    post_mask = in_session & (hours >= acc_end_hour)
    post_positions = [i for i, flag in enumerate(post_mask) if flag]
    if not post_positions:
        return Po3State(
            phase=PHASE_ACCUMULATION,
            acc_high=acc_high,
            acc_low=acc_low,
            reason="still inside accumulation window",
        )

    highs = df["high"].values
    lows = df["low"].values
    sweep_idx: Optional[int] = None
    swept_side: Optional[str] = None
    for pos in post_positions:
        if highs[pos] > acc_high:
            sweep_idx, swept_side = pos, "UP"
            break
        if lows[pos] < acc_low:
            sweep_idx, swept_side = pos, "DOWN"
            break

    if sweep_idx is None:
        return Po3State(
            phase=PHASE_ACCUMULATION,
            acc_high=acc_high,
            acc_low=acc_low,
            reason="range holding, no sweep yet",
        )

    # Süpürme sonrası displacement var mı? Varsa manipülasyon bitti, dağıtım başladı.
    ref = _body_ref(df, body_ref_len)
    body = (df["close"] - df["open"]).abs()
    confirm_idx: Optional[int] = None
    for pos in range(sweep_idx + 1, len(df)):
        if body.iloc[pos] >= disp_mult * ref.iloc[pos]:
            confirm_idx = pos
            break

    if confirm_idx is None:
        return Po3State(
            phase=PHASE_MANIPULATION,
            acc_high=acc_high,
            acc_low=acc_low,
            swept_side=swept_side,
            sweep_idx=sweep_idx,
            reason=f"{swept_side} sweep at bar {sweep_idx}, no displacement yet",
        )

    return Po3State(
        phase=PHASE_DISTRIBUTION,
        acc_high=acc_high,
        acc_low=acc_low,
        swept_side=swept_side,
        sweep_idx=sweep_idx,
        confirm_idx=confirm_idx,
        reason=f"displacement at bar {confirm_idx} after {swept_side} sweep",
    )


def po3_blocks_entry(state: Po3State) -> bool:
    """HARD GATE (G1): manipulation fazında giriş bloklanır.

    UNDEFINED bloklamaz — modül docstring'indeki gerekçeye bakın.
    """
    return state.phase == PHASE_MANIPULATION


def po3_expected_direction(state: Po3State) -> Optional[str]:
    """Süpürme yönünden beklenen dağıtım yönü.

    Klasik Po3: manipülasyon sahte yöndür; asıl hareket TERSİ yöne gider.
    Dipler süpürüldüyse (DOWN) beklenen yön LONG, tepeler süpürüldüyse SHORT.
    Süpürme yoksa None.
    """
    if state.swept_side == "DOWN":
        return "LONG"
    if state.swept_side == "UP":
        return "SHORT"
    return None


def po3_score(state: Po3State, direction: str) -> int:
    """Confluence katkısı (0-10). Tasarım §2.3 C5.

    DISTRIBUTION + yön uyumlu → 10; ACCUMULATION → 3; diğer → 0.
    MANIPULATION zaten `po3_blocks_entry` ile elendiği için 0 döner.
    """
    if state.phase == PHASE_DISTRIBUTION:
        expected = po3_expected_direction(state)
        return 10 if expected == direction else 0
    if state.phase == PHASE_ACCUMULATION:
        return 3
    return 0
