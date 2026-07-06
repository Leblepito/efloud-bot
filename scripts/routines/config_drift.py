from scripts.routines.runner import register
from scripts.routines._base import RoutineResult

def get_nested(d, key_path):
    parts = key_path.split(".")
    val = d
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return None
    return val

def evaluate(live_cfg, repo_cfg, watch_keys):
    breaches = []
    rows = []
    
    for key in watch_keys:
        live_val = get_nested(live_cfg, key)
        repo_val = get_nested(repo_cfg, key)
        
        drift = live_val != repo_val
        
        if drift:
            breaches.append({
                "severity": "warn",
                "key": f"drift:{key}",
                "title": f"Config Drift: {key}",
                "body": f"Value in live config is {live_val} while repository config is {repo_val}."
            })
            rows.append(f"| {key} | {live_val} | {repo_val} | **YES** |")
        else:
            rows.append(f"| {key} | {live_val} | {repo_val} | No |")
            
    report_lines = [
        "# Config Drift Report",
        "",
        "| Key | Live Config | Repo Config | Drift? |",
        "| --- | --- | --- | --- |"
    ]
    report_lines.extend(rows)
    report_text = "\n".join(report_lines)
    
    return report_text, breaches

@register("config_drift")
def run(client=None, alert=None, cfg=None):
    import os
    from scripts.routines._base import write_snapshot, write_report, RoutineResult, load_config, get_api

    # Baseline = bu instance'ın GERÇEKTEN yüklediği config (long/scalp
    # configs/config.phase2_*_1k.yaml kullanır; root config.yaml baseline'ı
    # onlar için sistematik false-positive drift üretir).
    repo_cfg = load_config(os.environ.get("EFLOUD_CONFIG_PATH", "config.yaml"))
    
    watch_keys = [
        "min_confluence",
        "symbols",
        "risk.max_position_notional_pct",
        "safety.weekly_drawdown_limit_pct",
        "safety.daily_loss_pct_limit"
    ]
    
    try:
        live_cfg = get_api("/api/config")
    except Exception as e:
        print(f"Error fetching live config via API: {e}")
        return RoutineResult(
            name="config_drift",
            ok=False,
            error=str(e)
        )
        
    report_text, breaches = evaluate(live_cfg, repo_cfg, watch_keys)
    
    report_path = "reports/config_drift.md"
    snapshot_path = "state/config_drift_snapshot.json"
    
    write_report(report_path, report_text)
    
    snapshot_data = {
        "live_cfg": live_cfg,
        "repo_cfg": repo_cfg,
        "watch_keys": watch_keys,
        "breaches_count": len(breaches)
    }
    write_snapshot(snapshot_path, snapshot_data)
    
    return RoutineResult(
        name="config_drift",
        ok=True,
        breaches=breaches,
        report_path=report_path
    )
