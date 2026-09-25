"""
Project Lucca — Live Session Flow Verification & Interactive Testing Harness
Directly exercises the full Orchestrator turn pipeline, live llama-server,
live EmbedWorker, SandboxService, and OutputSupervisor.

Usage:
    .venv\\Scripts\\python scripts\\test_session_flow.py --auto
    .venv\\Scripts\\python scripts\\test_session_flow.py --interactive
"""

import argparse
import sys
import time
from pathlib import Path

# Ensure project root and src are on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.core.orchestrator import Orchestrator
from lucca.core.trace import TurnTrace
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_tts import FakeTTS


def run_session(interactive: bool = False) -> None:
    print("=" * 70)
    print("  PROJECT LUCCA — LIVE ORCHESTRATOR VERIFICATION HARNESS")
    print("=" * 70)

    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    turn_idx = 1

    scenario = [
        "Can you look up Beverly N.F. Quintos, judge in the Philippines, and tell me about her?",
        "Why don't you look for alternative sources?",
        "Which websites have you searched?",
        "Factoriza",
    ]

    try:
        if interactive:
            print("\nInteractive Chat Mode. Type your message and press Enter (Ctrl+C to quit).\n")
            while True:
                try:
                    user_input = input(f"\n[Turn {turn_idx}] User > ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    break

                _execute_turn(orch, turn_idx, user_input)
                turn_idx += 1
        else:
            print(f"\nAutomated Replay Mode: Running {len(scenario)} sequential turns.\n")
            for prompt in scenario:
                print(f"\n" + "-" * 70)
                print(f"[Turn {turn_idx}] User: {prompt}")
                _execute_turn(orch, turn_idx, prompt)
                turn_idx += 1

    finally:
        print("\nShutting down Orchestrator and closing audio ring buffers...")
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
        print("[Done] Test session complete.")


def _execute_turn(orch: Orchestrator, turn_idx: int, prompt: str) -> None:
    trace = TurnTrace(trace_id=f"test-flow-{turn_idx}-{int(time.time())}", mode="transcript")
    t0 = time.perf_counter()

    tools_before = len(orch.executed_tools)
    orch._run_text_turn(trace, prompt)

    if orch.active_turn_thread:
        orch.active_turn_thread.join(timeout=45.0)

    elapsed = time.perf_counter() - t0
    new_tools = orch.executed_tools[tools_before:]

    print(f"\n[Turn {turn_idx} Completed in {elapsed:.2f}s]")
    if new_tools:
        print(f"  Tools Executed: {[t[0] for t in new_tools]}")
    else:
        print("  Tools Executed: None (Pure Conversational or Reflex)")

    if orch.history and orch.history[-1]["role"] == "assistant":
        print(f"  Assistant Reply:\n  {orch.history[-1]['content']}")
    print("-" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Lucca live session flow")
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Run interactive terminal chat"
    )
    parser.add_argument(
        "--auto", "-a", action="store_true", help="Run automated 4-turn replay of the live transcript"
    )
    args = parser.parse_args()

    run_session(interactive=not args.auto if not args.interactive else True)
