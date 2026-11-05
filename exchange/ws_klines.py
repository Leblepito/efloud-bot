"""Binance USDT-M futures kline WebSocket feed (read-only market data).

Faz 1 (T-20261104-11): yalnız VERİ katmanı. Emir/karar yolu bu modülü
kullanmaz; REST (`BinanceClient.fetch_ohlcv`) tek karar kaynağı olarak kalır.
Akış, REST'e karşı parite/gecikme ölçümü ve ileride olay-tetikli tarama
(Faz 2) için kapanan barları ve anlık fiyatı tutar.

- Genel (public) market-data akışı: API anahtarı GEREKMEZ, hesap verisi yok.
- Tek combined-stream bağlantısı: ``/market/stream?streams=btcusdt@kline_15m/...``.
- Kopmada üstel geri çekilmeyle yeniden bağlanır; Binance 24 saatte bağlantıyı
  kestiği için 23 saatte proaktif yeniler.
- ``x=true`` (bar kapandı) mesajları ``closed`` önbelleğine ve ``on_close``
  geri çağrısına gider; oluşan (forming) bar yalnız ``latest``/``last_price``
  içinde durur — C1 (yalnız kapanmış bar) kuralı karar yolunda korunur.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Iterable, Optional, Tuple

log = logging.getLogger("efloud.ws_klines")

MAINNET_BASE = "wss://fstream.binance.com"
TESTNET_BASE = "wss://stream.binancefuture.com"
RECONNECT_AFTER_SEC = 23 * 3600
MAX_STREAMS = 200  # Binance üst sınırı 1024; güvenli pay


def to_stream_symbol(symbol: str) -> str:
    """'BTC/USDT' | 'BTC/USDT:USDT' → 'btcusdt'."""
    return symbol.split(":")[0].replace("/", "").lower()


def build_url(symbols: Iterable[str], timeframes: Iterable[str], testnet: bool = False) -> str:
    streams = [f"{to_stream_symbol(s)}@kline_{tf}" for s in symbols for tf in timeframes]
    if not streams:
        raise ValueError("no streams requested")
    if len(streams) > MAX_STREAMS:
        raise ValueError(f"too many streams: {len(streams)} > {MAX_STREAMS}")
    base = TESTNET_BASE if testnet else MAINNET_BASE
    # /market route: Binance USDT-M serves kline streams here; the legacy
    # /stream route still accepts the connection but sends no kline frames
    # (verified 2026-11-05 mainnet: /stream 0 msgs vs /market/stream 56 in 8s).
    return f"{base}/market/stream?streams={'/'.join(streams)}"


CloseCb = Callable[[str, str, dict, int], None]


class KlineStream:
    """Arka plan thread'inde çalışan kline WS istemcisi."""

    def __init__(
        self,
        symbols: Iterable[str],
        timeframes: Iterable[str],
        testnet: bool = False,
        on_close: Optional[CloseCb] = None,
        keep_closed: int = 8,
    ) -> None:
        self.symbols = list(dict.fromkeys(symbols))
        self.timeframes = list(dict.fromkeys(timeframes))
        self.testnet = testnet
        self.on_close = on_close
        self._sym_map: Dict[str, str] = {to_stream_symbol(s).upper(): s for s in self.symbols}
        self._latest: Dict[Tuple[str, str], dict] = {}
        self._closed: Dict[Tuple[str, str], Deque[dict]] = {}
        self._keep_closed = keep_closed
        self._lock = threading.Lock()
        self.messages = 0
        self.reconnects = 0
        self.last_msg_ms = 0
        self.connected = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── mesaj işleme (saf; testlenebilir) ─────────────────────────
    def handle_message(self, raw, recv_ms: Optional[int] = None) -> bool:
        """Bir combined-stream mesajını işle. Geçerli kline ise True."""
        recv_ms = int(time.time() * 1000) if recv_ms is None else recv_ms
        try:
            msg = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
            data = msg.get("data", msg)
            if data.get("e") != "kline":
                return False
            k = data["k"]
            sym = self._sym_map.get(str(k["s"]).upper())
            if sym is None:
                return False
            bar = {
                "t": int(k["t"]), "T": int(k["T"]), "tf": k["i"],
                "o": float(k["o"]), "h": float(k["h"]), "l": float(k["l"]),
                "c": float(k["c"]), "v": float(k["v"]), "x": bool(k["x"]),
                "event_ms": int(data.get("E", 0)), "recv_ms": recv_ms,
            }
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            log.debug("ws kline parse skipped: %s", e)
            return False

        key = (sym, bar["tf"])
        with self._lock:
            self._latest[key] = bar
            self.messages += 1
            self.last_msg_ms = recv_ms
            if bar["x"]:
                q = self._closed.setdefault(key, deque(maxlen=self._keep_closed))
                if not q or q[-1]["t"] != bar["t"]:
                    q.append(bar)
                else:
                    return True  # aynı kapanış tekrarı → geri çağrı yok
            else:
                return True
        if self.on_close:
            try:
                self.on_close(sym, bar["tf"], bar, recv_ms)
            except Exception as e:  # geri çağrı akışı asla düşürmesin
                log.warning("ws on_close callback failed: %s", e)
        return True

    # ── okuma API'si ──────────────────────────────────────────────
    def last_price(self, symbol: str) -> Optional[float]:
        """Anlık (oluşan bar dahil) son fiyat — YALNIZ gözlem/uyarı içindir."""
        with self._lock:
            ts = [b for (s, _), b in self._latest.items() if s == symbol]
        if not ts:
            return None
        return max(ts, key=lambda b: b["recv_ms"])["c"]

    def latest_bar(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Son alınan bar (oluşan ya da kapanmış) — intrabar fitil/temas için."""
        with self._lock:
            b = self._latest.get((symbol, timeframe))
            return dict(b) if b else None

    def last_closed(self, symbol: str, timeframe: str) -> Optional[dict]:
        with self._lock:
            q = self._closed.get((symbol, timeframe))
            return dict(q[-1]) if q else None

    def closed_bar(self, symbol: str, timeframe: str, open_ms: int) -> Optional[dict]:
        with self._lock:
            for b in reversed(self._closed.get((symbol, timeframe), ())):
                if b["t"] == open_ms:
                    return dict(b)
        return None

    def age_ms(self, now_ms: Optional[int] = None) -> Optional[int]:
        """Son mesajdan beri geçen süre; hiç mesaj yoksa None."""
        if not self.last_msg_ms:
            return None
        return (int(time.time() * 1000) if now_ms is None else now_ms) - self.last_msg_ms

    def stats(self) -> dict:
        return {
            "connected": self.connected, "messages": self.messages,
            "reconnects": self.reconnects, "age_ms": self.age_ms(),
            "streams": len(self.symbols) * len(self.timeframes),
        }

    # ── yaşam döngüsü ─────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        build_url(self.symbols, self.timeframes, self.testnet)  # erken doğrulama
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ws-klines", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._supervise())
        except RuntimeError:
            pass  # loop.stop() ile durduruldu
        finally:
            self.connected = False
            try:
                self._loop.close()
            except Exception:
                pass

    async def _supervise(self) -> None:
        import websockets  # gecikmeli import: modül yoksa yalnız bu thread düşer

        url = build_url(self.symbols, self.timeframes, self.testnet)
        backoff = 1.0
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20,
                                              max_queue=1024) as ws:
                    self.connected = True
                    log.info("ws klines connected (%d streams)", len(self.symbols) * len(self.timeframes))
                    while not self._stop.is_set():
                        if time.monotonic() - started > RECONNECT_AFTER_SEC:
                            log.info("ws klines proactive 23h reconnect")
                            break
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError:
                            continue  # sessiz dakika; ping/pong bağlantıyı denetler
                        self.handle_message(raw)
                        backoff = 1.0
            except Exception as e:
                log.warning("ws klines disconnected: %s", e)
            finally:
                self.connected = False
            if self._stop.is_set():
                break
            self.reconnects += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
