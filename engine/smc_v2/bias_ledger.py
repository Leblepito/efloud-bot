"""BCEL — Bias Change Evidence Ledger (HTF bias değişim defteri) — MPA/4.

Kaynak: Efloud (@EfloudTheSurfer) kanal transkript analizi (2026-07-26).
Kaynağın kuralı:

  "Büyük zaman dilimi küçük zaman diliminden HER ZAMAN daha önemlidir.
   Küçük zaman dilimindeki aksiyonların büyük zaman dilimindeki yapıları
   değiştirme gücü vardır — ama bu TEK bir olayla olmaz; art arda gelen
   3-4-5 emare gerekir. TEK bir emare HTF yapıyı değiştirmez."

Bu modül o kuralı sayılabilir hale getirir: LTF'de biriken KARŞI YÖNLÜ
kanıtlar puanlanır, eskiyenler pencereden düşer, trend yönünde yeni bir
kırılım gelirse defter SIFIRLANIR.

Verdict semantiği:
  INTACT      — skor < transition_at. Normal işleyiş.
  TRANSITION  — transition_at <= skor < flip_at. HTF bias hâlâ geçerli ama
                ESKİ YÖNDE YENİ trend-devam işlemi AÇILMAZ (gate G9).
                Açık pozisyonlar kapatılmaz.
  FLIP        — skor >= flip_at VE en az bir YAPISAL kanıt (E1/E2) var.
                Bias çevrilir.

`flip_at` için yapısal kanıt şartı kritiktir: yalnızca "yumuşak" kanıtlarla
(momentum kaybı, dolmamış imbalance) 5 puan toplayıp yapı kırılımı OLMADAN
bias çevirmeyi engeller.

⚠️ Bu modül mevcut HTF bias hesabını DEĞİŞTİRMEZ. Ek bir katman olarak
çalışır: `smc_v2.bias_ledger: false` varsayılanıyla hiç çağrılmaz ve
V1/V2/V3 canlı botlarının davranışı birebir korunur.

ÇIKARIM UYARISI: Kaynak "3-5 ardışık emare" diyor ama (a) kanıtın hangi
TF'de sayılacağını, (b) kanıt tiplerinin göreli ağırlığını, (c) 3/5 iki
kademeli eşiği BELİRTMİYOR. Aşağıdaki ağırlık tablosu ve eşikler mühendislik
yorumudur; backtest'te ÖNCE bunlar taranmalıdır.

Saf fonksiyon — I/O yok, log yok.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import pandas as pd

from engine.smc import FVG, StructBreak, Swing

# Kanıt tipleri ve ağırlıkları — hepsi ÇIKARIM (kaynakta sayı yok).
EVIDENCE_WEIGHTS: Dict[str, int] = {
    "E1_CHOCH": 2,                  # karşı yönde ilk yapı kırılımı (YAPISAL)
    "E2_BOS_AFTER_CHOCH": 2,        # CHoCH sonrası karşı yönde BOS (YAPISAL)
    "E3_DISPLACEMENT_FVG": 1,       # karşı yönde displacement + FVG bıraktı
    "E4_SWEEP_SFP": 1,              # majör likidite süpürmesi + geri kapanış
    "E5_OB_MITIGATED": 1,           # HTF karşı OB/breaker mitigate + tepki
    "E6_NO_NEW_EXTREME": 1,         # trend yönünde yeni ekstremum yapamama
    "E7_IMBALANCE_UNRECLAIMED": 1,  # trend yönündeki taze imbalance geri alınamadı
    "E8_MOMENTUM_LOSS": 1,          # ardışık küçülen gövdeler
}

STRUCTURAL_CODES = frozenset({"E1_CHOCH", "E2_BOS_AFTER_CHOCH"})

VERDICT_INTACT = "INTACT"
VERDICT_TRANSITION = "TRANSITION"
VERDICT_FLIP = "FLIP"


@dataclass
class Evidence:
    """Tek bir karşı-yönlü emare.

    `leg_id` çift-sayım engeli: aynı swing bacağından en fazla BİR kanıt
    sayılır (en ağır olanı). Aksi halde tek bir sert hareket 4-5 kanıt
    üretip defteri tek başına doldurabilirdi.
    """

    code: str
    idx: int
    leg_id: int
    note: str = ""

    @property
    def weight(self) -> int:
        return EVIDENCE_WEIGHTS.get(self.code, 0)

    @property
    def structural(self) -> bool:
        return self.code in STRUCTURAL_CODES


@dataclass
class LedgerVerdict:
    verdict: str
    score: int
    has_structural: bool
    counted: List[Evidence] = field(default_factory=list)
    dropped: List[Evidence] = field(default_factory=list)
    reset_idx: Optional[int] = None


def _counter(bias: str) -> str:
    return "BEAR" if bias == "BULL" else "BULL"


def find_reset_idx(bias: str, breaks: Sequence[StructBreak]) -> Optional[int]:
    """Defteri sıfırlayan son olayın ordinali.

    Trend YÖNÜNDE yeni bir BOS (yani tezi doğrulayan bir kırılım) geldiyse,
    ondan önceki tüm karşı kanıtlar geçersizdir.
    """
    reset = None
    for brk in breaks:
        if brk.kind == "BOS" and brk.direction == bias:
            if reset is None or brk.idx > reset:
                reset = brk.idx
    return reset


def evaluate_bias_ledger(
    evidence: Sequence[Evidence],
    current_idx: int,
    window_bars: int = 20,
    transition_at: int = 3,
    flip_at: int = 5,
    reset_idx: Optional[int] = None,
) -> LedgerVerdict:
    """Kanıt defterini muhasebeleştir ve karar üret.

    Args:
        evidence: toplanmış Evidence listesi (sıra önemsiz).
        current_idx: değerlendirme anındaki bar ordinali.
        window_bars: kayan pencere; `idx <= current_idx - window_bars` olan
            kanıtlar düşer.
        transition_at / flip_at: eşikler ("3-5 ardışık emare" kuralı).
        reset_idx: `find_reset_idx` çıktısı; bu ordinalde veya öncesinde
            oluşan kanıtlar sayılmaz.
    """
    cutoff = current_idx - window_bars
    counted: List[Evidence] = []
    dropped: List[Evidence] = []

    # 1) Pencere ve reset filtresi
    surviving: List[Evidence] = []
    for ev in evidence:
        if ev.idx <= cutoff:
            dropped.append(ev)
            continue
        if reset_idx is not None and ev.idx <= reset_idx:
            dropped.append(ev)
            continue
        if ev.weight == 0:
            dropped.append(ev)
            continue
        surviving.append(ev)

    # 2) Bacak başına tek kanıt — en ağırı kazanır, eşitlikte en yenisi.
    best_per_leg: Dict[int, Evidence] = {}
    for ev in surviving:
        cur = best_per_leg.get(ev.leg_id)
        if cur is None or (ev.weight, ev.idx) > (cur.weight, cur.idx):
            if cur is not None:
                dropped.append(cur)
            best_per_leg[ev.leg_id] = ev
        else:
            dropped.append(ev)

    counted = sorted(best_per_leg.values(), key=lambda e: e.idx)
    score = sum(e.weight for e in counted)
    has_structural = any(e.structural for e in counted)

    if score >= flip_at and has_structural:
        verdict = VERDICT_FLIP
    elif score >= transition_at:
        verdict = VERDICT_TRANSITION
    else:
        verdict = VERDICT_INTACT

    return LedgerVerdict(
        verdict=verdict,
        score=score,
        has_structural=has_structural,
        counted=counted,
        dropped=dropped,
        reset_idx=reset_idx,
    )


def _leg_id_for(idx: int, break_idxs: Sequence[int]) -> int:
    """Kanıtı, kendisinden önceki SON yapı kırılımına göre bir bacağa ata."""
    leg = -1
    for b in break_idxs:
        if b <= idx and b > leg:
            leg = b
    return leg


def collect_structural_evidence(
    bias: str,
    breaks: Sequence[StructBreak],
    df: pd.DataFrame,
    swings: Optional[dict] = None,
    fvgs: Optional[Sequence[FVG]] = None,
    disp_mult: float = 1.5,
    body_ref_len: int = 20,
    momentum_run: int = 3,
) -> List[Evidence]:
    """Ham yapıdan türetilebilen kanıtları topla (E1, E2, E3, E6, E8).

    E4 (sweep+SFP) ve E5 (OB mitigasyonu) bu fonksiyonda ÜRETİLMEZ — onlar
    `engine.smc_v2.liquidity` ve OB durumundan gelir; çağıran hazır Evidence
    olarak ekleyebilir. E7 de aynı şekilde dışarıdan enjekte edilebilir.
    Bilinçli kapsam kısıtı: bu modül her şeyi hesaplamaya çalışmaz, muhasebeyi
    ve kolay türetilebilir kanıtları üstlenir.

    Args:
        bias: mevcut HTF bias — "BULL" | "BEAR".
        breaks: kanıt TF'indeki yapı kırılımları.
        df: kanıt TF'i OHLC DataFrame (ordinal eksen = konum).
        swings: {"swing_highs": [Swing...], "swing_lows": [Swing...]} — E6 için.
        fvgs: FVG listesi — E3 için (displacement barıyla idx eşleşmesi aranır).
        disp_mult / body_ref_len: displacement eşiği.
        momentum_run: E8 için ardışık küçülen gövde sayısı.
    """
    if bias not in ("BULL", "BEAR") or df is None or len(df) == 0:
        return []

    counter = _counter(bias)
    break_idxs = sorted(b.idx for b in breaks)
    out: List[Evidence] = []

    # --- E1 / E2: karşı yönlü yapı kırılımları ---
    counter_choch_idx: Optional[int] = None
    for brk in sorted(breaks, key=lambda b: b.idx):
        if brk.direction != counter:
            continue
        if brk.kind == "CHoCH":
            if counter_choch_idx is None:
                counter_choch_idx = brk.idx
            out.append(Evidence(
                code="E1_CHOCH",
                idx=brk.idx,
                leg_id=_leg_id_for(brk.idx, break_idxs),
                note=f"counter CHoCH @{brk.price}",
            ))
        elif brk.kind == "BOS" and counter_choch_idx is not None and brk.idx > counter_choch_idx:
            out.append(Evidence(
                code="E2_BOS_AFTER_CHOCH",
                idx=brk.idx,
                leg_id=_leg_id_for(brk.idx, break_idxs),
                note=f"counter BOS after CHoCH @{brk.price}",
            ))

    # --- E3: karşı yönde displacement + FVG ---
    ref = (df["high"] - df["low"]).rolling(body_ref_len, min_periods=1).mean()
    body = (df["close"] - df["open"]).abs()
    fvg_idxs = {f.idx for f in (fvgs or []) if f.direction == counter}
    for i in range(len(df)):
        if body.iloc[i] < disp_mult * ref.iloc[i]:
            continue
        bar_dir = "BULL" if df["close"].iloc[i] > df["open"].iloc[i] else "BEAR"
        if bar_dir != counter:
            continue
        # FVG listesi verildiyse eşleşme ara; verilmediyse displacement tek
        # başına yeterli sayılmaz (kanıt "displacement + FVG").
        if fvgs is not None and i not in fvg_idxs:
            continue
        if fvgs is None:
            continue
        out.append(Evidence(
            code="E3_DISPLACEMENT_FVG",
            idx=i,
            leg_id=_leg_id_for(i, break_idxs),
            note=f"counter displacement + FVG @bar {i}",
        ))

    # --- E6: trend yönünde yeni ekstremum yapamama ---
    if swings:
        if bias == "BULL":
            highs = sorted(swings.get("swing_highs", []), key=lambda s: s.idx)
            if len(highs) >= 2 and highs[-1].price < highs[-2].price:
                out.append(Evidence(
                    code="E6_NO_NEW_EXTREME",
                    idx=highs[-1].idx,
                    leg_id=_leg_id_for(highs[-1].idx, break_idxs),
                    note="lower high in BULL bias",
                ))
        else:
            lows = sorted(swings.get("swing_lows", []), key=lambda s: s.idx)
            if len(lows) >= 2 and lows[-1].price > lows[-2].price:
                out.append(Evidence(
                    code="E6_NO_NEW_EXTREME",
                    idx=lows[-1].idx,
                    leg_id=_leg_id_for(lows[-1].idx, break_idxs),
                    note="higher low in BEAR bias",
                ))

    # --- E8: momentum kaybı (trend yönünde ardışık küçülen gövdeler) ---
    if len(df) >= momentum_run:
        tail = df.iloc[-momentum_run:]
        bodies = (tail["close"] - tail["open"]).values
        trend_ok = all(b > 0 for b in bodies) if bias == "BULL" else all(b < 0 for b in bodies)
        shrinking = all(abs(bodies[k]) < abs(bodies[k - 1]) for k in range(1, len(bodies)))
        if trend_ok and shrinking:
            idx = len(df) - 1
            out.append(Evidence(
                code="E8_MOMENTUM_LOSS",
                idx=idx,
                leg_id=_leg_id_for(idx, break_idxs),
                note=f"{momentum_run} shrinking bodies in trend direction",
            ))

    return out


def ledger_blocks_new_entry(verdict: LedgerVerdict, direction: str, bias: str) -> bool:
    """Gate G9: TRANSITION'da ESKİ YÖNDE yeni trend-devam işlemi açılmaz.

    Karşı yöndeki (reversal) kurgular bu gate'ten etkilenmez — onları
    counter-trend kuralları (confirmation zorunluluğu) yönetir.
    """
    if verdict.verdict != VERDICT_TRANSITION:
        return False
    trend_direction = "LONG" if bias == "BULL" else "SHORT"
    return direction == trend_direction
