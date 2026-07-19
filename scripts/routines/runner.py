import asyncio
import json
import sys
from pathlib import Path
from scripts.routines._base import now_utc, RoutineResult

# ── python -m modül-ikiliği fix'i (2026-07-04) ──────────────────────────────
# `python -m scripts.routines.runner` bu dosyayı __main__ olarak yükler;
# rutin modülleri ise `from scripts.routines.runner import register` ile
# İKİNCİ bir kopya import eder → iki ayrı REGISTRY oluşur ve run_one tüm
# rutinler için "Unknown routine" döner (watch container'ında rutinler hiç
# koşmaz). Alias ile iki isim TEK modülü paylaşır, REGISTRY ortaklaşır.
if __name__ == "__main__":
    sys.modules.setdefault("scripts.routines.runner", sys.modules["__main__"])

REGISTRY = {}

def register(name):
    def decorator(func):
        REGISTRY[name] = func
        return func
    return decorator

# Import routines to register them.
# R-12 fix (2026-07-17): sessiz `except ImportError: pass` — pinlenmemiş
# bağımlılık (requirements '>=') yeni build'de bir modül importunu kırarsa
# rutin REGISTRY'den sessizce düşüyor, watch-loop "Unknown routine" ile devam
# ediyor ve operatör o izleme kanalını süresiz kaybediyordu. Artık her import
# hatası traceback'iyle YÜKSEK SESLE loglanır (ImportError dışındakiler —
# örn. SyntaxError — de yakalanır ki tek bozuk modül tüm watcher'ı düşürmesin);
# kalan rutinler çalışmaya devam eder.
IMPORT_FAILURES: dict = {}

def _import_routine(_modname):
    import importlib
    import traceback
    try:
        importlib.import_module(f"scripts.routines.{_modname}")
    except Exception as e:
        IMPORT_FAILURES[_modname] = f"{type(e).__name__}: {e}"
        print(f"[routines] IMPORT FAILED: {_modname}: {type(e).__name__}: {e}",
              file=sys.stderr)
        traceback.print_exc()

# Edge Measurement Core (activation item A): self-registering routines must be
# imported here or the watch-loop scheduler never sees them.
for _modname in (
    "breaker_watch", "margin_watch", "position_audit", "config_drift",
    "equity_report", "market_collect", "proof_export",
    "resolve_signals", "edge_report", "social_content",
):
    _import_routine(_modname)


def emit_import_failure_alerts(alert_router) -> int:
    """R-12+ (2026-07-18): IMPORT_FAILURES'daki her modül için bir kez Telegram
    alert'i at. Rutin import'u yeni build'de (dep-drift) kırılırsa REGISTRY'den
    sessizce düşüyordu; loud-log container'da kalıyor, operatöre ulaşmıyordu.
    Watcher açılışında çağrılır. Kaç alert denendiğini döndürür (test için)."""
    if not IMPORT_FAILURES:
        return 0
    sent = 0
    for _mod, _err in IMPORT_FAILURES.items():
        try:
            alert_router.send(
                "critical", f"routine_import_fail:{_mod}",
                f"Rutin import HATASI: {_mod}",
                f"{_err} — bu rutin REGISTRY'de yok, izleme kanalı düştü. "
                f"Yeni build'de dep-drift olabilir; requirements/constraints kontrol et.",
            )
            sent += 1
        except Exception as _e:
            print(f"startup import-fail alert gönderilemedi ({_mod}): {_e}")
    return sent


def run_one(name, client=None, alert=None, cfg=None) -> int:
    if name not in REGISTRY:
        print(f"Unknown routine: {name}")
        return 2
    try:
        from scripts.routines._base import make_future_client, load_config
        from scripts.routines._alert import AlertRouter

        c = make_future_client(client)
        a = alert or AlertRouter.from_env()
        config = cfg if cfg is not None else load_config()

        routine_func = REGISTRY[name]
        result = routine_func(client=c, alert=a, cfg=config)

        if result.breaches:
            for breach in result.breaches:
                a.send(
                    severity=breach.get("severity", "info"),
                    dedup_key=breach.get("key"),
                    title=breach.get("title"),
                    body=breach.get("body")
                )

        if not result.ok:
            print(f"Routine {name} failed or reported not OK.")
            return 1
        return 0
    except Exception as e:
        import traceback
        print(f"Exception running routine {name}: {e}")
        traceback.print_exc()
        return 1


CADENCES = {
    "breaker_watch": 60,
    "margin_watch": 60,
    "position_audit": 120,
    "config_drift": 3600,
    "market_collect": 300,
    # Edge Measurement Core: resolver every 5min, report hourly. Both are
    # cheap no-ops while signal_ledger is disabled (flag/env gate in main()).
    "signal_resolver": 300,
    "edge_report": 3600,
    # P-Kronos-Social: 4 saatte bir içerik üretimi. SOCIAL_CONTENT_ENABLED
    # kapalıyken (default) no-op — slot-dedup rutin içinde.
    "social_content": 14400,
}


async def watch_loop(client=None, alert=None, cfg=None):
    from scripts.routines._base import make_future_client, load_config, write_snapshot
    from scripts.routines._alert import AlertRouter

    config = cfg if cfg is not None else load_config()
    c = make_future_client(client)
    a = alert or AlertRouter.from_env()

    last_run = {name: 0.0 for name in CADENCES}
    heartbeat_path = "state/routines_watcher_heartbeat.json"

    # R-12+ (2026-07-18): watcher açılışında import-hatası alert'i (helper üstte).
    emit_import_failure_alerts(a)

    print("Starting routines-watcher loop...")
    while True:
        now = now_utc().timestamp()

        try:
            write_snapshot(heartbeat_path, {"status": "running", "timestamp": now})
        except Exception as e:
            print(f"Error writing heartbeat: {e}")

        for name, cadence in CADENCES.items():
            if now - last_run[name] >= cadence:
                print(f"[{now_utc().isoformat()}] Running routine: {name}")
                try:
                    rc = await asyncio.to_thread(run_one, name, c, a, config)
                    print(f"Finished routine: {name} (exit code: {rc})")
                except Exception as e:
                    print(f"Exception running routine {name} in watch loop: {e}")
                last_run[name] = now

        await asyncio.sleep(1)


if __name__ == "__main__":
    from scripts.routines._base import load_env
    load_env()

    if len(sys.argv) < 2:
        print("Usage: python -m scripts.routines.runner [run <name> | watch]")
        sys.exit(2)

    cmd = sys.argv[1]
    if cmd == "run":
        import os
        name = sys.argv[2] if len(sys.argv) >= 3 else os.environ.get("ROUTINE")
        if not name:
            print("Usage: python -m scripts.routines.runner run <name> (or set ROUTINE environment variable)")
            sys.exit(2)
        rc = run_one(name)
        sys.exit(rc)
    elif cmd == "watch":
        try:
            asyncio.run(watch_loop())
        except KeyboardInterrupt:
            print("Watcher stopped by user.")
            sys.exit(0)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(2)
