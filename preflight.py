"""
Pre-flight check — Mainnet API key/yetki doğrulaması.
Order ATMAZ. Sadece read-only API çağrıları yapar.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# Fix Windows console encoding issues
if sys.platform == "win32":
    try:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    except:
        pass

from main import load_dotenv
load_dotenv()

import os
import ccxt
import yaml

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

# Load active config if specified in environment
config_path = os.environ.get("EFLOUD_CONFIG_PATH", "configs/config.phase2_micro.yaml")
starting_balance = 100.0
hedge_mode = False
try:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        starting_balance = float(config.get("safety", {}).get("starting_balance", 100.0))
        hedge_mode = bool(config.get("exchange", {}).get("hedge_mode", False))
except Exception:
    pass

# 3. Balance (sadece var/yok kontrol)
try:
    bal = ex.fetch_balance(params={"type": "future"})
    usdt = bal.get("USDT", {})
    free = float(usdt.get("free", 0))
    total = float(usdt.get("total", 0))
    
    min_balance = max(10.0, starting_balance * 0.8)
    max_balance = starting_balance * 2.5
    
    if total < min_balance:
        print(f"  [3/4] Futures cüzdan: ❌ bakiye düşük (${total:.2f} USDT)")
        print(f"        Gerekli olan bakiye en az: ${min_balance:.2f} USDT (starting_balance={starting_balance})")
        sys.exit(1)
    elif total > max_balance:
        print(f"  [3/4] Futures cüzdan: ⚠️ bakiye yüksek (${total:.2f} USDT)")
        print(f"        Config {starting_balance} için optimize — fazlasını Spot'a geri al")
    else:
        print(f"  [3/4] Futures cüzdan: ✅ ${total:.2f} USDT (free: ${free:.2f})")
except Exception as e:
    print(f"  [3/4] Futures cüzdan: ❌ {type(e).__name__}: {e}")
    sys.exit(1)

# 4. Position mode
try:
    pos_mode = ex.fapiPrivateGetPositionSideDual()
    is_hedge = pos_mode.get("dualSidePosition", False)
    if is_hedge == hedge_mode:
        print(f"  [4/4] Position mode: ✅ {'HEDGE' if is_hedge else 'ONE-WAY'}")
    else:
        if hedge_mode:
            print(f"  [4/4] Position mode: ⚠️ ONE-WAY — Config'de HEDGE_MODE aktif, fakat hesap One-way modda. "
                  f"Bot başlatıldığında otomatik olarak HEDGE moda geçmeye çalışacaktır. "
                  f"(ÖNEMLİ: Hesapta açık emir veya pozisyon varsa geçiş başarısız olur!)")
        else:
            print(f"  [4/4] Position mode: ⚠️ HEDGE — Config'de ONE-WAY aktif, fakat hesap Hedge modda. "
                  f"Bot başlatıldığında otomatik olarak ONE-WAY moda geçmeye çalışacaktır. "
                  f"(ÖNEMLİ: Hesapta açık emir veya pozisyon varsa geçiş başarısız olur!)")
except Exception as e:
    print(f"  [4/4] Position mode: ⚠️ kontrol edilemedi ({e})")

print("\n" + "=" * 60)
print("  ✅ Pre-flight OK — bot başlatılabilir")
print("=" * 60)
print("\nKomut:")
print(f"  python main.py {config_path}")
