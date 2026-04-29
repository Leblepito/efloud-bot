#!/usr/bin/env python3
"""
Efloud SMC Trade Bot v2.1 — Live Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tam sistem:
  • SafeOrchestrator — 7 katmanlı analiz + güvenlik
  • Binance CCXT — data + order execution
  • Circuit breaker — daily/weekly loss, consecutive loss
  • Regime detector — trending/ranging/volatile
  • Position guards — size/exposure/SL distance
  • State persistence — crash recovery
  • MainnetGuard — gerçek para koruması

Kullanım:
  python main.py              # config.yaml kullan
  python main.py my_cfg.yaml  # özel config

Environment:
  BINANCE_API_KEY             # API key (config'den daha öncelikli)
  BINANCE_API_SECRET          # API secret
  EFLOUD_ALLOW_MAINNET=1      # Mainnet LIVE için zorunlu
"""

import yaml
import time
import logging
import logging.handlers
import sys
import os
import signal as sys_signal
from pathlib import Path
from datetime import datetime, timezone

from engine import SafeOrchestrator
from engine.safety import (
    MainnetGuard, mask_secret, retry_with_backoff,
    RateLimiter, validate_kline_integrity,
)
from engine.universe import SymbolUniverse
from engine.permissions import PermissionManager
from engine.notifications import NotificationManager
from exchange import BinanceClient, OrderManager


# ═══════════════════════════════════════════════
# .ENV LOADER (no external dependency)
# ═══════════════════════════════════════════════

def load_dotenv(path: str = ".env") -> int:
    """
    Basit .env dosya yükleyici. python-dotenv gerektirmez.
    Format: KEY=VALUE, # ile başlayan satırlar yorum.
    Returns: yüklenen değişken sayısı.
    """
    p = Path(path)
    if not p.exists():
        return 0
    count = 0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Sadece ayarlanmamışsa yükle (env zaten set'liyse override etme)
            if key and key not in os.environ:
                os.environ[key] = value
                count += 1
    except Exception as e:
        print(f"Warning: failed to load .env: {e}", file=sys.stderr)
    return count


# ═══════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════

def setup_logging(level: str = "INFO", log_file: str = "efloud_bot.log",
                    max_bytes: int = 50 * 1024 * 1024, backup_count: int = 5):
    """Rotating file handler + stdout."""
    fmt = "%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for h in list(root.handlers):
        root.removeHandler(h)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count,
            encoding="utf-8"
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)


# ═══════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════

def load_config(path: str = "config.yaml") -> dict:
    if not Path(path).exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_credentials(cfg: dict) -> tuple:
    """Env var > config'deki değer."""
    ex = cfg.get("exchange", {})
    api_key = os.environ.get("BINANCE_API_KEY") or ex.get("api_key") or ""
    api_secret = os.environ.get("BINANCE_API_SECRET") or ex.get("api_secret") or ""
    return api_key, api_secret


def print_banner(cfg: dict, api_key: str, symbols: list = None):
    dry = "DRY RUN" if cfg["operation"]["dry_run"] else "LIVE"
    net = "TESTNET" if cfg["exchange"]["testnet"] else "MAINNET"
    watch = " (watch only)" if cfg["operation"].get("watch_only") else ""
    sym_str = ", ".join(symbols) if symbols else "[resolved at startup]"
    if len(sym_str) > 50:
        sym_str = sym_str[:47] + "..."
    chain = f'{cfg["timeframes"]["entry"]} → {cfg["timeframes"]["mtf"]} → {cfg["timeframes"]["htf"]}'
    mode = f"{dry} | {net}{watch}"

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   EFLOUD SMC TRADE BOT v2.1                                  ║")
    print(f"║   Mode:    {mode:<50}║")
    print(f"║   Symbols: {sym_str:<50}║")
    print(f"║   Chain:   {chain:<50}║")
    print(f"║   API key: {mask_secret(api_key):<50}║")
    print(f"║   Min Conf: {cfg['risk']['min_confluence']}/100 | Min R:R: {cfg['risk']['min_rr']} | "
          f"Risk: {cfg['risk']['risk_per_trade_pct']}%{'':>9}║")
    print("╚══════════════════════════════════════════════════════════════╝")


# ═══════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════

@retry_with_backoff(max_attempts=4, base_delay=2.0, max_delay=30.0)
def safe_fetch_ohlcv(client: BinanceClient, symbol: str,
                      timeframe: str, limit: int = 500):
    """Retry wrapper'lı kline fetch."""
    df = client.fetch_ohlcv(symbol, timeframe, limit)
    validate_kline_integrity(df)
    return df


# ═══════════════════════════════════════════════
# CYCLE
# ═══════════════════════════════════════════════

def run_cycle(orch: SafeOrchestrator, client: BinanceClient,
                order_mgr: OrderManager, rate_limiter: RateLimiter,
                universe: SymbolUniverse, cfg: dict):
    """Tüm symbol universe'ü analiz et."""
    log = logging.getLogger("efloud.main")
    symbols = universe.resolve()
    scan_mode = cfg["operation"].get("symbol_scan_mode", "sequential")

    log.info(f"📡 Watchlist ({len(symbols)} symbols): {', '.join(symbols)}")

    if scan_mode == "parallel":
        _scan_parallel(symbols, orch, client, order_mgr, rate_limiter, cfg)
    else:
        _scan_sequential(symbols, orch, client, order_mgr, rate_limiter, cfg)

    # Exchange-side position check
    if order_mgr.positions and not cfg["operation"]["dry_run"]:
        order_mgr.check_positions()


def _scan_sequential(symbols, orch, client, order_mgr, rate_limiter, cfg):
    """Symbol'ları tek tek işle — rate limit güvenli."""
    log = logging.getLogger("efloud.main")
    min_gap = cfg["safety"].get("min_seconds_between_symbol_fetches", 1.0)

    for i, symbol in enumerate(symbols, 1):
        log.info(f"━━━ [{i}/{len(symbols)}] {symbol} ━━━")
        _scan_one(symbol, orch, client, order_mgr, rate_limiter, cfg)
        if i < len(symbols):
            time.sleep(min_gap)


def _scan_parallel(symbols, orch, client, order_mgr, rate_limiter, cfg):
    """Thread pool ile paralel işle — dikkatli API yükü."""
    import concurrent.futures
    log = logging.getLogger("efloud.main")
    workers = min(cfg["operation"].get("parallel_workers", 3), len(symbols))

    def task(sym):
        try:
            _scan_one(sym, orch, client, order_mgr, rate_limiter, cfg)
        except Exception as e:
            log.error(f"[{sym}] scan failed: {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(task, symbols))


def _scan_one(symbol, orch, client, order_mgr, rate_limiter, cfg):
    """Tek sembol için cycle - updated for permission handling."""
    log = logging.getLogger("efloud.main")

    # NEW: Check symbol permissions if using new system
    if hasattr(orch, 'permission_manager') and orch.permission_manager:
        permissions = orch.get_symbol_permissions()
        symbol_permission = permissions.get(symbol, 'readonly')

        if symbol_permission == 'readonly':
            log.debug(f"[{symbol}] Read-only symbol - analysis only")
    else:
        symbol_permission = 'tradeable'  # Legacy mode

    tf = cfg["timeframes"]
    limit = tf.get("kline_limit", 500)

    rate_limiter.acquire(weight=4)

    try:
        df_htf = safe_fetch_ohlcv(client, symbol, tf["htf"], limit)
        df_mtf = safe_fetch_ohlcv(client, symbol, tf["mtf"], limit)
        df_entry = safe_fetch_ohlcv(client, symbol, tf["entry"], limit)
        df_daily = None
        try:
            df_daily = safe_fetch_ohlcv(client, symbol, "1d", 100)
        except Exception as e:
            log.warning(f"[{symbol}] Daily data unavailable: {e}")
    except Exception as e:
        log.error(f"[{symbol}] Data fetch failed: {e}")
        return

    balance = None
    if not cfg["operation"]["dry_run"]:
        try:
            balance = client.get_balance()
        except Exception as e:
            log.warning(f"[{symbol}] Balance fetch failed: {e}")

    try:
        result = orch.run_cycle(
            symbol=symbol,
            df_htf=df_htf, df_mtf=df_mtf, df_entry=df_entry,
            df_daily=df_daily, balance=balance,
        )
    except Exception as e:
        log.error(f"[{symbol}] Orchestrator cycle failed: {e}", exc_info=True)
        return

    log.info(
        f"📊 [{symbol}] Price=${result.current_price:,.2f} | "
        f"Bias={result.htf_bias} | Regime={result.regime} | "
        f"Breaker={result.breaker_state} | CanTrade={result.can_trade} | "
        f"Permission={symbol_permission}"
    )

    # NEW: Handle read-only signals
    if symbol_permission == 'readonly' and hasattr(result, 'signal_data') and result.signal_data:
        orch.send_readonly_signal(symbol, result.signal_data)

    if result.actions_taken:
        log.info(f"🎬 [{symbol}] Actions: {result.actions_taken}")

    # Only sync orders for tradeable symbols
    if not cfg["operation"]["dry_run"] and symbol_permission == 'tradeable':
        sync_orders(orch, order_mgr, symbol, log)

    save_report(result, cfg.get("operation", {}).get("reports_dir", "./reports"))


def sync_orders(orch: SafeOrchestrator, order_mgr: OrderManager,
                 symbol: str, log):
    """Orchestrator'daki yeni pozisyonları gerçek order'a çevir."""
    for pos in orch.lifecycle.open_positions(symbol):
        already = any(p.symbol == pos.symbol and
                       p.direction == pos.direction and
                       abs(p.entry - pos.avg_entry_price) < 0.01
                       for p in order_mgr.positions)
        if already:
            continue
        log.info(f"📤 Submitting real order: {pos.direction} {pos.symbol} "
                 f"@ {pos.avg_entry_price:.4f}")
        order_mgr.open_position(
            symbol=pos.symbol, direction=pos.direction,
            size=pos.remaining_size,
            entry=pos.avg_entry_price,
            sl=pos.sl, tp1=pos.tp1, tp2=pos.tp2,
        )


def save_report(result, reports_dir: str):
    """Her cycle'ın markdown raporunu kaydet (journaling)."""
    try:
        Path(reports_dir).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = f"{result.symbol.replace('/', '')}_{result.timeframe}_{ts}.md"
        (Path(reports_dir) / fname).write_text(result.report_md, encoding="utf-8")
    except Exception as e:
        logging.getLogger("efloud.main").warning(f"Report save failed: {e}")


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════

def setup_orchestrator_with_client(cfg: dict, client, state_dir: str) -> SafeOrchestrator:
    """
    Setup SafeOrchestrator with integrated risk management and permission detection.
    """
    log = logging.getLogger("efloud.main")

    # Initialize orchestrator
    orch = SafeOrchestrator(cfg, state_dir=state_dir)

    # Setup permission manager with real client if using new risk system
    risk_config = cfg.get('risk', {})
    if risk_config.get('position_size_calculation') == 'reverse_from_risk':
        log.info("🔧 Setting up integrated permission detection...")
        orch._setup_permission_manager(client)

        # Log permission results
        try:
            tradeable = orch.permission_manager.get_tradeable_symbols() if orch.permission_manager else []
            readonly = orch.permission_manager.get_readonly_symbols() if orch.permission_manager else []
            log.info(f"📊 Permissions detected: {len(tradeable)} tradeable, {len(readonly)} readonly")

            if tradeable:
                log.info(f"✅ Tradeable: {', '.join(tradeable)}")
            if readonly:
                log.info(f"📖 Read-only: {', '.join(readonly)}")
        except (TypeError, AttributeError):
            # Handle case when permission_manager is a Mock or doesn't have expected methods
            log.info("📊 Permission manager setup completed")

    return orch


class GracefulShutdown:
    def __init__(self):
        self.stop = False
        sys_signal.signal(sys_signal.SIGINT, self._handle)
        sys_signal.signal(sys_signal.SIGTERM, self._handle)

    def _handle(self, signum, frame):
        logging.getLogger("efloud.main").info(
            f"Received signal {signum}, shutting down gracefully...")
        self.stop = True


def main():
    # .env dosyasını otomatik yükle (varsa) — BINANCE_API_KEY ve _SECRET'ı set eder
    loaded = load_dotenv()
    if loaded > 0:
        print(f"📄 Loaded {loaded} variables from .env")

    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"

    try:
        cfg = load_config(cfg_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Hint: Copy config.yaml from the repo and customize it.", file=sys.stderr)
        sys.exit(1)

    setup_logging(
        level=cfg["operation"].get("log_level", "INFO"),
        log_file=cfg["operation"].get("log_file", "efloud_bot.log"),
    )
    log = logging.getLogger("efloud.main")

    api_key, api_secret = resolve_credentials(cfg)
    # Banner'ı önce göster (symbols henüz resolve edilmeden)
    print_banner(cfg, api_key)

    # Mainnet Guard
    if not MainnetGuard.check(
        testnet=cfg["exchange"]["testnet"],
        dry_run=cfg["operation"]["dry_run"],
        interactive=True,
    ):
        log.error("Mainnet guard blocked startup. Exiting.")
        sys.exit(1)

    # Credentials required for live mode
    if not cfg["operation"]["dry_run"] and (not api_key or not api_secret):
        log.error("Live mode requires BINANCE_API_KEY and BINANCE_API_SECRET "
                   "(env var or config)")
        sys.exit(1)

    # Exchange client
    ex_cfg = cfg["exchange"]
    client = BinanceClient(
        api_key=api_key, api_secret=api_secret,
        testnet=ex_cfg["testnet"],
        market_type=ex_cfg["market_type"],
    )

    # Symbol universe — önce resolve et ki leverage vs. kurabilelim
    universe = SymbolUniverse(cfg, client=client)
    initial_syms = universe.resolve(force_refresh=True)
    log.info(f"📡 Initial watchlist ({len(initial_syms)}): {', '.join(initial_syms)}")

    # ── Permission detection (Binance API yetki kontrolü) ──
    permission_mgr = None
    notif_mgr = NotificationManager(channels=['terminal', 'log'])
    if api_key and not cfg["operation"].get("dry_run", True):
        # Sadece live trading'de detect et — dry_run'da gerek yok
        try:
            permission_mgr = PermissionManager(client)
            estimated_pos = cfg["safety"].get("starting_balance", 1000) * \
                            (cfg["safety"].get("max_position_notional_pct", 3.0) / 100) * \
                            ex_cfg.get("leverage", 3)
            permission_mgr.detect_all(initial_syms, estimated_notional=estimated_pos)
        except Exception as e:
            log.warning(f"Permission detection failed: {e}. Treating all as tradeable.")
            permission_mgr = None
    else:
        log.info("ℹ️  Dry run veya read-only key: permission detection atlandı")

    # Set leverage for futures trading
    if ex_cfg["market_type"] == "futures" and api_key:
        for sym in initial_syms:
            try:
                client.set_leverage(sym, ex_cfg.get("leverage", 3))

                # NEW: Set isolated margin mode for safety
                if ex_cfg.get("margin_mode") == "isolated":
                    client.set_margin_mode(sym, "ISOLATED")

            except Exception as e:
                log.warning(f"Leverage/margin setup failed for {sym}: {e}")

    # SafeOrchestrator (tüm güvenlik + analiz katmanları)
    state_dir = cfg["operation"].get("state_dir", "./state")

    # NEW: Use integrated setup function instead of direct SafeOrchestrator()
    orch = setup_orchestrator_with_client(cfg, client, state_dir)

    order_mgr = OrderManager(client, dry_run=cfg["operation"]["dry_run"])
    rate_limiter = RateLimiter(max_per_minute=1000)

    shutdown = GracefulShutdown()
    interval = cfg["operation"]["check_interval_sec"]
    log.info(f"🚀 Starting main loop — interval={interval}s")

    cycle_count = 0
    while not shutdown.stop:
        cycle_start = time.time()
        cycle_count += 1
        try:
            log.info(f"═══ Cycle #{cycle_count} ═══")
            run_cycle(orch, client, order_mgr, rate_limiter, universe, cfg)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"Cycle error: {e}", exc_info=True)

        elapsed = time.time() - cycle_start
        sleep_time = max(0, interval - elapsed)
        log.info(f"Cycle took {elapsed:.1f}s, sleeping {sleep_time:.0f}s...\n")

        for _ in range(int(sleep_time)):
            if shutdown.stop:
                break
            time.sleep(1)

    log.info("Shutdown complete. Final state persisted.")
    try:
        orch._persist_state()
    except Exception:
        pass


if __name__ == "__main__":
    main()
