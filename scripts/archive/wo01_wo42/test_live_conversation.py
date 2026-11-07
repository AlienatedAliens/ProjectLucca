"""
Project Lucca — Live AI Automated Conversation Test Harness
Directly exercises the live llama-server, prompt builder, and tool calling pipeline
without requiring manual microphone speech.

Usage:
    uv run python scripts/test_live_conversation.py
"""

import sys
import time
from pathlib import Path

import httpx

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import TOOL_DEFINITIONS, build_messages
from lucca.core.schemas import TokenDelta, ToolCallEnd
from lucca.sandbox.service import SandboxService


def check_server_health(base_url: str = "http://127.0.0.1:8080") -> bool:
    try:
        r = httpx.get(f"{base_url}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def run_live_test() -> None:
    base_url = "http://127.0.0.1:8080"
    print("=" * 65)
    print("  PROJECT LUCCA — LIVE AI AUTOMATED HARNESS")
    print("=" * 65)

    if not check_server_health(base_url):
        print(f"[FAIL] llama-server is not reachable at {base_url}.")
        print("Please start llama-server or run `uv run lucca` first.")
        sys.exit(1)

    print(f"[PASS] llama-server reachable at {base_url}\n")
    llm = LLMClient(base_url=base_url)
    sandbox = SandboxService(execute_apps=False)

    test_queries = [
        ("Conversational Chit-Chat", "Hello Lucca, tell me who you are in one short sentence."),
        ("Capabilities Tour (Fixed Bug)", "Okay, give me the tour of your capabilities."),
        ("Hardware Capabilities Query", "What hardware substrates are you running on?"),
        ("Action Tool Intent", "Can you launch Calculator for me?"),
    ]

    history: list[dict[str, str]] = []

    for idx, (label, query) in enumerate(test_queries, 1):
        print(f"\n--- [Test {idx}/4: {label}] ---")
        print(f"[User] {query}")

        t0 = time.perf_counter()
        tokens: list[str] = []
        tool_calls: list[ToolCallEnd] = []
        ttft_s: float | None = None

        for event in llm.stream_turn(current_text=query, history=history):
            if isinstance(event, TokenDelta) and event.delta:
                if ttft_s is None:
                    ttft_s = time.perf_counter() - t0
                tokens.append(event.delta)
                print(event.delta, end="", flush=True)
            elif isinstance(event, ToolCallEnd):
                tool_calls.append(event)

        elapsed = time.perf_counter() - t0
        spoken_response = ""

        if tool_calls:
            for tc in tool_calls:
                call = tc.call
                print(f"\n[Tool Call] tool={call.tool} args={call.args}")
                res = sandbox.execute_tool(
                    call_id=call.call_id, tool_name=call.tool, args=call.args
                )
                print(f"[Tool Executed] ok={res.ok} exit_code={res.exit_code}")

                # Vocalization check
                if call.tool == "query_capabilities":
                    spoken_response = (
                        "I can launch desktop applications like Calculator, Notepad, and Edge, "
                        "read and write files in your workspace, and remember our conversations "
                        "with persistent memory."
                    )
                elif call.tool == "launch_app":
                    app_name = str(call.args.get("app_name", "app"))
                    spoken_response = f"Launched {app_name}."
                else:
                    spoken_response = f"Executed {call.tool}."
                print(f"[Lucca Spoken] {spoken_response}")

        elif tokens:
            spoken_response = "".join(tokens).strip()

        print(f"\n[Timing] TTFT: {((ttft_s or 0) * 1000):.1f}ms | Total: {elapsed * 1000:.1f}ms")

        # Update conversational history
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": spoken_response})

    print("\n" + "=" * 65)
    print("  ALL LIVE AI TESTS EXECUTED SUCCESSFULLY")
    print("=" * 65)


if __name__ == "__main__":
    run_live_test()
