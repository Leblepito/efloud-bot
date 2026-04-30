"""Efloud Confluence Scoring — çoklu değerlendirme zorunlu."""

from typing import Tuple, List


def calc_confluence(
    is_long: bool,
    htf_bias: str,
    in_htf_fvg: bool,
    in_ote: bool,
    mtf_choch: bool,
    has_sfp: bool,
    in_ob: bool,
    ob_near_swing: bool,
    ob_at_eq: bool,
    correct_zone: bool,     # long+discount veya short+premium
    has_deviation: bool,
) -> Tuple[int, List[str]]:
    """
    Returns (score 0-100, reasons list).
    Efloud: "Tekil değerlendirilen konseptin çalışma olasılığı çok düşük."
    """
    s, r = 0, []

    bias_match = (is_long and htf_bias == "BULL") or (not is_long and htf_bias == "BEAR")
    if bias_match:
        s += 25; r.append(f"HTF bias aligned ({htf_bias})")
    if mtf_choch:
        s += 20; r.append("MTF CHoCH confirmation")
    if in_htf_fvg:
        s += 15; r.append("Price in HTF FVG")
    if in_ob:
        s += 10; r.append("Price at Order Block")
        if ob_near_swing:
            s += 5; r.append("OB near swing (high conf)")
        if ob_at_eq:
            s += 3; r.append("Price at OB EQ (refined entry)")
    if in_ote:
        s += 10; r.append("Price in OTE (0.618-0.786)")
    if has_sfp:
        s += 10; r.append("SFP liquidity sweep")
    if correct_zone:
        s += 5; r.append("Correct premium/discount zone")
    if has_deviation:
        s += 5; r.append("Range deviation")

    return min(s, 100), r
