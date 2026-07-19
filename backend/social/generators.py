"""Deterministic social content generators — 4h cycle (P-Kronos-Social).

Kronos cascade çıktısı + 3-bot filo durumu + SMC eğitim havuzundan
compliance-safe X/Instagram post gövdeleri üretir. LLM YOK — tamamen
deterministik şablonlar (compliance gate'i her üretimde koşulur, ama
şablonların kendisi de gate kurallarına göre yazılmıştır):

- Mutlak $ tutarı YOK (scripts.content_compliance._MONEY)
- Performans-% iddiası YOK (win-rate/kâr yüzdesi); yön konsensüsü ve
  band genişliği KELİMEYLE verilir (narrow/moderate/wide), sayı ile değil
- Yasak ifade YOK (BANNED_TR/EN_PHRASES)
- Sim-kelimeler (backtest/shadow/...) YOK → unlabeled_simulation riski yok
- Her post dile uygun disclaimer taşır

Trade path'e sıfır dokunuş: bu modül yalnız okur ve metin üretir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("efloud.social.generators")

# X (Twitter) free tier hard limit.
X_CHAR_LIMIT = 280

# Dil bazlı zorunlu disclaimer'lar. EN, engine.content_jobs.COMPLIANCE_EN ile
# aynı metindir (import etmiyoruz ki bu modül engine'e bağımlı olmasın —
# testte doğrulanır). RU karşılığı P-Kronos-Social ile eklendi.
DISCLAIMER = {
    "en": "Not investment advice. Trade at your own risk.",
    "ru": "Не является инвестиционной рекомендацией. Торговля — ваш риск.",
}

# Slot rotasyonu (UTC saat // 4 → günde 6 slot, 3 tipin dönüşümü):
SLOT_TYPES = ("market_update", "performance_recap", "educational")


@dataclass
class DraftSpec:
    """create_draft'a beslenecek hazır içerik."""

    body: str
    lang: str            # "en" | "ru"
    post_type: str       # content_queue whitelist'inden
    meta: dict[str, Any] = field(default_factory=dict)


# ────────────────────────── Educational havuz ──────────────────────────
# (EN, RU) çiftleri. Sıra deterministik — slot indexiyle seçilir.

EDU_POOL: list[tuple[str, str]] = [
    (
        "SMC basics: an Order Block is the last opposing candle cluster before "
        "an impulsive break. Our bots only rank it as A+ when HTF bias, "
        "liquidity sweep and OTE zone all agree.",
        "Основы SMC: ордер-блок — это последний противоположный кластер свечей "
        "перед импульсным пробоем. Наши боты дают ему высший ранг, только когда "
        "HTF-тренд, снятие ликвидности и зона OTE совпадают.",
    ),
    (
        "Why multi-timeframe? HTF sets the bias, MTF maps the structure, entry "
        "TF times the trigger. One timeframe alone is half the picture — "
        "confluence is the whole point.",
        "Зачем мульти-таймфрейм? HTF задаёт тренд, MTF показывает структуру, "
        "младший ТФ даёт точку входа. Один таймфрейм — лишь половина картины, "
        "суть в конфлюэнсе.",
    ),
    (
        "A liquidity sweep is not a breakout. When price spikes past equal "
        "highs and snaps back, smart money likely filled orders there. Our "
        "bots read the snap-back, not the spike.",
        "Снятие ликвидности — это не пробой. Когда цена пробивает равные "
        "максимумы и резко возвращается, крупный игрок скорее всего набрал "
        "позицию. Боты читают возврат, а не сам вынос.",
    ),
    (
        "Fair Value Gap (FVG): a 3-candle imbalance the market often revisits. "
        "We treat an FVG as a magnet zone, never as a standalone entry — it "
        "needs structure break confirmation first.",
        "Fair Value Gap (FVG): дисбаланс из трёх свечей, куда рынок часто "
        "возвращается. FVG для нас — зона-магнит, но не самостоятельный вход: "
        "сначала нужен слом структуры.",
    ),
    (
        "Risk first, entries second. Every bot position ships with a "
        "structure-based stop loss plus an ATR buffer, and TP levels mapped to "
        "real liquidity — not round numbers.",
        "Сначала риск, потом вход. Каждая позиция бота имеет стоп-лосс по "
        "структуре с буфером ATR, а тейки строятся по реальной ликвидности, а "
        "не по круглым числам.",
    ),
    (
        "Market Structure Break (MSB) is our first filter: no confirmed break, "
        "no trade. Candle patterns without structure context are noise.",
        "Слом структуры (MSB) — наш первый фильтр: нет подтверждённого слома — "
        "нет сделки. Свечные паттерны без контекста структуры — это шум.",
    ),
    (
        "Discount vs premium: in an active range we only look for longs in the "
        "discount half and shorts in the premium half. Location beats "
        "indicator signals.",
        "Дисконт и премиум: в активном диапазоне мы ищем лонги только в нижней "
        "(дисконт) половине, шорты — в верхней (премиум). Локация важнее "
        "индикаторов.",
    ),
    (
        "Confluence scoring: each signal is graded across structure, zones, "
        "liquidity and trend alignment. Below threshold, the bot simply "
        "stands aside. No forced trades, ever.",
        "Скоринг конфлюэнса: каждый сигнал оценивается по структуре, зонам, "
        "ликвидности и тренду. Ниже порога бот просто не торгует. Никаких "
        "сделок ради сделок.",
    ),
]

# ────────────────────────── Yardımcılar ──────────────────────────


def slot_index_for_hour(hour_utc: int) -> int:
    """UTC saat → 4-saatlik slot (0..5)."""
    return (hour_utc % 24) // 4


def post_type_for_slot(slot: int) -> str:
    """Slot → post tipi rotasyonu."""
    return SLOT_TYPES[slot % len(SLOT_TYPES)]


def _clip(text: str, limit: int = X_CHAR_LIMIT) -> str:
    """X limitine sığdır (kelime sınırında kes, disclaimer'ı asla kesme)."""
    if len(text) <= limit:
        return text
    # Disclaimer son satırdır — onu koruyarak gövdeyi kırp.
    lines = text.rsplit("\n", 1)
    if len(lines) == 2:
        body, tail = lines
        budget = limit - len(tail) - 1
        if budget > 40:
            clipped = body[:budget].rsplit(" ", 1)[0].rstrip(" ,.;—-")
            return f"{clipped}…\n{tail}"
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _band_word(band: str, lang: str) -> str:
    m = {
        "en": {"NARROW": "narrow band", "MODERATE": "moderate band", "WIDE": "wide band"},
        "ru": {"NARROW": "узкий диапазон", "MODERATE": "средний диапазон", "WIDE": "широкий диапазон"},
    }
    return m[lang].get(band, band.lower())


def _dir_word(direction: str, lang: str) -> str:
    m = {
        "en": {"UP": "up", "DOWN": "down", "FLAT": "flat"},
        "ru": {"UP": "вверх", "DOWN": "вниз", "FLAT": "флэт"},
    }
    return m[lang].get(direction, direction.lower())


# ────────────────────────── Üreticiler ──────────────────────────


def build_market_update(kronos: dict[str, Any], lang: str) -> str | None:
    """Kronos cascade JSON'undan market_update gövdesi.

    kronos formatı (scripts.kronos_service çıktısı):
    {"profile": "mid", "symbols": {"BTC": {"aligned": true|false|None,
        "layers": {"htf": {"direction","band","confirmed"}, ...}}}}

    Dönen None → çağıran educational'a düşer (Kronos verisi yok/boş).
    """
    symbols = (kronos or {}).get("symbols") or {}
    if not symbols:
        return None

    parts: list[str] = []
    for sym, info in list(symbols.items())[:4]:
        htf = (info.get("layers") or {}).get("htf") or {}
        direction = htf.get("direction")
        band = htf.get("band")
        if htf.get("confirmed") and direction and band:
            seg = f"{sym}: {_dir_word(direction, lang)}, {_band_word(band, lang)}"
        elif band or htf.get("runs"):
            # Koşu(lar) var ama konsensüs yok → dürüstçe "gürültü" raporla.
            seg = (
                f"{sym}: mixed runs = noise, no read"
                if lang == "en"
                else f"{sym}: прогоны расходятся — шум, без вывода"
            )
        else:
            continue  # katman tamamen boş (Kronos o sembolde hiç koşamamış)
        parts.append(seg)

    if not parts:
        return None

    if lang == "en":
        head = "Kronos AI daily-bias read (4h cycle): "
        tail = (
            "SMC structure stays the trigger; the model only confirms or vetoes."
        )
    else:
        head = "Kronos AI — дневной прогноз (цикл 4ч): "
        tail = "Триггер — структура SMC; модель лишь подтверждает или отменяет."

    body = head + " · ".join(parts) + "\n" + tail + "\n" + DISCLAIMER[lang]
    return _clip(body)


def build_fleet_status(fleet: dict[str, Any], lang: str) -> str | None:
    """3-bot filo durumu → performance_recap gövdesi (yüzdesiz, $'sız).

    fleet: {"bots": {"scalp": {"up": bool, "tf": "5m/1h/12h"}, ...},
            "open_positions": int|None, "signals_24h": int|None}

    Herhangi bir bot down ise None döner (marka açısından down-bot'u
    duyurmayız; çağıran educational'a düşer).
    """
    bots = (fleet or {}).get("bots") or {}
    if len(bots) < 3 or not all(b.get("up") for b in bots.values()):
        return None

    tfs = {k: v.get("tf", "") for k, v in bots.items()}
    pos = fleet.get("open_positions")
    sig = fleet.get("signals_24h")

    if lang == "en":
        body = (
            f"Fleet check: 3 SMC bots live on Binance perps — "
            f"scalp {tfs.get('scalp', '')}, mid {tfs.get('mid', '')}, "
            f"long {tfs.get('long', '')}."
        )
        if isinstance(pos, int):
            body += f" {pos} open position{'s' if pos != 1 else ''} right now."
        if isinstance(sig, int):
            body += f" {sig} signals scanned in the last 24h."
        body += " Every entry is rule-based and SL-protected."
    else:
        body = (
            f"Статус флота: 3 SMC-бота работают на перпах Binance — "
            f"скальп {tfs.get('scalp', '')}, мид {tfs.get('mid', '')}, "
            f"лонг {tfs.get('long', '')}."
        )
        if isinstance(pos, int):
            body += f" Открытых позиций сейчас: {pos}."
        if isinstance(sig, int):
            body += f" За 24 часа просканировано сигналов: {sig}."
        body += " Каждый вход — по правилам и со стоп-лоссом."

    body += "\n" + DISCLAIMER[lang]
    return _clip(body)


def build_educational(day_ordinal: int, slot: int, lang: str) -> str:
    """Eğitim havuzundan deterministik seçim (gün+slot → index)."""
    en, ru = EDU_POOL[(day_ordinal + slot) % len(EDU_POOL)]
    body = (en if lang == "en" else ru) + "\n" + DISCLAIMER[lang]
    return _clip(body)


def build_cycle_drafts(
    *,
    slot: int,
    day_ordinal: int,
    kronos: dict[str, Any] | None,
    fleet: dict[str, Any] | None,
    langs: tuple[str, ...] = ("en", "ru"),
    platforms: tuple[str, ...] = ("x",),
) -> list[DraftSpec]:
    """Bir 4h slotu için tüm draft'ları üret (lang başına 1 post).

    Slot tipi üretilemezse (Kronos verisi yok, bot down…) educational'a
    düşer — döngü asla boş geçmez.
    """
    want_type = post_type_for_slot(slot)
    out: list[DraftSpec] = []

    for lang in langs:
        body: str | None = None
        actual_type = want_type

        if want_type == "market_update":
            body = build_market_update(kronos or {}, lang)
        elif want_type == "performance_recap":
            body = build_fleet_status(fleet or {}, lang)

        if body is None:
            actual_type = "educational"
            body = build_educational(day_ordinal, slot, lang)

        out.append(
            DraftSpec(
                body=body,
                lang=lang,
                post_type=actual_type,
                meta={
                    "source": "social_content_routine",
                    "slot": slot,
                    "platforms": list(platforms),
                    "wanted_type": want_type,
                },
            )
        )
    return out
