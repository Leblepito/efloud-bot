"""
Notification Manager
━━━━━━━━━━━━━━━━━━━━
Bot'tan kullanıcıya bilgi akışı.

Kullanım yerleri:
  1. Read-only sembollerde sinyal tespiti → manuel trader'a haber
  2. Yeni pozisyon açıldı → bilgilendirme
  3. Stop-loss tetiklendi → alarm
  4. Circuit breaker tripped → uyarı

Şu an: sadece terminal + log (eye-catching)
İleride: Telegram bot, Discord webhook, email — aynı API ile.
"""

import logging
from typing import Optional
from datetime import datetime

from .null_manager import NullNotificationManager

log = logging.getLogger("efloud.notifications")


class NotificationManager:
    """Sinyal ve event bildirimi — kanal-agnostic."""

    def __init__(self, channels: Optional[list] = None, content_emitter=None):
        """
        channels: ['terminal', 'log', 'telegram', ...] — şimdilik 'terminal' + 'log'
        content_emitter: ContentJobEmitter instance (Lane A, default None = inert)
        """
        self.channels = channels or ['terminal', 'log']
        self.content_emitter = content_emitter

    def signal_readonly(self, symbol: str, direction: str,
                          entry: float, sl: float, tp1: float, tp2: float,
                          confluence: int, reasons: list = None,
                          timeframe: str = None, regime: str = None,
                          horizon: str = None, trace_id: str = None):
        """
        Read-only sembolde sinyal var — bot trade etmiyor ama kullanıcı bilsin.
        Manuel trader bu sinyali değerlendirip kendisi karar verir.
        """
        # RR hesapla
        risk = abs(entry - sl)
        reward1 = abs(tp1 - entry)
        rr1 = reward1 / risk if risk > 0 else 0

        msg_lines = [
            "",
            "╔" + "═" * 68 + "╗",
            f"║  🔍 [READONLY SIGNAL] {symbol:<46}║",
            "╠" + "═" * 68 + "╣",
            f"║  Direction:  {direction:<54}║",
            f"║  Entry:      ${entry:<54,.4f}║",
            f"║  Stop Loss:  ${sl:<54,.4f}║",
            f"║  TP1:        ${tp1:<54,.4f}║",
            f"║  TP2:        ${tp2:<54,.4f}║",
            f"║  Confluence: {confluence}/100  R:R: {rr1:.2f}{'':<33}║",
            "╚" + "═" * 68 + "╝",
            "",
        ]
        msg = "\n".join(msg_lines)

        if 'terminal' in self.channels:
            print(msg)
        if 'log' in self.channels:
            log.info(f"🔍 READONLY: {symbol} {direction} @ {entry:.4f} "
                     f"SL={sl:.4f} TP1={tp1:.4f} Conf={confluence}")

        # Lane A: content_job event emit (inert if emitter None)
        if self.content_emitter is not None:
            self.content_emitter.emit(
                "content_job.created",
                signal={"symbol": symbol, "direction": direction, "entry": entry,
                        "sl": sl, "tp1": tp1, "tp2": tp2, "confluence": confluence,
                        "timeframe": timeframe, "horizon": horizon, "regime": regime,
                        "reasons": reasons or [], "reasons_detail": {"trace_id": trace_id}},
            )

    def position_opened(self, symbol: str, direction: str, entry: float,
                          size: float, sl: float, tp1: float, confluence: int,
                          timeframe: str = None, regime: str = None,
                          horizon: str = None, trace_id: str = None,
                          leverage: int = None):
        """Pozisyon açıldı."""
        msg = (f"✅ [TRADE OPENED] {symbol} {direction} @ {entry:.4f} | "
               f"size={size:.6f} | SL={sl:.4f} TP1={tp1:.4f} | Conf={confluence}")
        if 'terminal' in self.channels:
            print(msg)
        if 'log' in self.channels:
            log.info(msg)

        # Lane A: position_opened content_job event (inert if emitter None)
        if self.content_emitter is not None:
            self.content_emitter.emit(
                "content_job.position_opened",
                signal={"symbol": symbol, "direction": direction, "entry": entry,
                        "sl": sl, "tp1": tp1, "confluence": confluence,
                        "timeframe": timeframe, "horizon": horizon, "regime": regime},
                execution={"filled": True, "fill_price": entry, "quantity": size,
                           "leverage": leverage, "trace_id": trace_id},
            )

    def position_closed(self, symbol: str, direction: str, exit_price: float,
                         pnl: float, reason: str):
        """Pozisyon kapandı."""
        emoji = "💰" if pnl > 0 else "📉" if pnl < 0 else "➖"
        msg = (f"{emoji} [TRADE CLOSED] {symbol} {direction} @ {exit_price:.4f} | "
               f"PnL=${pnl:+.2f} | reason={reason}")
        if 'terminal' in self.channels:
            print(msg)
        if 'log' in self.channels:
            log.info(msg)

    def alert(self, level: str, message: str):
        """
        Genel uyarı.
        level: INFO | WARNING | CRITICAL
        """
        prefix = {
            "INFO": "ℹ️ ",
            "WARNING": "⚠️ ",
            "CRITICAL": "🚨"
        }.get(level.upper(), "•")
        msg = f"{prefix}  [{level.upper()}] {message}"
        if 'terminal' in self.channels:
            print(msg)
        if 'log' in self.channels:
            getattr(log, level.lower(), log.info)(msg)

