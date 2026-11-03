#!/usr/bin/env python3
"""LuxAlgo modu izleme aracı — yalnız stdlib.

Üç mod:

  follow  Canlı akış. stdin'den bot logunu okur, yalnız LuxAlgo/v2 satırlarını
          sade ve renkli basar.
            docker logs -f --since 10m efloud-bot 2>&1 \\
              | docker exec -i efloud-bot python scripts/lux_monitor.py follow

  report  Özet. stdin'deki logdan sembol bazında tarama durumu, açılan setup,
          kapıdan/red'den düşenler, girişler ve TP kaynakları.
            docker logs --since 24h efloud-bot 2>&1 \\
              | docker exec -i efloud-bot python scripts/lux_monitor.py report

  state   Bekleyen setup'lar. setup_candidates.json'u okur (EFLOUD_STATE_DIR ya
          da /app/state*), LuxAlgo kaynaklı olanları tablo halinde basar.
            docker exec efloud-bot python scripts/lux_monitor.py state

Log satırı düz ("ts | logger | LEVEL | msg") ya da JSON
(EFLOUD_LOGGING_FORMAT=json → {"ts":..,"message":..}) olabilir; ikisi de okunur.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Iterable, Optional, Tuple

MARKERS = ("[lux]", "[v2]", "[v2 reject]", "[v2 gate]", "LUX_", "LUX ")

RE_SCAN = re.compile(
    r"\[lux\] scan (?P<sym>\S+) htf_bias=(?P<bias>\S+) ltf_swing=(?P<sw>\S+) "
    r"ltf_internal=(?P<int>\S+) last_break=(?P<lb>\S+) active_obs=(?P<obs>\d+) "
    r"cands=(?P<c>\d+) eq=(?P<eq>\S+)")
RE_SETUP = re.compile(r"\[lux\] setup\+ (?P<sym>\S+) (?P<dir>LONG|SHORT) "
                      r"zone=\[(?P<lo>[^-\]]+)-(?P<hi>[^\]]+)\]")
RE_EXPIRED = re.compile(r"\[lux\] expired (?P<sym>\S+) (?P<dir>LONG|SHORT)")
RE_ENTRY = re.compile(
    r"\[v2\] (?P<dir>LONG|SHORT) (?P<sym>\S+) entry=(?P<entry>\S+) sl=(?P<sl>\S+) "
    r"tp1=(?P<tp1>\S+) tp2=(?P<tp2>\S+) size=\S+ \(zone=(?P<zone>[^,]+), "
    r"tp1=(?P<s1>[^,]+), tp2=(?P<s2>[^)]+)\)")
RE_REJECT = re.compile(r"\[v2 reject\] (?P<sym>\S+): (?P<reason>[a-z_0-9]+)")
RE_GATE = re.compile(r"\[v2 gate\] (?P<sym>\S+) (?P<dir>LONG|SHORT) setup dropped")


def parse_line(raw: str) -> Optional[Tuple[str, str]]:
    """(ts, message) döner; LuxAlgo/v2 ile ilgisizse None."""
    line = raw.rstrip("\n")
    if not line.strip():
        return None
    ts, msg = "", line
    if line.lstrip().startswith("{"):
        try:
            obj = json.loads(line)
            ts, msg = str(obj.get("ts", "")), str(obj.get("message", ""))
        except ValueError:
            pass
    else:
        parts = line.split(" | ", 3)
        if len(parts) == 4:
            ts, msg = parts[0].strip(), parts[3]
    if not any(m in msg for m in MARKERS):
        return None
    return ts, msg


# ── follow ─────────────────────────────────────────────────────────────────

_COLORS = {"setup+": "\033[32m", "expired": "\033[90m", "scan": "\033[36m",
           "entry": "\033[1;33m", "reject": "\033[31m", "gate": "\033[35m"}
_RESET = "\033[0m"


def classify(msg: str) -> str:
    if "[lux] setup+" in msg:
        return "setup+"
    if "[lux] expired" in msg:
        return "expired"
    if "[lux] scan" in msg:
        return "scan"
    if "[v2] " in msg:
        return "entry"
    if "[v2 reject]" in msg:
        return "reject"
    if "[v2 gate]" in msg:
        return "gate"
    return "other"


def follow(lines: Iterable[str], out=sys.stdout, color: bool = True) -> int:
    n = 0
    for raw in lines:
        p = parse_line(raw)
        if p is None:
            continue
        ts, msg = p
        kind = classify(msg)
        tag = f"{kind.upper():8s}"
        if color and kind in _COLORS:
            tag = f"{_COLORS[kind]}{tag}{_RESET}"
        out.write(f"{ts[:19]:19s} {tag} {msg}\n")
        out.flush()
        n += 1
    return n


# ── report ─────────────────────────────────────────────────────────────────

def build_report(lines: Iterable[str]) -> dict:
    scans: dict = {}
    setups = Counter()
    expired = Counter()
    gates = Counter()
    rejects = Counter()
    reject_reasons = Counter()
    entries = []
    tp_sources = Counter()
    for raw in lines:
        p = parse_line(raw)
        if p is None:
            continue
        ts, msg = p
        if m := RE_SCAN.search(msg):
            scans[m["sym"]] = {"ts": ts, **m.groupdict()}
        elif m := RE_SETUP.search(msg):
            setups[(m["sym"], m["dir"])] += 1
        elif m := RE_EXPIRED.search(msg):
            expired[(m["sym"], m["dir"])] += 1
        elif m := RE_ENTRY.search(msg):
            entries.append({"ts": ts, **m.groupdict()})
            tp_sources[m["s1"]] += 1
        elif m := RE_GATE.search(msg):
            gates[m["sym"]] += 1
        elif m := RE_REJECT.search(msg):
            rejects[m["sym"]] += 1
            reject_reasons[m["reason"]] += 1
    return {"scans": scans, "setups": setups, "expired": expired, "gates": gates,
            "rejects": rejects, "reject_reasons": reject_reasons,
            "entries": entries, "tp_sources": tp_sources}


def _table(rows, headers) -> str:
    rows = [[str(c) for c in r] for r in rows]
    w = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
         for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:{x}}}" for x in w)
    out = [fmt.format(*headers), fmt.format(*["-" * x for x in w])]
    out += [fmt.format(*r) for r in rows]
    return "\n".join(out)


def render_report(r: dict) -> str:
    out = []
    syms = sorted(set(r["scans"]) | {s for s, _ in r["setups"]} | set(r["rejects"])
                  | set(r["gates"]) | {e["sym"] for e in r["entries"]})
    if not syms:
        return ("LuxAlgo/v2 satırı bulunamadı. Kontrol: (1) deploy edilen commit "
                "[lux] loglarını içeriyor mu, (2) smc_v2.luxalgo.enabled: true mi, "
                "(3) bot running mi, (4) --since aralığı yeterli mi.")
    rows = []
    for s in syms:
        sc = r["scans"].get(s, {})
        rows.append([
            s, sc.get("bias", "-"), sc.get("sw", "-"), sc.get("lb", "-"),
            sc.get("obs", "-"),
            r["setups"][(s, "LONG")] + r["setups"][(s, "SHORT")],
            r["expired"][(s, "LONG")] + r["expired"][(s, "SHORT")],
            r["gates"][s], r["rejects"][s],
            sum(1 for e in r["entries"] if e["sym"] == s),
        ])
    out.append("SEMBOL BAZINDA (son tarama + dönem sayaçları)")
    out.append(_table(rows, ["sembol", "htf_bias", "ltf_swing", "son_kırılım",
                             "aktif_OB", "setup+", "expired", "kapı_drop",
                             "red", "giriş"]))
    if r["entries"]:
        out.append("\nGİRİŞLER")
        out.append(_table([[e["ts"][:19], e["sym"], e["dir"], e["entry"], e["sl"],
                            e["tp1"], e["s1"], e["tp2"], e["s2"], e["zone"]]
                           for e in r["entries"]],
                          ["zaman", "sembol", "yön", "giriş", "sl", "tp1", "tp1_kaynak",
                           "tp2", "tp2_kaynak", "zone"]))
        lux_tp = sum(v for k, v in r["tp_sources"].items() if k.startswith("LUX_"))
        out.append(f"\nTP1 kaynakları: {dict(r['tp_sources'])}  "
                   f"(LuxAlgo hedefi: {lux_tp}/{len(r['entries'])})")
    if r["reject_reasons"]:
        out.append(f"\nRED NEDENLERİ: {dict(r['reject_reasons'].most_common())}")
    tot_setup = sum(r["setups"].values())
    out.append(f"\nTOPLAM: setup+ {tot_setup} | expired {sum(r['expired'].values())} | "
               f"kapı_drop {sum(r['gates'].values())} | red {sum(r['rejects'].values())} | "
               f"giriş {len(r['entries'])}")
    return "\n".join(out)


# ── state ──────────────────────────────────────────────────────────────────

def find_state_file(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit
    env = os.environ.get("EFLOUD_STATE_DIR")
    cands = ([os.path.join(env, "setup_candidates.json")] if env else []) + \
        sorted(glob.glob("/app/state*/setup_candidates.json")) + \
        sorted(glob.glob("state*/setup_candidates.json"))
    return next((c for c in cands if os.path.exists(c)), None)


def render_state(path: Optional[str], show_all: bool = False) -> str:
    if not path or not os.path.exists(path):
        return "setup_candidates.json bulunamadı (EFLOUD_STATE_DIR / --file ver)."
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    cands = data.get("candidates", [])
    rows = []
    for c in cands:
        reasons = c.get("reasons") or []
        lux = bool(reasons) and str(reasons[0]).startswith("LUX ")
        if not (lux or show_all):
            continue
        z = c.get("target_zone") or {}
        rows.append([c.get("symbol"), c.get("direction"), c.get("state"),
                     c.get("bars_waited"), f"{z.get('low', 0):.8g}-{z.get('high', 0):.8g}",
                     f"{c.get('htf_swing_anchor', 0):.8g}", "LUX" if lux else "efloud",
                     (reasons[0] if reasons else "")[:70]])
    head = f"{path}  —  {len(rows)} bekleyen setup ({len(cands)} toplam)"
    if not rows:
        return head + "\n(LuxAlgo kaynaklı bekleyen setup yok)"
    return head + "\n" + _table(rows, ["sembol", "yön", "durum", "bar", "zone",
                                       "sl_çapa", "kaynak", "gerekçe"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("follow")
    f.add_argument("--color", action="store_true", help="renkleri zorla (tty yoksa)")
    sub.add_parser("report")
    s = sub.add_parser("state")
    s.add_argument("--file")
    s.add_argument("--all", action="store_true", help="efloud setup'larını da göster")
    a = ap.parse_args(argv)
    if a.cmd == "follow":
        try:
            follow(sys.stdin, color=a.color or sys.stdout.isatty())
        except KeyboardInterrupt:
            pass
        return 0
    if a.cmd == "report":
        print(render_report(build_report(sys.stdin)))
        return 0
    print(render_state(find_state_file(a.file), a.all))
    return 0


if __name__ == "__main__":
    sys.exit(main())
