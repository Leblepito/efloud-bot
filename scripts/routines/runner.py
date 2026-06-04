import asyncio
import json
import sys
from pathlib import Path
from scripts.routines._base import now_utc, RoutineResult

REGISTRY = {}

def register(name):
    def decorator(func):
        REGISTRY[name] = func
        return func
    return decorator

# Import routines to register them
try:
    from scripts.routines import breaker_watch
except ImportError:
    pass
try:
    from scripts.routines import margin_watch
except ImportError:
    pass
try:
    from scripts.routines import position_audit
except ImportError:
    pass
try:
    from scripts.routines import config_drift
except ImportError:
    pass
try:
    from scripts.routines import equity_report
except ImportError:
    pass
try:
    from scripts.routines import market_collect
except ImportError:
    pass


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
}


async def watch_loop(client=None, alert=None, cfg=None):
    from scripts.routines._base import make_future_client, load_config, write_snapshot
    from scripts.routines._alert import AlertRouter

    config = cfg if cfg is not None else load_config()
    c = make_future_client(client)
    a = alert or AlertRouter.from_env()

    last_run = {name: 0.0 for name in CADENCES}
    heartbeat_path = "state/routines_watcher_heartbeat.json"

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
        if len(sys.argv) < 3:
            print("Usage: python -m scripts.routines.runner run <name>")
            sys.exit(2)
        name = sys.argv[2]
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
