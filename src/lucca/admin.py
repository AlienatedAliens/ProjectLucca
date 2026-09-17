"""
Project Lucca — Admin CLI
Spec 11 §7 (`lucca-admin`)
"""

import sys

from lucca.core.env_check import run_env_check


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "help":
        msg = (
            "lucca-admin commands: env-check, latency, metrics, "
            "memory, rules, router, sandbox, models, replay, logs"
        )
        print(msg)
        return

    cmd = args[0]
    if cmd == "env-check":
        sys.exit(run_env_check())
    else:
        print(f"Unknown command '{cmd}'. Use 'lucca-admin help'")


if __name__ == "__main__":
    main()
