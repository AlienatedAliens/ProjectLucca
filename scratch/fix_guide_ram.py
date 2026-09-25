"""Update the env-check count claim in the user guide."""

from pathlib import Path

p = Path("docs/USER_GUIDE_WHAT_LUCCA_DOES.md")
text = p.read_text(encoding="utf-8")
old = "Seven checks (`src/lucca/admin.py`): dGPU VRAM budget"
new = "Eight checks (`src/lucca/core/env_check.py`): system RAM budget (>=3.5 GB free), dGPU VRAM budget"
n = text.count(old)
print(f"occurrences: {n}")
if n == 1:
    p.write_text(text.replace(old, new), encoding="utf-8")
    print("OK")
