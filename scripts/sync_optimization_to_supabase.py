#!/usr/bin/env python3
"""Efloud-bot Strategy Optimization Results Supabase Sync.

TSV formatindaki optimizasyon sonuclarini Supabase Postgres veritabanina otonom
sekilde senkronize eder.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
import datetime

import asyncpg

# Proje kok dizinini path'e ekle
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import load_dotenv

# Logger kurulumu
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("efloud.supabase_sync")


async def create_table_if_not_exists(conn: asyncpg.Connection) -> None:
    """Supabase uzerinde optimizasyon sonuclari tablosunu olusturur."""
    # UNIQUE constraint ekleyerek duplicate kayitlari engelle
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_optimization_results (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            min_confluence INT NOT NULL,
            risk_per_trade_pct DOUBLE PRECISION NOT NULL,
            recency_bars INT NOT NULL,
            min_rr DOUBLE PRECISION NOT NULL,
            total_return_pct DOUBLE PRECISION NOT NULL,
            max_drawdown_pct DOUBLE PRECISION NOT NULL,
            sharpe_like DOUBLE PRECISION NOT NULL,
            fitness DOUBLE PRECISION NOT NULL,
            status VARCHAR(50) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT unique_strategy_opt UNIQUE (timestamp, min_confluence, risk_per_trade_pct, recency_bars, min_rr)
        );
        """
    )
    logger.info("Database tablosu kontrol edildi/olusturuldu.")


async def sync_tsv_to_supabase(tsv_path: Path, db_url: str) -> None:
    """TSV dosyasindaki verileri okur ve Supabase'e yazar."""
    if not tsv_path.exists():
        logger.warning("TSV dosyasi bulunamadi: %s", tsv_path)
        return

    logger.info("TSV dosyasi okunuyor: %s", tsv_path)
    rows_to_insert = []
    
    with open(tsv_path, encoding="utf-8") as f:
        header = f.readline().strip().split("\t")
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 10:
                continue
            
            try:
                # TSV format: timestamp min_confluence risk_per_trade_pct recency_bars min_rr total_return_pct max_drawdown_pct sharpe_like fitness status
                dt = datetime.datetime.fromisoformat(parts[0])
                min_conf = int(parts[1])
                risk = float(parts[2])
                recency = int(parts[3])
                min_rr = float(parts[4])
                total_ret = float(parts[5])
                max_dd = float(parts[6])
                sharpe = float(parts[7])
                fitness = float(parts[8])
                status = parts[9]
                
                rows_to_insert.append((
                    dt, min_conf, risk, recency, min_rr,
                    total_ret, max_dd, sharpe, fitness, status
                ))
            except Exception as e:
                logger.error("Satir parse edilemedi: %s | Hata: %s", line.strip(), e)

    if not rows_to_insert:
        logger.info("Senkronize edilecek gecerli veri bulunamadi.")
        return

    logger.info("%d adet kayit Supabase'e gonderiliyor...", len(rows_to_insert))
    
    try:
        conn = await asyncpg.connect(db_url)
        try:
            await create_table_if_not_exists(conn)
            
            # Upsert mantigi ile verileri tek tek veya batch olarak ekle
            success_count = 0
            for row in rows_to_insert:
                try:
                    await conn.execute(
                        """
                        INSERT INTO strategy_optimization_results (
                            timestamp, min_confluence, risk_per_trade_pct, recency_bars, min_rr,
                            total_return_pct, max_drawdown_pct, sharpe_like, fitness, status
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT ON CONSTRAINT unique_strategy_opt DO NOTHING
                        """,
                        *row
                    )
                    success_count += 1
                except Exception as e:
                    logger.warning("Kayit eklenirken hata (geciliyor): %s", e)
            
            logger.info("Senkronizasyon tamamlandi. %d/%d yeni kayit eklendi.", success_count, len(rows_to_insert))
        finally:
            await conn.close()
    except Exception as e:
        logger.error("Supabase baglantisinda veya isleminde hata olustu: %s", e)


async def main() -> None:
    load_dotenv()
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL .env icinde bulunamadi! Cikiliyor.")
        sys.exit(1)
        
    tsv_path = ROOT / "reports" / "optimization" / "results.tsv"
    await sync_tsv_to_supabase(tsv_path, db_url)


if __name__ == "__main__":
    asyncio.run(main())
