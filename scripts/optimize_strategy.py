#!/usr/bin/env python3
"""Efloud-bot Strategy Parameter Optimizer (Autoresearch Loop).

Sistemli veya rastgele arama yontemiyle config.yaml icindeki strateji parametrelerini
backtest motoru uzerinden otonom sekilde optimize eder ve en iyi adaylari raporlar.
Canli production konfigurasyonunu dogrudan degistirmez.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

# Logger kurulumu
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("efloud.optimizer")


def load_yaml_config(path: Path) -> dict[str, Any]:
    """YAML konfigürasyon dosyasını yükler."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml_config(path: Path, config: dict[str, Any]) -> None:
    """YAML konfigürasyon dosyasını kaydeder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True)


def create_candidate_config(
    base_path: Path,
    output_path: Path,
    min_confluence: int,
    risk_per_trade_pct: float,
    recency_bars: int,
    min_rr: float,
) -> None:
    """Belirtilen parametrelerle aday bir konfigurasyon dosyasi yazar."""
    config = load_yaml_config(base_path)

    # Parametreleri ez
    config.setdefault("risk", {})
    config["risk"]["min_confluence"] = min_confluence
    config["risk"]["risk_per_trade_pct"] = risk_per_trade_pct
    config["risk"]["recency_bars"] = recency_bars
    config["risk"]["min_rr"] = min_rr

    save_yaml_config(output_path, config)


def find_latest_portfolio_result(search_dir: Path, timestamp_cutoff: float) -> dict[str, Any] | None:
    """Belirtilen kesme zamanindan sonra olusturulmus en son portfolio result.json dosyasini bulur."""
    if not search_dir.exists():
        return None

    best_file: Path | None = None
    best_mtime: float = 0.0

    # reports/backtests/ altindeki tum result.json dosyalarini ara
    for p in search_dir.glob("**/result.json"):
        # Klasor adinda portfolio gectiginden emin ol
        if "portfolio" not in p.parent.name:
            continue
        mtime = p.stat().st_mtime
        if mtime > timestamp_cutoff and mtime > best_mtime:
            best_mtime = mtime
            best_file = p

    if best_file is None:
        return None

    try:
        with open(best_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Result dosyasi okunamadi %s: %s", best_file, e)
        return None


def run_portfolio_backtest(
    config_path: Path,
    symbols: str,
    period_days: int,
    balance: float,
) -> dict[str, Any] | None:
    """Subprocess ile portfolio backtest'ini tetikler ve sonucunu doner."""
    start_time = time.time()
    cmd = [
        sys.executable,
        "-m",
        "backtest.cli",
        "portfolio",
        "--config",
        str(config_path),
        "--symbols",
        symbols,
        "--period-days",
        str(period_days),
        "--balance",
        str(balance),
    ]

    logger.info("Backtest tetikleniyor: %s", " ".join(cmd))
    try:
        # Çıktıları yakala ve sessizce çalıştır
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.debug("Backtest çıktısı:\n%s", res.stdout)
    except subprocess.CalledProcessError as e:
        logger.error("Backtest hatayla sonlandi (Exit %d):\n%s", e.returncode, e.stderr)
        return None

    # reports/backtests altındaki son result.json dosyasını bul
    result = find_latest_portfolio_result(Path("reports/backtests"), start_time - 2)
    return result


def calculate_fitness(result: dict[str, Any], max_drawdown_limit: float = 12.0) -> tuple[float, float, float, float, str]:
    """Backtest sonucundan fitness skoru hesaplar."""
    total_return_pct = float(result.get("total_return_pct", 0.0))
    max_drawdown_pct = float(result.get("max_drawdown_pct", 0.0))
    sharpe_like = float(result.get("sharpe_like", 0.0))

    # Kısıt kontrolü: Drawdown limiti aşılırsa fitness 0.0 ve doğrudan discard
    if max_drawdown_pct > max_drawdown_limit:
        return 0.0, total_return_pct, max_drawdown_pct, sharpe_like, "discard_drawdown_exceeded"

    # Fitness formülü: Sharpe * (1 + Return/100)
    # Sharpe negatifse return de negatif olacağından çarpanı sınırla
    multiplier = max(0.0, 1.0 + total_return_pct / 100.0)
    fitness = sharpe_like * multiplier
    fitness = max(0.0, round(fitness, 4))

    return fitness, total_return_pct, max_drawdown_pct, sharpe_like, "keep"


def append_to_tsv(
    tsv_path: Path,
    min_confluence: int,
    risk_per_trade_pct: float,
    recency_bars: int,
    min_rr: float,
    total_return_pct: float,
    max_drawdown_pct: float,
    sharpe_like: float,
    fitness: float,
    status: str,
) -> None:
    """Optimizasyon sonucunu TSV dosyasına ekler."""
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not tsv_path.exists()

    with open(tsv_path, "a", encoding="utf-8") as f:
        if write_header:
            f.write(
                "timestamp\tmin_confluence\trisk_per_trade_pct\trecency_bars\tmin_rr\t"
                "total_return_pct\tmax_drawdown_pct\tsharpe_like\tfitness\tstatus\n"
            )
        now_str = datetime.datetime.now().isoformat()
        f.write(
            f"{now_str}\t{min_confluence}\t{risk_per_trade_pct:.4f}\t{recency_bars}\t{min_rr:.2f}\t"
            f"{total_return_pct:.2f}\t{max_drawdown_pct:.2f}\t{sharpe_like:.2f}\t{fitness:.4f}\t{status}\n"
        )


def main() -> None:
    """Ana optimizasyon arama döngüsü."""
    parser = argparse.ArgumentParser(description="Efloud Strategy Parameter Optimizer")
    parser.add_argument("--config", default="config.yaml", help="Temel konfigurasyon dosyasi")
    parser.add_argument("--symbols", default="ETH/USDT,BTC/USDT,SOL/USDT,BNB/USDT,ADA/USDT,LINK/USDT,AVAX/USDT", help="Backtest icin semboller")
    parser.add_argument("--period-days", type=int, default=180, help="Backtest donemi (gun)")
    parser.add_argument("--balance", type=float, default=2000.0, help="Baslangic bakiyesi")
    parser.add_argument("--max-dd", type=float, default=12.0, help="Maksimum izin verilen Drawdown (yuzde)")
    parser.add_argument("--iterations", type=int, default=0, help="Iterasyon sayisi (0 = sonsuz dongu)")
    parser.add_argument("--mode", choices=["hill_climb", "random"], default="hill_climb", help="Arama modu (hill_climb veya random)")
    args = parser.parse_args()

    base_config_path = Path(args.config)
    candidate_config_path = Path("configs/candidate_opt.yaml")
    best_config_path = Path("configs/best_optimized_config.yaml")
    tsv_path = Path("reports/optimization/results.tsv")

    logger.info("=== OPTIMIZATION STARTED ===")
    logger.info("Base Config: %s", base_config_path)
    logger.info("Symbols: %s", args.symbols)
    logger.info("Period Days: %d, Balance: %.1f", args.period_days, args.balance)

    # 1. Baseline Kosusu
    logger.info("--- Establishing Baseline ---")
    base_cfg = load_yaml_config(base_config_path)
    base_min_conf = int(base_cfg.get("risk", {}).get("min_confluence", 55))
    base_risk = float(base_cfg.get("risk", {}).get("risk_per_trade_pct", 0.75))
    base_recency = int(base_cfg.get("risk", {}).get("recency_bars", 40))
    base_min_rr = float(base_cfg.get("risk", {}).get("min_rr", 1.8))

    create_candidate_config(
        base_config_path,
        candidate_config_path,
        base_min_conf,
        base_risk,
        base_recency,
        base_min_rr,
    )
    res = run_portfolio_backtest(candidate_config_path, args.symbols, args.period_days, args.balance)

    if res is None:
        logger.error("Baseline kosusu basarisiz oldu! Cikiliyor.")
        sys.exit(1)

    best_fitness, base_ret, base_dd, base_sharpe, base_status = calculate_fitness(res, args.max_dd)
    logger.info(
        "Baseline Sonuclari: Sharpe=%.2f, Return=%.2f%%, DD=%.2f%% -> Fitness: %.4f (Status: %s)",
        base_sharpe, base_ret, base_dd, best_fitness, base_status
    )

    append_to_tsv(
        tsv_path,
        base_min_conf,
        base_risk,
        base_recency,
        base_min_rr,
        base_ret,
        base_dd,
        base_sharpe,
        best_fitness,
        "keep" if best_fitness > 0 else "discard",
    )

    # En iyi parametreleri kaydet
    best_params = {
        "min_confluence": base_min_conf,
        "risk_per_trade_pct": base_risk,
        "recency_bars": base_recency,
        "min_rr": base_min_rr,
    }
    if best_fitness > 0:
        save_yaml_config(best_config_path, load_yaml_config(candidate_config_path))

    # Arama sinirlari
    bounds = {
        "min_confluence": (50, 90),
        "risk_per_trade_pct": (0.5, 3.0),
        "recency_bars": (20, 60),
        "min_rr": (1.2, 2.5),
    }

    step_sizes = {
        "min_confluence": 5,
        "risk_per_trade_pct": 0.25,
        "recency_bars": 5,
        "min_rr": 0.1,
    }

    iter_count = 0
    while True:
        iter_count += 1
        if args.iterations > 0 and iter_count > args.iterations:
            logger.info("Iterasyon limitine ulasildi (%d). Optimizasyon bitti.", args.iterations)
            break

        logger.info("\n--- Iteration %d ---", iter_count)

        # Aday parametreleri belirle
        if args.mode == "hill_climb" and best_fitness > 0:
            # Hill Climbing: Mevcut en iyi parametrelere kucuk bir rassal adim ekle
            candidate_params = best_params.copy()
            param_to_mutate = random.choice(list(bounds.keys()))
            step = step_sizes[param_to_mutate]
            direction = random.choice([-1, 1])
            new_val = candidate_params[param_to_mutate] + step * direction

            # Sinir kontrolu yap ve clamp'le
            low, high = bounds[param_to_mutate]
            new_val = max(low, min(high, new_val))

            # Tamsayi alanlar icin yuvarla
            if param_to_mutate in ("min_confluence", "recency_bars"):
                new_val = int(round(new_val))

            candidate_params[param_to_mutate] = new_val
        else:
            # Random Search: Tamamen rassal parametre seti sec
            candidate_params = {
                "min_confluence": int(round(random.choice(range(bounds["min_confluence"][0], bounds["min_confluence"][1] + 1, step_sizes["min_confluence"])))),
                "risk_per_trade_pct": round(random.uniform(bounds["risk_per_trade_pct"][0], bounds["risk_per_trade_pct"][1]), 4),
                "recency_bars": int(round(random.choice(range(bounds["recency_bars"][0], bounds["recency_bars"][1] + 1, step_sizes["recency_bars"])))),
                "min_rr": round(random.choice([x * 0.1 for x in range(int(bounds["min_rr"][0] * 10), int(bounds["min_rr"][1] * 10) + 1)]), 1),
            }

        logger.info("Aday Parametreler: %s", candidate_params)

        # Aday konfigurasyonunu olustur
        create_candidate_config(
            base_config_path,
            candidate_config_path,
            candidate_params["min_confluence"],
            candidate_params["risk_per_trade_pct"],
            candidate_params["recency_bars"],
            candidate_params["min_rr"],
        )

        # Backtest kos
        res = run_portfolio_backtest(candidate_config_path, args.symbols, args.period_days, args.balance)

        if res is None:
            logger.warning("Backtest coktu veya basarisiz oldu! Discard ediliyor.")
            append_to_tsv(
                tsv_path,
                candidate_params["min_confluence"],
                candidate_params["risk_per_trade_pct"],
                candidate_params["recency_bars"],
                candidate_params["min_rr"],
                0.0, 0.0, 0.0, 0.0,
                "crash",
            )
            continue

        # Fitness hesapla
        fitness, ret, dd, sharpe, status = calculate_fitness(res, args.max_dd)
        logger.info(
            "Sonuc: Sharpe=%.2f, Return=%.2f%%, DD=%.2f%% -> Fitness: %.4f (Status: %s)",
            sharpe, ret, dd, fitness, status
        )

        # Karsilastir ve ilerle
        if status == "keep" and fitness > best_fitness:
            logger.info("🚀 YENI EN IYI BULUNDU! Eski: %.4f -> Yeni: %.4f", best_fitness, fitness)
            best_fitness = fitness
            best_params = candidate_params.copy()
            # En iyi konfigurasyonu yedekle
            save_yaml_config(best_config_path, load_yaml_config(candidate_config_path))
            append_to_tsv(
                tsv_path,
                candidate_params["min_confluence"],
                candidate_params["risk_per_trade_pct"],
                candidate_params["recency_bars"],
                candidate_params["min_rr"],
                ret, dd, sharpe,
                fitness,
                "keep",
            )
        else:
            logger.info("Discard edildi. En iyi fitness: %.4f", best_fitness)
            append_to_tsv(
                tsv_path,
                candidate_params["min_confluence"],
                candidate_params["risk_per_trade_pct"],
                candidate_params["recency_bars"],
                candidate_params["min_rr"],
                ret, dd, sharpe,
                fitness,
                "discard",
            )


if __name__ == "__main__":
    main()
