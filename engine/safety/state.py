"""
State Persistence — Crash Recovery
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Bot her state değişikliğinde JSON'a yazar.
Startup'ta state yükler, exchange ile reconcile eder.

Kaydedilen:
  - Açık pozisyonlar + entries + exits
  - Aktif senaryolar
  - Circuit breaker durumu
  - Son cycle timestamp

Atomik yazım: önce .tmp'ye yaz, sonra rename (crash-safe).
"""

import json
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any
import logging

log = logging.getLogger("efloud.state")


class StateStore:
    """Atomik dosya tabanlı state persistence."""

    def __init__(self, state_dir: str = "./state"):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: Any) -> bool:
        """Atomik yaz — önce tmp, sonra rename."""
        path = self.dir / f"{key}.json"
        tmp_path = path.with_suffix(".json.tmp")

        try:
            payload = {
                "saved_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "data": data,
            }
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=self._serialize)
                f.flush()
                os.fsync(f.fileno())

            # Atomik rename
            shutil.move(str(tmp_path), str(path))
            return True
        except Exception as e:
            log.error(f"State save failed for {key}: {e}")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return False

    def load(self, key: str) -> Optional[Any]:
        """State yükle."""
        path = self.dir / f"{key}.json"
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload.get("data")
        except Exception as e:
            log.error(f"State load failed for {key}: {e}")
            # Corrupted file'ı backup'a taşı
            backup = path.with_suffix(f".corrupted.{int(datetime.now(timezone.utc).replace(tzinfo=None).timestamp())}")
            try:
                shutil.move(str(path), str(backup))
                log.warning(f"Corrupted state moved to {backup}")
            except Exception:
                pass
            return None

    def saved_at(self, key: str) -> Optional[datetime]:
        """State dosyası ne zaman yazıldı?"""
        path = self.dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                payload = json.load(f)
            return datetime.fromisoformat(payload["saved_at"])
        except Exception:
            return None

    def delete(self, key: str):
        path = self.dir / f"{key}.json"
        if path.exists():
            path.unlink()

    def list_keys(self) -> list:
        return [p.stem for p in self.dir.glob("*.json")]

    @staticmethod
    def _serialize(obj):
        """Custom JSON serialization."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        if hasattr(obj, "value"):  # Enum
            return obj.value
        return str(obj)


class ReconciliationError(Exception):
    """Bot state ile exchange state uyuşmadığında."""
    pass


def reconcile_positions(bot_positions: list, exchange_positions: list,
                        symbol: str) -> dict:
    """
    Bot'un bildiği pozisyonlarla exchange'deki gerçek pozisyonları karşılaştırır.

    Args:
        bot_positions: StateStore'dan yüklenen pozisyonlar
        exchange_positions: Exchange API'den çekilen açık pozisyonlar
        symbol: İncelenecek sembol

    Returns:
        dict: {
            "matched": [...],          # Her iki tarafta da var, eşleşiyor
            "bot_only": [...],         # Bot'ta var, exchange'de yok (kapanmış?)
            "exchange_only": [...],    # Exchange'de var, bot bilmiyor (riskli!)
            "size_mismatch": [...],    # İkisinde de var ama boyutlar farklı
        }
    """
    result = {
        "matched": [],
        "bot_only": [],
        "exchange_only": [],
        "size_mismatch": [],
    }

    bot_open = [p for p in bot_positions
                if p.get("symbol") == symbol and p.get("remaining_size", 0) > 0]

    ex_pos = [p for p in exchange_positions
              if p.get("symbol") == symbol and float(p.get("contracts", 0)) > 0]

    # Match by direction
    for bp in bot_open:
        bot_dir = bp.get("direction")
        bot_size = float(bp.get("remaining_size", 0))

        matched_ex = None
        for ep in ex_pos:
            # Binance direction: "long" / "short"
            ex_dir_raw = str(ep.get("side", "")).upper()
            ex_dir = "LONG" if ex_dir_raw in ("LONG", "BUY") else "SHORT"
            if ex_dir == bot_dir:
                matched_ex = ep
                break

        if matched_ex is None:
            result["bot_only"].append(bp)
        else:
            ex_size = float(matched_ex.get("contracts", 0))
            # Size tolerance %1
            if abs(ex_size - bot_size) / max(bot_size, 1e-10) > 0.01:
                result["size_mismatch"].append({
                    "bot": bp, "exchange": matched_ex,
                    "diff": ex_size - bot_size
                })
            else:
                result["matched"].append({"bot": bp, "exchange": matched_ex})

    # Exchange'de var ama bot bilmiyor
    matched_ex_ids = {m["exchange"].get("symbol", "") + str(m["exchange"].get("side", ""))
                       for m in result["matched"]}
    matched_ex_ids |= {m["exchange"].get("symbol", "") + str(m["exchange"].get("side", ""))
                       for m in result["size_mismatch"]}

    for ep in ex_pos:
        key = ep.get("symbol", "") + str(ep.get("side", ""))
        if key not in matched_ex_ids:
            result["exchange_only"].append(ep)

    return result
