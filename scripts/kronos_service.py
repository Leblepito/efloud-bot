"""Kronos cascade service — PLAYBOOK'un sunucu-tarafı otomasyonu.

`.claude/skills/kronos` skill'ini (run_kronos.py launcher) subprocess ile
çağırıp PLAYBOOK.md'deki profil→katman komut haritasını ve 3-koşu konsensüs
ritüelini uygular. Çıktı `data/market/kronos_cascade.json`'a atomic yazılır;
`scripts/routines/social_content.py` bu dosyayı okur.

Trade path'e sıfır dokunuş: emir vermez, config'e dokunmaz, sadece dosya yazar.
Kronos kurulu değilse / koşu başarısızsa sembol atlanır — fail-safe.

Kullanım:
    python -m scripts.kronos_service                # env/default sembollerle
    python -m scripts.kronos_service BTC ETH SOL    # explicit semboller

Env:
    KRONOS_SKILL_DIR       default: .claude/skills/kronos
    KRONOS_SYMBOLS         default: BTC,ETH,SOL   (yfinance -USD eklenir)
    KRONOS_RUNS_PER_LAYER  default: 3
    KRONOS_OUTPUT_PATH     default: data/market/kronos_cascade.json
    KRONOS_RUN_TIMEOUT_SEC default: 300 (koşu başına)
    KRONOS_EXEC_MODE       default: launcher
        launcher → skill'in run_kronos.py'si (ilk koşuda venv+repo kurar;
                   lokal/Windows kullanımı)
        direct   → skill'in _predict.py'si sistem python'uyla (torch'un
                   kurulu geldiği Dockerfile.kronos container'ı için)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# PLAYBOOK.md §2 — profil → (katman, period, interval, pred_len).
# yfinance 4h/8h/12h desteklemez; HTF'ler 1d/1wk'e eşlenir (PLAYBOOK §0.1).
PROFILE_LAYERS: dict[str, list[tuple[str, str, str, str]]] = {
    "scalp": [
        ("htf", "6mo", "1d", "14"),
        ("mtf", "1mo", "1h", "24"),
        ("ltf", "5d", "5m", "12"),
    ],
    "mid": [
        ("htf", "2y", "1d", "14"),
        ("mtf", "3mo", "1h", "24"),
        ("ltf", "1mo", "15m", "12"),
    ],
    "long": [
        ("htf", "max", "1wk", "12"),
        ("mtf", "2y", "1d", "20"),
        ("ltf", "3mo", "1h", "24"),
    ],
}

# _predict.py format_output satırları (bkz. skill scripts/_predict.py):
#   **Direction:** UP (+2.34%)
#   **Confidence band:** NARROW (signal worth investigating)
_DIRECTION_RE = re.compile(r"\*\*Direction:\*\*\s+(UP|DOWN|FLAT)\b")
_BAND_RE = re.compile(r"\*\*Confidence band:\*\*\s+(NARROW|MODERATE|WIDE)\b")


def _skill_dir() -> Path:
    return Path(os.environ.get("KRONOS_SKILL_DIR", ".claude/skills/kronos"))


def _symbols() -> list[str]:
    raw = os.environ.get("KRONOS_SYMBOLS", "BTC,ETH,SOL")
    return [s.strip().upper().replace("-USD", "") for s in raw.split(",") if s.strip()]


def _runs_per_layer() -> int:
    try:
        return max(1, int(os.environ.get("KRONOS_RUNS_PER_LAYER", "3")))
    except ValueError:
        return 3


def _run_timeout() -> int:
    try:
        return int(os.environ.get("KRONOS_RUN_TIMEOUT_SEC", "300"))
    except ValueError:
        return 300


def run_once(
    symbol: str, period: str, interval: str, pred_len: str,
    *, skill_dir: Path | None = None, timeout: int | None = None,
) -> dict | None:
    """Tek Kronos koşusu → {"direction": ..., "band": ...} | None (hata)."""
    sd = skill_dir or _skill_dir()
    if os.environ.get("KRONOS_EXEC_MODE", "launcher").strip().lower() == "direct":
        # Container modu: torch sistem python'unda kurulu → _predict.py direkt.
        script = sd / "scripts" / "_predict.py"
        env = {**os.environ, "KRONOS_REPO": str(sd / "_kronos")}
        cmd = [sys.executable, str(script), f"{symbol}-USD", period, interval, pred_len]
    else:
        script = sd / "scripts" / "run_kronos.py"
        env = None
        cmd = [sys.executable, str(script), f"{symbol}-USD", period, interval, pred_len]
    if not script.exists():
        print(f"[kronos_service] script yok: {script}", file=sys.stderr)
        return None
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout or _run_timeout(),
            env=env,
        )
    except subprocess.TimeoutExpired:
        print(f"[kronos_service] timeout: {symbol} {interval}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(
            f"[kronos_service] koşu hata ({symbol} {interval}): "
            f"{(proc.stderr or '')[-300:]}",
            file=sys.stderr,
        )
        return None
    dir_m = _DIRECTION_RE.search(proc.stdout or "")
    band_m = _BAND_RE.search(proc.stdout or "")
    if not dir_m or not band_m:
        print(f"[kronos_service] parse edilemedi: {symbol} {interval}", file=sys.stderr)
        return None
    return {"direction": dir_m.group(1), "band": band_m.group(1)}


def consensus(runs: list[dict]) -> dict:
    """PLAYBOOK §3 — çoğunluk yön + en sık band; confirmed = ≥%50+1 aynı yön.

    runs boş → confirmed=False, direction=None.
    """
    if not runs:
        return {"direction": None, "band": None, "confirmed": False, "runs": 0}
    dirs = Counter(r["direction"] for r in runs)
    bands = Counter(r["band"] for r in runs)
    direction, dir_count = dirs.most_common(1)[0]
    band = bands.most_common(1)[0][0]
    confirmed = dir_count * 2 > len(runs)  # strict majority
    return {
        "direction": direction if confirmed else None,
        "band": band,
        "confirmed": confirmed,
        "runs": len(runs),
        "votes": dict(dirs),
    }


def cascade_symbol(symbol: str, profile: str, runs_per_layer: int) -> dict:
    """Bir sembol için 3-katman cascade (PLAYBOOK §4)."""
    layers: dict[str, dict] = {}
    for layer, period, interval, pred_len in PROFILE_LAYERS[profile]:
        results = []
        for _ in range(runs_per_layer):
            r = run_once(symbol, period, interval, pred_len)
            if r:
                results.append(r)
        layers[layer] = consensus(results)

    directions = {
        l: v["direction"] for l, v in layers.items() if v.get("confirmed")
    }
    aligned: bool | None
    if len(directions) < 3:
        aligned = None  # en az bir katman gürültü/başarısız → hizalama bilinmiyor
    else:
        aligned = len(set(directions.values())) == 1
    return {"layers": layers, "aligned": aligned}


def load_profile(config_path: str = "config.yaml") -> str:
    """config.yaml → timeframes.profile; yoksa/geçersizse 'mid'."""
    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        prof = ((cfg.get("timeframes") or {}).get("profile") or "").strip().lower()
        if prof in PROFILE_LAYERS:
            return prof
    except Exception as exc:  # config yoksa da servis çalışsın
        print(f"[kronos_service] config okunamadı ({exc}) → mid", file=sys.stderr)
    return "mid"


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    symbols = [a.upper().replace("-USD", "") for a in args] or _symbols()
    profile = load_profile()
    runs = _runs_per_layer()
    out_path = Path(os.environ.get("KRONOS_OUTPUT_PATH", "data/market/kronos_cascade.json"))

    print(
        f"[kronos_service] profile={profile} symbols={symbols} runs/layer={runs}",
        file=sys.stderr,
    )

    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "runs_per_layer": runs,
        "symbols": {},
    }
    for sym in symbols:
        payload["symbols"][sym] = cascade_symbol(sym, profile, runs)

    # Hiçbir sembol tek katman bile üretemediyse eski dosyayı EZME —
    # social_content bayat-ama-geçerli veriyle devam edebilsin.
    any_data = any(
        any(l.get("runs") for l in s["layers"].values())
        for s in payload["symbols"].values()
    )
    if not any_data:
        print("[kronos_service] hiç veri üretilemedi — çıktı yazılmadı", file=sys.stderr)
        return 1

    atomic_write_json(out_path, payload)
    print(f"[kronos_service] yazıldı: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
