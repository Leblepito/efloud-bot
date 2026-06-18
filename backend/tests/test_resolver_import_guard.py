import ast
from pathlib import Path

def test_resolver_imports_no_order_surface():
    src = Path("scripts/routines/resolve_signals.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"exchange", "engine.lifecycle", "engine.safe_orchestrator", "order_manager"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = (getattr(node, "module", "") or "")
            names = mod + " " + " ".join(a.name for a in getattr(node, "names", []))
            assert not any(b in names for b in banned), f"resolver must not import order surface: {names}"
