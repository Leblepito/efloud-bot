import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import yaml
import httpx

def load_env(env_path=".env"):
    p = Path(env_path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

def make_future_client(client=None):
    if client is not None:
        return client
    import ccxt
    return ccxt.binance({
        "apiKey": os.environ.get("BINANCE_API_KEY"),
        "secret": os.environ.get("BINANCE_API_SECRET"),
        "options": {
            "defaultType": "future",
            # position_audit fix (2026-07-04): symbol'süz fetch_open_orders,
            # ccxt'de acknowledge edilmezse ExchangeError FIRLATIR (uyarı değil).
            # Audit bilinçli olarak TÜM emirleri tek çağrıda tarar (2dk cadence,
            # weight bütçesi yeterli) — uyarıyı bilinçli kabul ediyoruz.
            "warnOnFetchOpenOrdersWithoutSymbol": False,
            # CCXT ≥4.5 drift fix (2026-07-17): defaultType='future' artık
            # symbol'süz fetch_open_orders'ı fapi'ye yönlendirmiyor → çağrı
            # SPOT /api/v3/openOrders'a düşüyor ve audit yanlış marketi tarıyor
            # (her açık pozisyon "Bare Position" false-critical üretir). Method-
            # scoped override yalnız fetchOpenOrders'ı USDM'e sabitler; eski
            # ccxt'te davranış değişmez ('warnWithoutSymbol' ≥4.5 adı; üstteki
            # düz key eski sürümler için duruyor).
            "fetchOpenOrders": {
                "type": "swap",
                "subType": "linear",
                "warnWithoutSymbol": False,
            },
        },
    })

def now_utc():
    return datetime.now(timezone.utc)

def load_config(path="config.yaml"):
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def read_state_json(path):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def read_snapshot(path):
    return read_state_json(path)

def resolve_state_dir(cfg=None):
    """Canlı instance'ın state dizini (R-1/R-3 fix, 2026-07-17).

    Öncelik: EFLOUD_STATE_DIR env > cfg operation.state_dir > ./state.
    Canlı bot configs/config.phase2_1k.yaml ile ./state_1k'ya yazar; rutinler
    root config.yaml'ın ./state'ine bakınca breaker/positions'ı HİÇ görmüyordu
    (breaker trip alarmı ölü, position_audit boş ledger'a karşı false drift).
    """
    env = os.environ.get("EFLOUD_STATE_DIR")
    if env:
        return env
    return ((cfg or {}).get("operation", {}) or {}).get("state_dir", "./state")

def unwrap_state(payload):
    """StateStore.save zarfını aç: {"saved_at":…, "data":…} → data.

    Bot state dosyaları (breaker.json, positions.json) StateStore ile yazılır;
    rutinler zarfı açmadan okuyunca `state` gibi alanlar hep default'a
    düşüyordu (R-1/R-3, 2026-07-17). Düz (zarfısız) format geriye-uyumlu.
    """
    if isinstance(payload, dict) and "saved_at" in payload and "data" in payload:
        return payload.get("data") if payload.get("data") is not None else {}
    return payload

def write_snapshot(path, data: dict):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["last_checked"] = now_utc().isoformat()
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def write_report(path, text: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def get_api(path, params=None):
    """GET an authed API endpoint from the local FastAPI server."""
    base_url = os.environ.get("EFLOUD_API_BASE_URL", "http://localhost:8080")
    password = os.environ.get("DASHBOARD_PASSWORD", "")
    
    with httpx.Client(timeout=10.0) as client:
        # First, log in
        login_res = client.post(f"{base_url}/api/login", json={"password": password})
        if login_res.status_code != 200:
            raise Exception(f"API Login failed: {login_res.status_code} - {login_res.text}")
            
        # Make the actual GET request
        res = client.get(f"{base_url}{path}", params=params)
        if res.status_code != 200:
            raise Exception(f"API request {path} failed: {res.status_code} - {res.text}")
        return res.json()

class RoutineResult:
    def __init__(self, name, ok=True, breaches=None, report_path=None, error=None):
        self.name = name
        self.ok = ok
        self.breaches = breaches or []
        self.report_path = report_path
        self.error = error
