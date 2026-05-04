"""No-op notification manager for backtest mode.

Swallows all calls. Use when you want SafeOrchestrator to run without
any external notifications (logs, webhooks, etc.).
"""


class NullNotificationManager:
    def notify(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        # Any unknown notify_* method becomes a no-op callable.
        def noop(*a, **kw):
            return None
        return noop
