#!/usr/bin/env python3
"""Module regression ledger for efloud-bot (generates REGRESSION.md).

The module table below is the hand-maintained part. Everything else is
derived reproducibly from tracked files:

* downstream consumers  = AST import scan of non-test .py files (+ declared
  runtime edges in MANUAL_EDGES, each with a `git grep` evidence command);
* acceptance tests      = test files that import a module's files, name one
  of its files in a string literal, or match the module's text tokens.

Usage:
  python scripts/regression_ledger.py render            # rewrite REGRESSION.md
  python scripts/regression_ledger.py check             # exit 1 if stale
  python scripts/regression_ledger.py affected [--base REF]
  python scripts/regression_ledger.py run MODULE... [--dry-run]
  python scripts/regression_ledger.py run --base REF [--dry-run]

Verdict = exit code: `run` exits non-zero if any required command fails.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = "REGRESSION.md"
SKIP_PREFIXES = ("node_modules/", "external_repos/", "_to_delete/", ".claude/")
# Changes here alter collection or the environment of every Python test.
GLOBAL_TRIGGERS = ("conftest.py", "tests/conftest.py", "pyproject.toml",
                   "requirements.txt", "constraints.txt")


@dataclass(frozen=True)
class Module:
    id: str
    title: str
    paths: tuple[str, ...]           # "dir/" prefix or fnmatch pattern
    commands: tuple[str, ...] = ()   # non-pytest acceptance commands
    tokens: str = ""                 # regex: test text that references it
    note: str = ""


MODULES: tuple[Module, ...] = (
    Module("data", "Market data fetch/cache + timeframe profiles", ("data/",)),
    Module("utils", "Logging + shared cache helpers", ("utils/",)),
    Module("risk-sizing", "Position sizing (`from risk import calc_position_size`)", ("risk/",)),
    Module("exchange", "Exchange adapters (Binance/CCXT, MT5, OANDA, WS klines)", ("exchange/",)),
    Module("smc-v1", "SMC v1 signal engine + confluence scoring",
           ("engine/smc.py", "engine/signals.py", "engine/confluence.py",
            "engine/levels.py", "engine/scenarios.py", "engine/universe.py",
            "engine/adaptive.py", "engine/intent.py")),
    Module("regimes", "ML regime model", ("engine/regimes/",)),
    Module("smc-v2", "SMC v2 port (zones, triggers, SL/TP calc) + v2 doctor",
           ("engine/smc_v2/", "tools/v2_doctor.py")),
    Module("safety", "Circuit breaker, guards, orphan protection, risk calc",
           ("engine/safety/", "engine/risk/", "engine/permissions/"),
           note="Mainnet-critical: risk-ops review + operator sign-off (CLAUDE.md)."),
    Module("llm-agents", "Advisory LLM layer (clients, roles, team, sentiment, Kronos)",
           ("engine/agents/", "engine/ai/")),
    Module("orchestrator", "SafeOrchestrator, lifecycle, journal, ledgers, notifications",
           ("engine/__init__.py", "engine/safe_orchestrator.py", "engine/lifecycle.py",
            "engine/journal.py", "engine/memory.py", "engine/postmortem.py",
            "engine/report.py", "engine/allocation.py", "engine/instance_manager.py",
            "engine/signal_ledger.py", "engine/edge_costs.py", "engine/edge_metrics.py",
            "engine/notifications/", "main.py", "preflight.py"),
           note="Mainnet-critical: risk-ops review + operator sign-off (CLAUDE.md)."),
    Module("backend-api", "FastAPI backend, auth, healthz, bot runner, websockets",
           ("backend/",)),
    Module("backend-db", "Postgres access + SQL migrations",
           ("backend/db.py", "backend/migrate.py", "backend/migrations/")),
    Module("backend-social", "Backend social content queue, generators, clients",
           ("backend/social/",)),
    Module("social-pipeline", "Chart/video render, lane A-G social bundles + publish",
           ("scripts/chart_render.py", "scripts/video_render.py", "scripts/lane_*",
            "scripts/lane_e/", "scripts/lane_c/", "scripts/daily_social_run.py",
            "scripts/higgsfield_adapter.py", "scripts/content_compliance.py",
            "scripts/content_templates/", "scripts/social_from_telegram.py",
            "scripts/pipeline_orchestrator.py", "scripts/collect_social_doctrine.py",
            "scripts/telegram_channel_collector.py", "engine/content_jobs.py")),
    Module("routines", "Scheduled routines (breaker/margin watch, reports, digests)",
           ("scripts/routines/",)),
    Module("desk", "Research desk scripts + desk agent definitions",
           ("scripts/desk/", "agents/")),
    Module("pine", "TradingView Pine port + pine-lab tooling",
           ("pine/", "scripts/build_pine_lab.py", "scripts/pine_lab_*"),
           tokens=r"\.pine\b|PINE_SPEC",
           note="Pine compile itself is manual (TradingView MCP `pine_smart_compile`, 0 errors)."),
    Module("scripts-misc", "Other operator/analysis scripts", ("scripts/",)),
    Module("alerter", "Telegram alerter (log-line rules, dedup, heartbeat)", ("ops/alerter/",)),
    Module("overseer", "Overseer (log/journal tail, healthz poll, sinks)", ("ops/overseer/",)),
    Module("ops-misc", "Daily report, IG/X webhook + token tooling", ("ops/",)),
    Module("panel", "Unified ops panel (HTTP Basic, proxies bot API)", ("panel/",)),
    Module("live-write-gate", "PreToolUse hook blocking live-bot writes",
           ("hooks/",), tokens=r"live_write_gate"),
    Module("configs", "Bot configs (live: configs/config.phase2_1k.yaml)",
           ("configs/", "config.yaml"), tokens=r"configs/|config\.yaml|config\.phase"),
    Module("deploy", "Dockerfiles, compose files, deploy scripts",
           ("deploy/", "Dockerfile", "Dockerfile.*", "docker-compose*.yml"),
           tokens=r"docker-compose|Dockerfile"),
    Module("ci", "GitHub workflows, CI review scripts, this ledger tool",
           (".github/", "scripts/ci/", "scripts/regression_ledger.py"),
           tokens=r"\.github|claude_review"),
    Module("collab", "3-model collaboration hub (tasks, logs, status)", ("collab/",),
           tokens=r"\bcollab\b"),
    Module("frontend", "Next.js dashboard", ("frontend/", "packages/"),
           commands=("npm run typecheck --workspace efloud-frontend",
                     "npm run test --workspace efloud-frontend")),
    Module("u2algo-site", "Marketing site + waitlist/webhook server (Railway)",
           ("u2algo-site/",), commands=("npm --prefix u2algo-site test",)),
)

# Runtime edges the import scan cannot see: (consumer, provider, reason, evidence).
MANUAL_EDGES: tuple[tuple[str, str, str, str], ...] = (
    ("alerter", "orchestrator", "parses bot log lines",
     'git grep -n "efloud_bot.log" -- ops/alerter'),
    ("alerter", "safety", "parses breaker/SL log lines",
     'git grep -n "breaker" -- ops/alerter/rules.py'),
    ("alerter", "exchange", "parses TP/SL order-failure log lines",
     'git grep -n "TP\\|SL" -- ops/alerter/rules.py'),
    ("overseer", "orchestrator", "tails trade_journal.jsonl + bot log",
     'git grep -n "journal" -- ops/overseer/ingestors'),
    ("overseer", "backend-api", "polls /healthz",
     'git grep -n "healthz" -- ops/overseer/ingestors'),
    ("routines", "orchestrator", "reads state/trade_journal.jsonl",
     'git grep -n "trade_journal.jsonl" -- scripts/routines'),
    ("panel", "backend-api", "proxies /api/bot/* and /api/breaker/reset over HTTP",
     'git grep -n "/api/" -- panel/main.py'),
    ("frontend", "backend-api", "fetches /api/* JSON over HTTP",
     'git grep -n "/api/" -- frontend/lib frontend/components'),
    ("pine", "smc-v1", "Pine port mirrors Python SMC logic (PINE_SPEC.md)",
     'git grep -n "signals.py" -- pine/PINE_SPEC.md'),
    ("pine", "smc-v2", "SMC v2 Pine port mirrors engine/smc_v2",
     'git grep -n "smc_v2" -- pine/PINE_SPEC.md'),
)

# Modules with no executable acceptance check today (ledger gaps, not passes).
KNOWN_GAPS: tuple[str, ...] = ()

_BY_ID = {m.id: m for m in MODULES}


def _score(pattern: str) -> int:
    return len(pattern.replace("*", "").replace("?", ""))


def module_of(path: str) -> str | None:
    best, best_score = None, -1
    for m in MODULES:
        for p in m.paths:
            hit = path.startswith(p) if p.endswith("/") else fnmatch.fnmatchcase(path, p)
            if hit and _score(p) > best_score:
                best, best_score = m.id, _score(p)
    return best


def is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.endswith(".py") and (
        name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
        or "/tests/" in f"/{path}"
    )


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    return sorted(f for f in out.splitlines() if f and not f.startswith(SKIP_PREFIXES))


@dataclass
class Graph:
    files: list[str]
    downstream: dict[str, set[str]] = field(default_factory=dict)  # provider -> consumers
    tests: dict[str, set[str]] = field(default_factory=dict)       # module -> test files

    def tests_for(self, module_id: str) -> set[str]:
        return self.tests.get(module_id, set())


def _imports(tree: ast.AST, pkg: str) -> list[tuple[str, tuple[str, ...]]]:
    """(module, submodule candidates) per import; `from a import b` tries a.b first."""
    found: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name, ()) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = pkg.split(".") if pkg else []
                base = parts[: len(parts) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            if mod:
                found.append((mod, tuple(f"{mod}.{a.name}" for a in node.names)))
    return found


def _resolver(files: list[str]):
    pyfiles = {f for f in files if f.endswith(".py")}
    by_stem: dict[str, list[str]] = {}
    for f in pyfiles:
        stem = f.rsplit("/", 1)[-1][:-3]
        if stem == "__init__":
            stem = f.rsplit("/", 2)[-2] if "/" in f else stem
        by_stem.setdefault(stem, []).append(f)

    def exact(name: str) -> list[str]:
        stem = name.replace(".", "/")
        return [c for c in (f"{stem}.py", f"{stem}/__init__.py") if c in pyfiles][:1]

    def resolve(name: str, importer: str, conservative: bool) -> list[str]:
        parts = name.split(".")
        for i in range(len(parts), 0, -1):
            stem = "/".join(parts[:i])
            for cand in (f"{stem}.py", f"{stem}/__init__.py"):
                if cand in pyfiles:
                    return [cand]
        if parts[0] in sys.stdlib_module_names:
            return []  # never let a repo file shadow the stdlib (e.g. `secrets`)
        here = importer.rsplit("/", 1)[0] + "/" if "/" in importer else ""
        sibling = f"{here}{parts[0]}.py"
        if sibling in pyfiles:
            return [sibling]
        cands = by_stem.get(parts[0], [])
        return cands if (conservative or len(cands) == 1) else []

    return resolve, exact


def build_graph(root: Path = ROOT) -> Graph:
    files = tracked_files(root)
    g = Graph(files=files)
    resolve, exact = _resolver(files)
    basenames: dict[str, list[str]] = {}
    for f in files:
        basenames.setdefault(f.rsplit("/", 1)[-1], []).append(f)
    token_res = {m.id: re.compile(m.tokens) for m in MODULES if m.tokens}

    for f in files:
        if not f.endswith(".py"):
            continue
        try:
            text = (root / f).read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            continue
        pkg = f.rsplit("/", 1)[0].replace("/", ".") if "/" in f else ""
        test = is_test_file(f)
        targets: set[str] = set()
        for mod, subs in _imports(tree, pkg):
            hits = [h for sub in subs for h in exact(sub)]
            if len(hits) < len(subs) or not subs:
                hits += resolve(mod, f, conservative=test)
            targets.update(hits)
        if test:
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    s = node.value.replace("\\", "/")
                    if s in basenames and "." in s:
                        targets.update(basenames[s])
                    elif "/" in s and s in g.files:
                        targets.add(s)
            if f.endswith("conftest.py"):
                continue  # loaded implicitly by pytest; changes handled in plan_for
            hit = {module_of(t) for t in targets} | {
                mid for mid, rx in token_res.items() if rx.search(text)}
            for mid in hit - {None}:
                g.tests.setdefault(mid, set()).add(f)
        else:
            src = module_of(f)
            for t in targets:
                dst = module_of(t)
                if src and dst and dst != src:
                    g.downstream.setdefault(dst, set()).add(src)
    return g


@dataclass
class Plan:
    modules: set[str] = field(default_factory=set)
    test_files: set[str] = field(default_factory=set)
    unverified_included: set[str] = field(default_factory=set)
    unmapped: list[str] = field(default_factory=list)
    full_suite: bool = False


def _manual_consumers(provider: str) -> set[str]:
    return {c for c, p, _, _ in MANUAL_EDGES if p == provider}


def plan_for(g: Graph, changed: list[str]) -> Plan:
    plan = Plan()
    queue: list[str] = []
    for f in sorted(set(changed)):
        if f in GLOBAL_TRIGGERS:
            plan.full_suite = True
        elif f.endswith("/conftest.py"):
            plan.test_files.add(f.rsplit("/", 1)[0])  # rerun the whole directory
        elif is_test_file(f):
            plan.test_files.add(f)
        elif (mid := module_of(f)) is not None:
            queue.append(mid)
        else:
            plan.unmapped.append(f)
    while queue:
        mid = queue.pop()
        if mid in plan.modules:
            continue
        plan.modules.add(mid)
        manual = _manual_consumers(mid)
        plan.unverified_included |= manual - g.downstream.get(mid, set())
        queue.extend(g.downstream.get(mid, set()) | manual)
    plan.unverified_included &= plan.modules
    for mid in plan.modules:
        plan.test_files |= g.tests_for(mid)
    return plan


def commands_for(plan: Plan) -> list[str]:
    cmds = ["python -m pytest -q"] if plan.full_suite else []
    if plan.test_files and not plan.full_suite:
        cmds.append("python -m pytest -q " + " ".join(sorted(plan.test_files)))
    for mid in sorted(plan.modules):
        cmds.extend(_BY_ID[mid].commands)
    return cmds


def changed_files(base: str, root: Path = ROOT) -> list[str]:
    def git(*args: str) -> list[str]:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True,
                             text=True, encoding="utf-8", check=True).stdout
        return [ln for ln in out.splitlines() if ln]

    names = set(git("diff", "--name-only", f"{base}...HEAD"))
    names |= set(git("diff", "--name-only")) | set(git("diff", "--cached", "--name-only"))
    names |= {ln[3:].split(" -> ")[-1].strip('"') for ln in git("status", "--porcelain")}
    return sorted(names)


def render(g: Graph) -> str:
    out = [
        "# REGRESSION.md — module regression ledger",
        "",
        "<!-- GENERATED by `python scripts/regression_ledger.py render` — do not edit by hand.",
        "     Edit the module table / MANUAL_EDGES in scripts/regression_ledger.py instead. -->",
        "",
        "After any change: `python scripts/regression_ledger.py run --base origin/master`.",
        "It maps the diff (committed + staged + unstaged + untracked) to modules, follows",
        "downstream consumers transitively, and runs every required command.",
        "**Verdict = exit code.** Red anywhere means the change is not finished.",
        "",
        "Propagation rule (all modules): a change to module A runs A plus every",
        "transitive downstream consumer, including `unverified` runtime edges (they are",
        "always included, never skipped). A changed test file always runs. Changes to",
        f"{', '.join(f'`{t}`' for t in GLOBAL_TRIGGERS)} run the full suite.",
        "Exemption: only a diff with no mapped path (e.g. docs-only); `affected` lists",
        "such paths as unmapped. Test points (TEST-IDs) live in `TESTS.md`.",
        "",
        "Dependency evidence: AST import scan of tracked non-test `.py` files",
        "(`python scripts/regression_ledger.py render`); test mapping = imports, file",
        "names in string literals, and per-module text tokens. Runtime edges below are",
        "`unverified` (not import-provable) and carry a `git grep` evidence command.",
        "",
        "## Runtime (unverified) edges",
        "",
        "| Consumer | Provider | Why | Evidence |",
        "|---|---|---|---|",
    ]
    for c, p, why, ev in MANUAL_EDGES:
        out.append(f"| {c} | {p} | {why} | `{ev}` |")
    out.append("")
    for n, m in enumerate(MODULES, 1):
        down = sorted(g.downstream.get(m.id, set()))
        manual = sorted(_manual_consumers(m.id) - set(down))
        consumers = down + [f"{c} (unverified)" for c in manual]
        tests = sorted(g.tests_for(m.id))
        out += [f"## Module {n:02d} — {m.id}", "", m.title, ""]
        out.append("Paths: " + ", ".join(f"`{p}`" for p in m.paths))
        out.append("Downstream consumers: " + (", ".join(consumers) or "none"))
        acc = [f"`python scripts/regression_ledger.py run {m.id}`"]
        acc += [f"`{c}`" for c in m.commands]
        out.append("Regression acceptance command: " + " + ".join(acc))
        if tests:
            out.append(f"Mapped tests: {len(tests)}")
        elif not m.commands:
            out.append("Mapped tests: 0 — **LEDGER GAP** (no executable acceptance check)")
        if m.note:
            out.append(f"Note: {m.note}")
        if tests:
            out += ["", "<details><summary>test files</summary>", ""]
            out += [f"- `{t}`" for t in tests]
            out += ["", "</details>"]
        out.append("")
    return "\n".join(out)


def _run(cmds: list[str], dry: bool) -> int:
    worst = 0
    for c in cmds:
        argv = shlex.split(c)
        argv[0] = sys.executable if argv[0] == "python" else (shutil.which(argv[0]) or argv[0])
        print(f"$ {c}", flush=True)
        if dry:
            continue
        code = subprocess.run(argv, cwd=ROOT).returncode
        print(f"-> exit {code}", flush=True)
        worst = worst or code
    return worst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render")
    sub.add_parser("check")
    a = sub.add_parser("affected")
    a.add_argument("--base", default="origin/master")
    r = sub.add_parser("run")
    r.add_argument("modules", nargs="*")
    r.add_argument("--base")
    r.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    g = build_graph(ROOT)
    if args.cmd == "render":
        (ROOT / LEDGER).write_text(render(g), encoding="utf-8", newline="\n")
        return 0
    if args.cmd == "check":
        current = (ROOT / LEDGER).read_text(encoding="utf-8")
        if current != render(g):
            print("REGRESSION.md is stale: run `python scripts/regression_ledger.py render`")
            return 1
        return 0
    if args.cmd == "affected" or (args.cmd == "run" and args.base):
        plan = plan_for(g, changed_files(args.base))
    else:
        unknown = [m for m in args.modules if m not in _BY_ID]
        if unknown or not args.modules:
            print(f"unknown/missing module(s): {unknown}; known: {sorted(_BY_ID)}")
            return 2
        plan = Plan(modules=set(args.modules))
        for mid in plan.modules:
            plan.test_files |= g.tests_for(mid)
    print(f"modules: {', '.join(sorted(plan.modules)) or 'none'}")
    if plan.unverified_included:
        print(f"unverified edges included: {', '.join(sorted(plan.unverified_included))}")
    if plan.unmapped:
        print(f"unmapped (no regression module): {', '.join(plan.unmapped)}")
    cmds = commands_for(plan)
    if args.cmd == "affected":
        print("\n".join(f"$ {c}" for c in cmds) or "nothing to run")
        return 0
    return _run(cmds, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
