"""Sub-classify silent broad excepts by handler body shape."""

import ast
from collections import Counter
from pathlib import Path

ROOT = Path("src/lucca")
shapes: Counter[str] = Counter()
by_shape: dict[str, list[str]] = {}

for py in sorted(ROOT.rglob("*.py")):
    rel = py.relative_to(ROOT)
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        t = node.type
        is_broad = (t is not None and isinstance(t, ast.Name) and t.id == "Exception") or (
            t is not None and isinstance(t, ast.Attribute) and t.attr == "Exception"
        )
        if not is_broad:
            continue
        body_src = ast.dump(node)
        has_log = "id='logger'" in body_src or "id='_LOG'" in body_src
        has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(node))
        if has_log or has_raise:
            continue
        # classify body
        stmts = node.body
        if len(stmts) == 1 and isinstance(stmts[0], ast.Pass):
            shape = "pass"
        elif len(stmts) == 1 and isinstance(stmts[0], ast.Return):
            val = ast.dump(stmts[0].value) if stmts[0].value else "None"
            shape = f"return_default({val[:40]})"
        elif any(isinstance(s, ast.Return) for s in stmts):
            shape = "multi_stmt_with_return"
        elif any(isinstance(s, ast.Continue) for s in stmts):
            shape = "continue"
        else:
            shape = "other"
        shapes[shape] += 1
        by_shape.setdefault(shape, []).append(f"{rel}:{node.lineno}")

print("=== Silent broad-except shapes ===")
for shape, n in shapes.most_common():
    print(f"  {shape}: {n}")

print("\n=== 'other' and 'multi_stmt_with_return' sites (need manual review) ===")
for shape in ("other", "multi_stmt_with_return"):
    for s in by_shape.get(shape, []):
        print(f"  [{shape}] {s}")
