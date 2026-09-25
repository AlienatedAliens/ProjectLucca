"""Featureset audit F2: dead-code detection + fixed coverage heuristic."""

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path("src/lucca")
TESTS = Path("tests")

# ---- Fixed coverage: count 2-part and 3-part imports, and package imports ----
coverage: dict[str, set[str]] = defaultdict(set)
for tf in TESTS.rglob("test_*.py"):
    try:
        tree = ast.parse(tf.read_text(encoding="utf-8"), filename=str(tf))
    except SyntaxError:
        continue
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    for mod in mods:
        if not mod.startswith("lucca"):
            continue
        parts = mod.split(".")
        if len(parts) == 2:  # lucca.admin
            coverage[parts[1]].add(tf.name)
        elif len(parts) >= 3:  # lucca.core.orchestrator or lucca.reasoning.scheme
            coverage[f"{parts[1]}/{parts[2]}"].add(tf.name)

def is_covered(mod_key: str) -> bool:
    if mod_key in coverage:
        return True
    # package-level import covers submodules: 'reasoning/scheme' covers 'reasoning/scheme/parser'
    return any(mod_key.startswith(pkg + "/") for pkg in coverage)

print("=== Modules with zero test imports (>100 lines), FIXED heuristic ===")
for py in sorted(ROOT.rglob("*.py")):
    rel = py.relative_to(ROOT)
    lines = len(py.read_text(encoding="utf-8").splitlines())
    if lines <= 100:
        continue
    mod_key = f"{rel.parts[0]}/{rel.stem}" if len(rel.parts) > 1 else rel.stem
    if not is_covered(mod_key):
        print(f"  {rel} ({lines} lines)")

# ---- Dead code: public functions/classes never referenced outside their module ----
defined: dict[str, tuple[str, int, str]] = {}  # qualname -> (module, lineno, kind)
for py in sorted(ROOT.rglob("*.py")):
    rel = str(py.relative_to(ROOT))
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                defined[f"{rel}::{node.name}"] = (rel, node.lineno, "fn")
        elif isinstance(node, ast.ClassDef):
            defined[f"{rel}::{node.name}"] = (rel, node.lineno, "class")

# gather all name references across src + tests + scripts
refs: set[str] = set()
for base in (Path("src"), Path("tests"), Path("scripts"), Path("docker")):
    if not base.exists():
        continue
    for py in base.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                refs.add(node.id)
            elif isinstance(node, ast.Attribute):
                refs.add(node.attr)

print("\n=== Public functions/classes never referenced anywhere (dead candidates) ===")
dead = 0
for qual, (mod, lineno, kind) in sorted(defined.items()):
    name = qual.split("::")[1]
    if name in ("main", "run", "__init__"):
        continue
    if name not in refs:
        print(f"  {mod}:{lineno} ({kind}) {name}")
        dead += 1
print(f"\nTotal dead candidates: {dead} / {len(defined)} public definitions")
