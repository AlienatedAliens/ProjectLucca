"""Composite lint script for T0 gate (F-TEST-008).

Chains:
1. ruff check src tests
2. ruff format --check src tests
3. mypy src
4. lint-imports
5. pytest -q --collect-only
"""

import shutil
import subprocess
import sys


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"\n[T0] Running {name}: {' '.join(cmd)}")
    res = subprocess.run(cmd, check=False)  # noqa: S603
    if res.returncode != 0:
        print(f"[FAIL] {name} failed with exit code {res.returncode}")
        return False
    print(f"[PASS] {name}")
    return True


def main() -> None:
    lint_imports_bin = shutil.which("lint-imports") or "lint-imports"
    steps = [
        ("ruff check", [sys.executable, "-m", "ruff", "check", "src", "tests"]),
        ("ruff format", [sys.executable, "-m", "ruff", "format", "--check", "src", "tests"]),
        ("mypy", [sys.executable, "-m", "mypy", "src"]),
        ("import-linter", [lint_imports_bin]),
        ("pytest collect", [sys.executable, "-m", "pytest", "-q", "--collect-only"]),
    ]

    for name, cmd in steps:
        if not run_step(name, cmd):
            sys.exit(1)

    print("\n[SUCCESS] All T0 gate checks passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()
