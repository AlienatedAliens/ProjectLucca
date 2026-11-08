"""
Project Lucca — Interactive Terminal Companion
Allows direct, live conversation with Lucca through the full compound pipeline,
with real-time token streaming, tool execution, and optional live voice playback.

Usage:
    .venv\\Scripts\\python.exe scripts/interactive_cli.py [--speak]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import TOOL_DEFINITIONS
from lucca.core.schemas import TokenDelta, ToolCallEnd
from lucca.sandbox.service import SandboxService


def main() -> None:
    parser = argparse.ArgumentParser(description="Lucca Interactive CLI Companion")
    parser.add_argument("--speak", action="store_true", help="Speak assistant responses with active Asuka voice")
    args = parser.parse_args()

    print("=" * 65)
    print("  PROJECT LUCCA — INTERACTIVE TERMINAL CHAT")
    if args.speak:
        print("  [VOICE ACTIVATED: Asuka Langley Soryu RVC v2 Enabled]")
    print("  Type 'exit' or 'quit' to end session.")
    print("=" * 65)

    client = LLMClient(base_url="http://127.0.0.1:8080")
    sandbox = SandboxService(use_direct_fallback=False, execute_apps=True)

    tts = None
    ring = None
    sd = None
    if args.speak:
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
            from lucca.senses.ring_buffer import get_playback_ring
            from lucca.senses.tts import TTSWorker

            ring = get_playback_ring(create=True)
            tts = TTSWorker(play_ring=ring)
        except Exception as exc:  # noqa: BLE001
            print(f"  [Warning: Could not initialize voice playback: {exc}]")
            tts = None

    history: list[dict[str, str]] = []

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        print("\nLucca: ", end="", flush=True)

        tool_calls_to_run = []
        full_reply = []

        # Turn streaming
        gen = client.stream_turn(
            current_text=user_input,
            history=history,
            tools=TOOL_DEFINITIONS,
            temperature=0.4,
            max_tokens=2048,
        )

        for event in gen:
            if isinstance(event, TokenDelta):
                print(event.delta, end="", flush=True)
                full_reply.append(event.delta)
            elif isinstance(event, ToolCallEnd):
                tool_calls_to_run.append((event.call.tool, event.call.args, event.call.call_id))

        reply_str = "".join(full_reply).strip()

        # Execute tools if requested
        if tool_calls_to_run:
            print("\n")
            tool_messages = []
            for name, tool_args, call_id in tool_calls_to_run:
                print(f"  [Tool Executing] -> {name}({tool_args})")
                res = sandbox.execute_tool(call_id=call_id, tool_name=name, args=tool_args)
                status_symbol = "OK" if res.ok else "FAILED"
                print(f"  [Tool Result {status_symbol}] -> {(res.content or res.stderr or '')[:150]}")
                tool_messages.append({
                    "role": "tool",
                    "content": res.content or res.stderr or "",
                    "tool_call_id": call_id,
                })

            # Synthesis turn after tool execution
            print("\nLucca (synthesis): ", end="", flush=True)
            synth_reply = []
            gen_synth = client.stream_turn(
                current_text=user_input,
                history=history,
                tools=TOOL_DEFINITIONS,
                tool_messages=tool_messages,
                temperature=0.4,
                max_tokens=2048,
            )
            for event in gen_synth:
                if isinstance(event, TokenDelta):
                    print(event.delta, end="", flush=True)
                    synth_reply.append(event.delta)
            reply_str = "".join(synth_reply).strip()

        print()

        # Play spoken audio if voice enabled
        if tts is not None and ring is not None and sd is not None and reply_str:
            try:
                done = tts.synthesize(chunk_id=len(history) + 1, text=reply_str)
                samples = ring.read_slice(0, done.samples)
                sd.play(samples, 24000)
                sd.wait()
            except Exception as exc:  # noqa: BLE001
                print(f"  [Speech playback error: {exc}]")

        history.append({"role": "user", "content": user_input})
        if reply_str:
            history.append({"role": "assistant", "content": reply_str})


if __name__ == "__main__":
    main()
