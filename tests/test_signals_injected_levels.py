"""HOTFIX (2026-07-23, canlı incident): _collect_smc_blocks injected `levels`
ile HER cycle çöküyordu — `AttributeError: 'Level' object has no attribute 'get'`.

Kırık ifade (satır 158/190, iki simetrik dal):
    p = getattr(lvl, "price", lvl.get("price", 0)) if isinstance(lvl, (dict, object)) else 0

İki ayrı hata:
  1. `getattr`'ın default argümanı EAGER değerlendirilir — lvl bir Level
     dataclass'ıyken `lvl.get(...)` fallback'e gerek kalmadan patlar
     (price attr'ı VAR olsa bile).
  2. `isinstance(lvl, (dict, object))` her nesne için True — koşul anlamsız.

Canlı etki: LevelEngine dolu `levels` enjekte eder → generate_signals her
sembol/cycle'da AttributeError → "[SYM] cycle failed" → V1 sinyal yolu tamamen
ölü, hiçbir pozisyon açılamıyor (bot.ualgotrade + v3 scalp, 2026-07-23).
Testler yakalamamıştı çünkü fikstürler `levels`'ı hep None/boş geçiyordu —
bu dosya o boşluğu kapatır.
"""
from engine.levels import Level
from engine.signals import _collect_smc_blocks


def _lvl(price: float, name: str = "MO") -> Level:
    return Level(name=name, price=price, kind="open")


def test_long_injected_level_dataclass_no_crash_and_collected():
    """PARA TESTİ: Level dataclass'lı liste → crash YOK + entry üstündeki
    seviye LEVEL bloğu olarak toplanır (eski kod AttributeError atıyordu)."""
    blocks = _collect_smc_blocks(
        is_long=True, entry_price=100.0, htf={}, e_range=None,
        levels=[_lvl(110.0), _lvl(90.0)],
    )
    assert (110.0, "LEVEL") in blocks, "entry üstü seviye LONG kâr yönünde toplanmalı"
    assert all(p != 90.0 for p, _ in blocks), "entry altı seviye LONG'da alınmaz"


def test_short_injected_level_dataclass_no_crash_and_collected():
    blocks = _collect_smc_blocks(
        is_long=False, entry_price=100.0, htf={}, e_range=None,
        levels=[_lvl(110.0), _lvl(90.0)],
    )
    assert (90.0, "LEVEL") in blocks
    assert all(p != 110.0 for p, _ in blocks)


def test_dict_levels_still_supported():
    """Regresyon-donduran: dict formatındaki seviyeler (varsa eski üreticiler)
    çalışmaya devam etmeli."""
    blocks = _collect_smc_blocks(
        is_long=True, entry_price=100.0, htf={}, e_range=None,
        levels=[{"price": 120.0}, {"price": 80.0}],
    )
    assert (120.0, "LEVEL") in blocks


def test_malformed_level_entries_skipped_not_crash():
    """price'sız dict / attr'sız nesne / None → sessizce atlanır, cycle ölmez."""
    class Weird:
        pass
    blocks = _collect_smc_blocks(
        is_long=True, entry_price=100.0, htf={}, e_range=None,
        levels=[{"note": "no price"}, Weird(), None, _lvl(105.0)],
    )
    assert (105.0, "LEVEL") in blocks
    assert len([b for b in blocks if b[1] == "LEVEL"]) == 1
