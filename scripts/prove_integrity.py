"""Project Lucca — Canonical Repository Integrity Verifier (WO-43 Phase 4.2)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify Project Lucca repository integrity.')
    parser.add_argument('--offline', action='store_true', help='Run offline static and holdout checks')
    _ = parser.parse_args()
    lint_bin = shutil.which('lint-imports') or 'lint-imports'
    steps = [
        ('static-gates', [sys.executable, '-m', 'pytest', 'tests/test_static_gates.py', '-q']),
        ('import-linter', [lint_bin]),
    ]
    for name, cmd in steps:
        print(f'[INTEGRITY] Running {name}...')
        res = subprocess.run(cmd, check=False)
        if res.returncode != 0:
            return res.returncode
    print('[INTEGRITY] All integrity checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
