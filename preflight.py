"""
Pre-flight check — Mainnet API key/yetki doğrulaması.
Order ATMAZ. Sadece read-only API çağrıları yapar.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from main import load_dotenv
load_dotenv()

import os
import ccxt

ALLOW = os.environ.get("EFLOUD_ALLOW_MAINNET") == "1"
KEY = os.environ.get("BINANCE_API_KEY", "")
SEC = os.environ.get("BINANCE_API_SECRET", "")

print("=" * 60)
print("  PRE-FLIGHT CHECK — Binance Mainnet Futures")
print("=" * 60)

if not KEY or not SEC:
    print("\n❌ FAIL: BINANCE_API_KEY veya BINANCE_API_SECRET set değil")
    sys.exit(1)
if not ALLOW:
    print("\n❌ FAIL: EFLOUD_ALLOW_MAINNET=1 değil")
    sys.exit(1)

print(f"  Key:    set ({len(KEY)} char)")
print(f"  Secret: set ({len(SEC)} char)")
print(f"  ALLOW_MAINNET: 1\n")

ex = ccxt.binance({
    "apiKey": KEY,
    "secret": SEC,
    "enableRateLimit": True,
    "options": {"defaultType": "future"},
})

# 1. Public ping
try:
    server_time = ex.fetch_time()
    print(f"  [1/4] Mainnet bağlantı: ✅ (server time OK)")
except Exception as e:
    print(f"  [1/4] Mainnet bağlantı: ❌ {type(e).__name__}: {e}")
    sys.exit(1)

# 2. Account info (key validity + permissions)
try:
    info = ex.fapiPrivateV2GetAccount()
    can_trade = info.get("canTrade", False)
    can_deposit = info.get("canDeposit", False)
    can_withdraw = info.get("canWithdraw", False)
    print(f"  [2/4] API auth: ✅")
    print(f"        canTrade:    {can_trade} {'✅' if can_trade else '❌ Futures trading kapalı!'}")
    print(f"        canDeposit:  {can_deposit}")
    print(f"        canWithdraw: {can_withdraw} {'⚠️ AÇIK — kapatman önerilir' if can_withdraw else '✅ kapalı (güvenli)'}")
    if not can_trade:
        print("\n❌ FAIL: Futures trade yetkisi olmadan bot order veremez. Bu kritik blocker'dır.")
        sys.exit(1)
    if can_withdraw:
        print("\n⚠️  Çekim yetkisi açık — ŞİDDETLE kapatılması önerilir (key sızarsa fon kaybı).")
except Exception as e:
    print(f"  [2/4] API auth: ❌ {type(e).__name__}: {e}")
    print("        İhtimaller: 1) yanlış key, 2) IP whitelist, 3) futures yetkisi yok")
    sys.exit(1)

# 3. Balance (sadece var/yok kontrol)
try:
    bal = ex.fetch_balance(params={"type": "future"})
    usdt = bal.get("USDT", {})
    free = float(usdt.get("free", 0))
    total = float(usdt.get("total", 0))
    if total < 10:
        print(f"  [3/4] Futures cüzdan: ❌ bakiye çok düşük (${total:.2f} USDT)")
        print("        Binance Spot → Futures'a en az $50-200 transfer et")
        sys.exit(1)
    elif total > 500:
        print(f"  [3/4] Futures cüzdan: ⚠️ bakiye yüksek (${total:.2f} USDT)")
        print("        Micro config $100 için optimize — fazlasını Spot'a geri al")
    else:
        print(f"  [3/4] Futures cüzdan: ✅ ${total:.2f} USDT (free: ${free:.2f})")
except Exception as e:
    print(f"  [3/4] Futures cüzdan: ❌ {type(e).__name__}: {e}")
    sys.exit(1)

# 4. Position mode
try:
    pos_mode = ex.fapiPrivateGetPositionSideDual()
    is_hedge = pos_mode.get("dualSidePosition", False)
    if is_hedge:
        print(f"  [4/4] Position mode: ⚠️ HEDGE — bot ONE-WAY mode için tasarlandı")
        print("        Binance → Futures Settings → Position Mode → One-way")
    else:
        print(f"  [4/4] Position mode: ✅ ONE-WAY")
except Exception as e:
    print(f"  [4/4] Position mode: ⚠️ kontrol edilemedi ({e})")

print("\n" + "=" * 60)
print("  ✅ Pre-flight OK — bot başlatılabilir")
print("=" * 60)
print("\nKomut:")
print('  python main.py configs/config.phase2_micro.yaml')
