"""Architectural audit: cross-package import graph + specific boundary checks."""

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path("src/lucca")
PACKAGES = {"brain", "core", "memory", "reasoning", "router", "sandbox", "senses", "ui", "tools"}

edges: dict[str, set[str]] = defaultdict(set)
signer_importers: list[str] = []
port_importers: dict[str, set[str]] = defaultdict(set)

for py in sorted(ROOT.rglob("*.py")):
    rel = py.relative_to(ROOT)
    src_pkg = rel.parts[0] if len(rel.parts) > 1 else "(root)"
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        mod: str | None = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if mod.startswith("lucca."):
                    parts = mod.split(".")
                    if len(parts) > 1 and parts[1] in PACKAGES:
                        edges[src_pkg].add(parts[1])
                    if "memory.signers" in mod:
                        signer_importers.append(f"{rel}: import {mod}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if mod.startswith("lucca."):
                parts = mod.split(".")
                if len(parts) > 1 and parts[1] in PACKAGES:
                    edges[src_pkg].add(parts[1])
                if "memory.signers" in mod:
                    signer_importers.append(f"{rel}: from {mod}")
            if mod == "lucca.ports":
                for alias in node.names:
                    port_importers[str(rel)].add(alias.name)

print("=== Cross-package import graph (package -> packages it imports) ===")
for pkg in sorted(edges):
    print(f"  {pkg:12s} -> {sorted(edges[pkg])}")

print("\n=== Direct importers of lucca.memory.signers (ADR-006 allow-list check) ===")
for s in signer_importers:
    print(f"  {s}")

print("\n=== lucca.ports consumers ===")
for f, names in sorted(port_importers.items()):
    print(f"  {f}: {sorted(names)}")
