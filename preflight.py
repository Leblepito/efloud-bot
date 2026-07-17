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
import yaml


def _fix_win_console():
    """Force UTF-8 on the Windows console (for the emoji output). Only relevant
    when run as a script — kept out of import so pytest's capture isn't broken
    by detaching stdout/stderr at import time."""
    if sys.platform == "win32":
        try:
            import codecs
            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
            sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
        except Exception:
            pass


def _parse_dual_side(value) -> bool:
    """F14 (2026-07-11 spec): Binance dualSidePosition string "true"/"false"
    dönebilir (bkz. exchange/__init__.py set_position_mode notu) — bool'a
    normalize edilmezse hedge-mode karşılaştırması her zaman mismatch verir."""
    return str(value).strip().lower() == "true"


def evaluate_flat_book(mode_change_needed: bool, open_positions: int,
                       open_orders: int) -> tuple:
    """Decide whether preflight may proceed given a pending mode change.

    Binance rejects a margin-type / position-mode change while any position or
    order is open. When such a change is pending and the book is NOT flat,
    preflight must fail so the operator cannot half-apply the switch (PR A).
    Returns (ok, message).
    """
    if mode_change_needed and (open_positions > 0 or open_orders > 0):
        return False, (
            f"FAIL: margin/position-mode change is pending but the book is NOT "
            f"flat ({open_positions} open positions, {open_orders} open orders). "
            f"Close all positions and cancel all orders, then restart."
        )
    return True, "Flat-book gate OK"


def count_open_book(ex) -> tuple:
    """Return (n_positions, n_orders, regular_ok, algo_ok) for the flat-book gate.

    BUG (2026-07-08 debug session): this used to be inlined in main() as a
    bare `ex.fetch_open_orders()` call, which only sees REGULAR orders.
    Binance's SL/TP are placed as server-side ALGO orders (STOP_MARKET /
    TAKE_PROFIT_MARKET, routed through /fapi/v1/algo/*) and are invisible to
    fetch_open_orders — the exact same gap the reconcile path already had to
    patch (exchange/__init__.py, 2026-05-09 LTC/ADA incident:
    fapiPrivateGetOpenAlgoOrders). A leftover algo SL/TP from a previously
    closed position made preflight report "0 open orders" (flat book) while
    Binance's own dualSidePosition change still rejected with the book
    genuinely not flat — the operator saw a false "safe to start" green light.

    regular_ok=False (fail-open, advisory only) on a read error for
    positions/regular-orders — mirrors the existing fail-open behavior in
    main(): a query failure must not block the operator, Binance's own
    rejection is the authoritative guard. algo_ok=False means the algo-order
    count could not be confirmed (n_orders may be an UNDERCOUNT) even though
    regular_ok is True — the caller must surface this distinctly rather than
    reporting a confident "flat" when it isn't verified.
    """
    try:
        positions = [p for p in ex.fetch_positions() if float(p.get("contracts", 0) or 0) > 0]
        open_orders = ex.fetch_open_orders()
        n_pos, n_ord = len(positions), len(open_orders)
    except Exception:
        return 0, 0, False, False
    try:
        algo_orders = ex.fapiPrivateGetOpenAlgoOrders({})
        n_ord += len(algo_orders)
    except Exception:
        return n_pos, n_ord, True, False
    return n_pos, n_ord, True, True


def main():
    _fix_win_console()
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
        "options": {
            "defaultType": "future",
            # CCXT ≥4.5 drift fix (2026-07-17): symbol'süz fetch_open_orders
            # (count_open_book) hem acknowledge hatası fırlatıyor hem de
            # SPOT'a yönleniyordu → flat-book gate'i kalıcı "sorgulanamadı"
            # düşüp mode-change korumasını devre dışı bırakıyordu. Method-
            # scoped override USDM routing + yeni acknowledge adı; eski
            # ccxt'te no-op.
            "warnOnFetchOpenOrdersWithoutSymbol": False,
            "fetchOpenOrders": {
                "type": "swap",
                "subType": "linear",
                "warnWithoutSymbol": False,
            },
        },
    })

    # 1. Public ping
    try:
        server_time = ex.fetch_time()
        print(f"  [1/5] Mainnet bağlantı: ✅ (server time OK)")
    except Exception as e:
        print(f"  [1/5] Mainnet bağlantı: ❌ {type(e).__name__}: {e}")
        sys.exit(1)

    # 2. Account info (key validity + permissions)
    try:
        info = ex.fapiPrivateV2GetAccount()
        can_trade = info.get("canTrade", False)
        can_deposit = info.get("canDeposit", False)
        can_withdraw = info.get("canWithdraw", False)
        print(f"  [2/5] API auth: ✅")
        print(f"        canTrade:    {can_trade} {'✅' if can_trade else '❌ Futures trading kapalı!'}")
        print(f"        canDeposit:  {can_deposit}")
        print(f"        canWithdraw: {can_withdraw} {'⚠️ AÇIK — kapatman önerilir' if can_withdraw else '✅ kapalı (güvenli)'}")
        if not can_trade:
            print("\n❌ FAIL: Futures trade yetkisi olmadan bot order veremez. Bu kritik blocker'dır.")
            sys.exit(1)
        if can_withdraw:
            print("\n⚠️  Çekim yetkisi açık — ŞİDDETLE kapatılması önerilir (key sızarsa fon kaybı).")
    except Exception as e:
        print(f"  [2/5] API auth: ❌ {type(e).__name__}: {e}")
        print("        İhtimaller: 1) yanlış key, 2) IP whitelist, 3) futures yetkisi yok")
        sys.exit(1)

    # Load active config if specified in environment
    # F3.6: default to the real production config (the old micro path did not
    # exist → except:pass below → bogus starting_balance=100 band).
    config_path = os.environ.get("EFLOUD_CONFIG_PATH", "configs/config.phase2_1k.yaml")
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
            print(f"  [3/5] Futures cüzdan: ❌ bakiye düşük (${total:.2f} USDT)")
            print(f"        Gerekli olan bakiye en az: ${min_balance:.2f} USDT (starting_balance={starting_balance})")
            sys.exit(1)
        elif total > max_balance:
            print(f"  [3/5] Futures cüzdan: ⚠️ bakiye yüksek (${total:.2f} USDT)")
            print(f"        Config {starting_balance} için optimize — fazlasını Spot'a geri al")
        else:
            print(f"  [3/5] Futures cüzdan: ✅ ${total:.2f} USDT (free: ${free:.2f})")
    except Exception as e:
        print(f"  [3/5] Futures cüzdan: ❌ {type(e).__name__}: {e}")
        sys.exit(1)

    # 4. Position mode
    is_hedge = hedge_mode
    try:
        pos_mode = ex.fapiPrivateGetPositionSideDual()
        is_hedge = _parse_dual_side(pos_mode.get("dualSidePosition", False))
        if is_hedge == hedge_mode:
            print(f"  [4/5] Position mode: ✅ {'HEDGE' if is_hedge else 'ONE-WAY'}")
        else:
            if hedge_mode:
                print(f"  [4/5] Position mode: ⚠️ ONE-WAY — Config'de HEDGE_MODE aktif, fakat hesap One-way modda. "
                      f"Bot başlatıldığında otomatik olarak HEDGE moda geçmeye çalışacaktır. "
                      f"(ÖNEMLİ: Hesapta açık emir veya pozisyon varsa geçiş başarısız olur!)")
            else:
                print(f"  [4/5] Position mode: ⚠️ HEDGE — Config'de ONE-WAY aktif, fakat hesap Hedge modda. "
                      f"Bot başlatıldığında otomatik olarak ONE-WAY moda geçmeye çalışacaktır. "
                      f"(ÖNEMLİ: Hesapta açık emir veya pozisyon varsa geçiş başarısız olur!)")
    except Exception as e:
        print(f"  [4/5] Position mode: ⚠️ kontrol edilemedi ({e})")

    # 5. Flat-book gate — a pending mode change requires a flat account.
    #    is_hedge (current exchange state) vs hedge_mode (desired config) — if
    #    they differ, a position-mode switch will be attempted at startup, which
    #    Binance rejects unless the book is flat.
    mode_change_needed = (is_hedge != hedge_mode)
    n_pos, n_ord, regular_ok, algo_ok = count_open_book(ex)
    if not regular_ok:
        # Fail-open: a read error must not block the operator. This is only an
        # ADVISORY preflight check — Binance's own rejection + the startup abort
        # in _enforce_margin_setup are the authoritative guards. Treat a ⚠️ here
        # as inconclusive and verify flatness manually (runbook step 4).
        print(f"  [5/5] Flat-book gate: ⚠️ pozisyon/emir sorgulanamadı — manuel doğrula")
        mode_change_needed = False
    elif not algo_ok:
        # Regular orders/positions counted fine, but the algo-order (SL/TP)
        # count is UNCONFIRMED — n_ord may be an undercount. A clean "0
        # orders" here would be a false green light (see count_open_book
        # docstring), so this must not report as a confident flat book.
        print(f"  [5/5] Flat-book gate: ⚠️ algo (SL/TP) emirleri doğrulanamadı — "
              f"{n_ord} normal emir görüldü ama SAYIM EKSİK OLABİLİR. "
              f"Binance uygulamasından/TradingView'dan manuel kontrol et.")
        mode_change_needed = False
    ok, msg = evaluate_flat_book(mode_change_needed, n_pos, n_ord)
    if not ok:
        print(f"  [5/5] Flat-book gate: ❌ {msg}")
        sys.exit(1)
    print(f"  [5/5] Flat-book gate: ✅ ({n_pos} pozisyon, {n_ord} emir, "
          f"mode_change_needed={mode_change_needed})")

    print("\n" + "=" * 60)
    print("  ✅ Pre-flight OK — bot başlatılabilir")
    print("=" * 60)
    print("\nKomut:")
    print(f"  python main.py {config_path}")


if __name__ == "__main__":
    main()
