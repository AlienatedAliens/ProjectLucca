"""Architectural audit: exception classification, god-object metrics, test hooks."""

import ast
from collections import Counter
from pathlib import Path

ROOT = Path("src/lucca")

logged = 0
reraise = 0
silent: list[str] = []
typed_ok = 0  # except Exception with specific re-raise or return of error value

for py in sorted(ROOT.rglob("*.py")):
    rel = py.relative_to(ROOT)
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        t = node.type
        is_broad = (
            t is not None
            and isinstance(t, ast.Name)
            and t.id == "Exception"
        ) or (
            t is not None
            and isinstance(t, ast.Attribute)
            and t.attr == "Exception"
        )
        if not is_broad:
            continue
        body_src = ast.dump(node)
        has_log = (
            "id='logger'" in body_src
            or "id='_LOG'" in body_src
            or "id='structlog'" in body_src
            or "id='logging'" in body_src
        )
        has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(node))
        if has_raise:
            reraise += 1
        elif has_log:
            logged += 1
        else:
            # find line
            silent.append(f"{rel}:{node.lineno}")

print("=== Broad 'except Exception' classification ===")
print(f"  logged-and-continue: {logged}")
print(f"  re-raises:           {reraise}")
print(f"  SILENT (no log, no raise): {len(silent)}")
for s in silent:
    print(f"    {s}")

print("\n=== God-object metrics ===")
for target in ("core/orchestrator.py", "ui/settings_dialog.py", "core/cascade.py"):
    p = ROOT / target
    tree = ast.parse(p.read_text(encoding="utf-8"))
    methods = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    print(f"  {target}: {len(classes)} classes, {len(methods)} functions/methods")

print("\n=== Repeated signer-construction pattern in orchestrator ===")
orch = (ROOT / "core/orchestrator.py").read_text(encoding="utf-8")
print(f"  'create_.*_signer' call sites: {orch.count('create_user_speech_signer') + orch.count('create_tool_result_signer') + orch.count('create_assistant_utterance_signer')}")
print(f"  dev-key fallback literal occurrences: {orch.count('01234567890123456789012345678901')}")

print("\n=== Test hooks in production code ===")
for py in sorted(ROOT.rglob("*.py")):
    rel = py.relative_to(ROOT)
    text = py.read_text(encoding="utf-8")
    for hook in ("_current_simulated_time", "_early_transcript_commit", "_last_transcript_signed"):
        n = text.count(hook)
        if n:
            print(f"  {rel}: {hook} x{n}")

print("\n=== hasattr/getattr defensive patterns per file (top 10) ===")
counts: Counter[str] = Counter()
for py in sorted(ROOT.rglob("*.py")):
    rel = str(py.relative_to(ROOT))
    text = py.read_text(encoding="utf-8")
    counts[rel] = text.count("getattr(") + text.count("hasattr(")
for f, c in counts.most_common(10):
    print(f"  {f}: {c}")
