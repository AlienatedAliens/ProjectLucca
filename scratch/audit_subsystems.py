"""Featureset audit: per-subsystem metrics across all of src/lucca."""

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path("src/lucca")
TESTS = Path("tests")

SUBSYSTEMS = {
    "brain": "LLM client, prompt builder, chunker, server control",
    "core": "Orchestrator, cascade, turn pipeline, capabilities, coherence",
    "memory": "Store, retrieval, gate, signers, reflection",
    "reasoning": "MicroScheme, lifecycle, induction, egraph, SMT, skills",
    "router": "Heuristic router, conformal guard, calibration, labeler",
    "sandbox": "Tool execution, policy, RPC, output supervisor, egress",
    "senses": "ASR, TTS, VAD, embed, DSP, ring buffers",
    "ui": "App, settings, speech bubble, telemetry HUD",
}

# test file -> covered source modules (by import)
test_coverage: dict[str, set[str]] = defaultdict(set)
for tf in TESTS.rglob("test_*.py"):
    try:
        tree = ast.parse(tf.read_text(encoding="utf-8"), filename=str(tf))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        mod = None
        if isinstance(node, ast.Import):
            for a in node.names:
                mod = a.name
                if mod and mod.startswith("lucca."):
                    parts = mod.split(".")
                    if len(parts) >= 3:
                        test_coverage[f"{parts[1]}/{parts[2].replace('.py','')}"].add(tf.name)
                        test_coverage[f"{parts[1]}/{parts[-1].replace('.py','')}"].add(tf.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("lucca."):
            parts = node.module.split(".")
            if len(parts) >= 3:
                test_coverage[f"{parts[1]}/{parts[2]}"].add(tf.name)
                test_coverage[f"{parts[1]}/{parts[-1]}"].add(tf.name)
                for a in node.names:
                    test_coverage[f"{parts[1]}/{a.name}"].add(tf.name)

print(f"{'module':42s} {'lines':>6} {'fns':>4} {'async':>5} {'exc':>4} {'sil':>4} {'geta':>4}  tests")
print("-" * 100)

subsystem_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
module_rows: list[tuple[str, int, int, int, int, int, int, int]] = []

for py in sorted(ROOT.rglob("*.py")):
    rel = py.relative_to(ROOT)
    sub = rel.parts[0] if len(rel.parts) > 1 else "(root)"
    text = py.read_text(encoding="utf-8")
    lines = len(text.splitlines())
    tree = ast.parse(text, filename=str(py))
    fns = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    async_fns = [n for n in fns if isinstance(n, ast.AsyncFunctionDef)]
    broad = 0
    silent = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            t = node.type
            if (t is not None and isinstance(t, ast.Name) and t.id == "Exception") or (
                t is not None and isinstance(t, ast.Attribute) and t.attr == "Exception"
            ):
                broad += 1
                body = ast.dump(node)
                if "id='logger'" not in body and "id='_LOG'" not in body and not any(
                    isinstance(n, ast.Raise) for n in ast.walk(node)
                ):
                    silent += 1
    geta = text.count("getattr(") + text.count("hasattr(")
    mod_key = f"{rel.parts[0]}/{rel.stem}" if len(rel.parts) > 1 else rel.stem
    n_tests = len(test_coverage.get(mod_key, set()))
    module_rows.append((str(rel), lines, len(fns), len(async_fns), broad, silent, geta, n_tests))
    st = subsystem_totals[sub]
    st["lines"] += lines
    st["fns"] += len(fns)
    st["async"] += len(async_fns)
    st["broad"] += broad
    st["silent"] += silent
    st["geta"] += geta
    st["modules"] += 1
    st["untested"] += 1 if n_tests == 0 else 0

for rel, lines, nf, na, broad, silent, geta, n_tests in sorted(
    module_rows, key=lambda r: -r[1]
):
    flag = " [X] NO TESTS" if n_tests == 0 and lines > 100 else ""
    print(f"{rel:42s} {lines:>6} {nf:>4} {na:>5} {broad:>4} {silent:>4} {geta:>4}  {n_tests}{flag}")

print("\n=== Subsystem roll-up ===")
print(f"{'subsystem':12s} {'mods':>5} {'lines':>6} {'fns':>5} {'async':>5} {'broad':>5} {'silent':>6} {'geta':>5} {'untested>100L':>13}")
for sub in SUBSYSTEMS:
    st = subsystem_totals.get(sub)
    if not st:
        continue
    print(
        f"{sub:12s} {st['modules']:>5} {st['lines']:>6} {st['fns']:>5} {st['async']:>5} "
        f"{st['broad']:>5} {st['silent']:>6} {st['geta']:>5} {st['untested']:>13}"
    )
st = subsystem_totals.get("(root)")
if st:
    print(
        f"{'(root)':12s} {st['modules']:>5} {st['lines']:>6} {st['fns']:>5} {st['async']:>5} "
        f"{st['broad']:>5} {st['silent']:>6} {st['geta']:>5} {st['untested']:>13}"
    )
