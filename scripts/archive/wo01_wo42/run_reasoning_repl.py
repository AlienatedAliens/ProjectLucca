"""
Project Lucca — CLI Entry Point for Reasoning REPL & CEGIS Testing Harness
v1.44.0 General Reasoning & Autonomous Program Induction

Usage Examples:
  # Launch interactive REPL:
  python scripts/run_reasoning_repl.py --interactive

  # Solve a task autonomously via Unshackled CEGIS:
  python scripts/run_reasoning_repl.py --task CenterMinimal --auto

  # Step through CEGIS repair turns on a ConceptARC task:
  python scripts/run_reasoning_repl.py --task AboveBelow1 --step

  # Run statistically powered benchmark sweep on ConceptARC:
  python scripts/run_reasoning_repl.py --benchmark concept_arc --concept AboveBelow --limit 10

  # Evaluate custom Python code on a task:
  python scripts/run_reasoning_repl.py --task OrderMinimal --eval "def transform(g): return sorted(g)"
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.reasoning.repl_loop import ReasoningREPL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project Lucca Reasoning REPL & Autonomous CEGIS Harness"
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Launch interactive REPL session"
    )
    parser.add_argument(
        "--task", "-t", type=str, default=None, help="Task name or JSON file path to load"
    )
    parser.add_argument(
        "--auto", action="store_true", help="Run full autonomous CEGIS loop on the task"
    )
    parser.add_argument(
        "--step", action="store_true", help="Run a single turn of CEGIS (induction or repair)"
    )
    parser.add_argument(
        "--induce", action="store_true", help="Run Turn 1 Unshackled Tool Induction"
    )
    parser.add_argument(
        "--show", action="store_true", help="Display task demonstrations"
    )
    parser.add_argument(
        "--diff", action="store_true", help="Display side-by-side diff against expected output"
    )
    parser.add_argument(
        "--eval", type=str, default=None, help="Execute Python code on active input"
    )
    parser.add_argument(
        "--scheme", type=str, default=None, help="Evaluate MicroScheme expression on active input"
    )
    parser.add_argument(
        "--benchmark", "-b", type=str, default=None, help="Benchmark suite (minimal, concept_arc, arc1)"
    )
    parser.add_argument(
        "--concept", "-c", type=str, default=None, help="Filter benchmark by concept name"
    )
    parser.add_argument(
        "--limit", "-l", type=int, default=None, help="Maximum number of benchmark tasks to run"
    )
    parser.add_argument(
        "--max-turns", type=int, default=4, help="Maximum CEGIS turns per task (default: 4)"
    )
    parser.add_argument(
        "--server-url", type=str, default="http://127.0.0.1:8080/v1/chat/completions",
        help="LLM completions endpoint"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable ANSI color codes in output"
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None, help="Output path to save benchmark JSON report"
    )

    args = parser.parse_args()

    repl = ReasoningREPL(
        server_url=args.server_url,
        use_color=not args.no_color,
    )

    # 1. Benchmark Mode
    if args.benchmark:
        summary = repl.run_benchmark(
            suite=args.benchmark,
            concept=args.concept,
            limit=args.limit,
            max_turns=args.max_turns,
        )
        if args.output and summary:
            out_p = Path(args.output)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(f"Report written to: {out_p}")
        return

    # 2. Task-specific execution
    if args.task:
        ok = repl.load_task(args.task)
        if not ok:
            sys.exit(1)

        if args.show:
            repl.show_task("train")
            repl.show_task("test")

        if args.eval:
            repl.eval_python(args.eval)

        if args.scheme:
            repl.eval_scheme(args.scheme)

        if args.induce:
            repl.induce_turn_1()

        if args.step:
            repl.step_cegis()

        if args.auto:
            repl.auto_cegis(max_turns=args.max_turns)

        if args.diff:
            repl.show_diff(train_idx=0)

        if not (args.show or args.eval or args.scheme or args.induce or args.step or args.auto or args.diff):
            # Default action when loading task without other flags: show task info and run auto
            repl.show_task("train", idx=0)
            repl.auto_cegis(max_turns=args.max_turns)

        return

    # 3. Interactive REPL Mode (default if no specific action provided)
    repl.run_interactive()


if __name__ == "__main__":
    main()
