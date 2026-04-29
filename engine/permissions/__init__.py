"""
Permission Manager
━━━━━━━━━━━━━━━━━━

Binance API'den trade yetkilerini tespit eder.

Akış:
  1. Bot başlarken: account info çek (canTrade, permissions)
  2. Her sembol için: futures'ta listeli mi, trading aktif mi, min notional uygun mu
  3. Sonuç: tradeable_symbols + readonly_symbols ayrımı
  4. Bot sadece tradeable'lara order atar; readonly için NotificationManager devreye girer

Edge cases:
  - API key sadece-okuma izinli → tüm semboller readonly
  - Sembol Binance'de yok → readonly ve uyarı log
  - Min notional > pozisyon boyutu → readonly (bot ufak pozisyon açamıyor)
"""

import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

log = logging.getLogger("efloud.permissions")


@dataclass
class SymbolPermission:
    symbol: str
    tradeable: bool
    reason: str = ""        # Neden tradeable veya readonly
    min_notional: float = 0
    min_qty: float = 0
    status: str = ""        # Binance status: TRADING, BREAK, vs.


class PermissionManager:
    """API yetkilerini tespit eder ve sembol bazlı filter sağlar."""

    def __init__(self, client):
        """
        client: BinanceClient instance
        """
        self.client = client
        self.permissions: Dict[str, SymbolPermission] = {}
        self.account_can_trade: bool = False
        self._exchange_info_cache = None

    def detect_all(self, symbols: List[str],
                    estimated_notional: float = 30.0) -> Dict[str, SymbolPermission]:
        """
        Tüm semboller için yetki tespiti yap.

        estimated_notional: Bot'un ortalama açacağı pozisyon büyüklüğü (USDT).
                            Min notional kontrolü için kullanılır.
        """
        # 1. Account info çek
        try:
            account = self._fetch_account_info()
            self.account_can_trade = account.get("canTrade", False)
            log.info(f"🔐 Account canTrade: {self.account_can_trade}")
        except Exception as e:
            log.error(f"Account info fetch failed: {e}")
            log.warning("Falling back: assume canTrade=False, all symbols readonly")
            self.account_can_trade = False

        # 2. Exchange info çek (sembol metadata)
        try:
            self._exchange_info_cache = self._fetch_exchange_info()
        except Exception as e:
            log.error(f"Exchange info fetch failed: {e}")
            self._exchange_info_cache = {"symbols": []}

        # 3. Her sembol için kontrol
        for sym in symbols:
            self.permissions[sym] = self._check_symbol(sym, estimated_notional)

        # 4. Özet log
        tradeable = [s for s, p in self.permissions.items() if p.tradeable]
        readonly = [s for s, p in self.permissions.items() if not p.tradeable]
        log.info(f"📋 Permission summary: {len(tradeable)} tradeable, {len(readonly)} readonly")
        if readonly:
            log.info(f"   Readonly: {', '.join(readonly)}")

        return self.permissions

    def _fetch_account_info(self) -> dict:
        """Futures account info."""
        if self.client.market_type == "futures":
            # CCXT method
            try:
                return self.client.exchange.fetch_balance({"type": "future"})
            except Exception:
                # Fallback: privateGetAccount
                return self.client.exchange.fapiPrivateV2GetAccount()
        return self.client.exchange.fetch_balance()

    def _fetch_exchange_info(self) -> dict:
        """Futures exchange info — tüm semboller, filterları, status'ları."""
        if self.client.market_type == "futures":
            return self.client.exchange.fapiPublicGetExchangeinfo()
        return self.client.exchange.publicGetExchangeinfo()

    def _check_symbol(self, symbol: str, estimated_notional: float) -> SymbolPermission:
        """Tek sembol için yetki tespiti."""
        # 1. Account trade yetkisi yok → readonly
        if not self.account_can_trade:
            return SymbolPermission(symbol, False,
                                      reason="Account canTrade=False (read-only API key)")

        # 2. Sembol Binance'de listeli mi?
        # Binance format: BTCUSDT (slashless)
        binance_sym = symbol.replace("/", "")
        sym_info = None
        for s in self._exchange_info_cache.get("symbols", []):
            if s.get("symbol") == binance_sym:
                sym_info = s
                break

        if sym_info is None:
            return SymbolPermission(symbol, False,
                                      reason=f"Symbol not listed on Binance futures",
                                      status="NOT_FOUND")

        # 3. Trading aktif mi?
        status = sym_info.get("status", "UNKNOWN")
        if status != "TRADING":
            return SymbolPermission(symbol, False,
                                      reason=f"Trading status: {status}",
                                      status=status)

        # 4. Min notional ve min qty kontrolü
        min_notional = 0.0
        min_qty = 0.0
        for f in sym_info.get("filters", []):
            ftype = f.get("filterType", "")
            if ftype == "MIN_NOTIONAL":
                min_notional = float(f.get("notional", f.get("minNotional", 0)))
            elif ftype == "LOT_SIZE":
                min_qty = float(f.get("minQty", 0))

        # Estimated notional min'i karşılıyor mu?
        if min_notional > 0 and estimated_notional < min_notional:
            return SymbolPermission(symbol, False,
                                      reason=f"Min notional {min_notional} > "
                                              f"estimated position {estimated_notional}",
                                      min_notional=min_notional,
                                      min_qty=min_qty,
                                      status=status)

        # ✅ Tüm check'ler geçti
        return SymbolPermission(symbol, True,
                                  reason="All checks passed",
                                  min_notional=min_notional,
                                  min_qty=min_qty,
                                  status=status)

    def is_tradeable(self, symbol: str) -> bool:
        """Hızlı erişim: sembol tradeable mi?"""
        perm = self.permissions.get(symbol)
        return perm is not None and perm.tradeable

    def get_tradeable_symbols(self) -> List[str]:
        return [s for s, p in self.permissions.items() if p.tradeable]

    def get_readonly_symbols(self) -> List[str]:
        return [s for s, p in self.permissions.items() if not p.tradeable]
