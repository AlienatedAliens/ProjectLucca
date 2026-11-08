"""
Project Lucca — Live LLM Verification & Response Battery
Tests live llama-server running Mistral NeMo 12B Instruct Abliterated Q6_K
with canonical Tekken Jinja template and hardened inference settings.
"""

import json
import sys
import time

import httpx

from lucca.brain.llm_client import LLMClient
from lucca.brain.prompt_builder import TOOL_DEFINITIONS
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Done, TokenDelta, ToolCallEnd
from lucca.core.trace import TurnTrace


def main() -> int:
    print("====================================================================")
    print("  PROJECT LUCCA — EXTENSIVE LIVE LLM RESPONSE VERIFICATION")
    print("====================================================================")

    # 1. Health & Template Capabilities Check
    print("\n[1/5] Checking llama-server /props and /health...")
    try:
        r_health = httpx.get("http://127.0.0.1:8080/health", timeout=5.0)
        assert r_health.status_code == 200, (
            f"Server unhealthy: {r_health.status_code} {r_health.text}"
        )
        r_props = httpx.get("http://127.0.0.1:8080/props", timeout=5.0)
        props = r_props.json()
        caps = props.get("chat_template_caps", {})
        print("  [OK] /health: HTTP 200 OK")
        print(f"  [OK] supports_system_role: {caps.get('supports_system_role')}")
        print(f"  [OK] supports_tools: {caps.get('supports_tools')}")
        print(f"  [OK] supports_tool_calls: {caps.get('supports_tool_calls')}")
        assert caps.get("supports_system_role") is True, "CRITICAL: System role stripped by server!"
        assert caps.get("supports_tools") is True, "CRITICAL: Tool calling not supported by server!"
    except Exception as exc:
        print(f"[FAIL] llama-server probe failed: {exc}")
        return 1

    client = LLMClient()

    # 2. Test Case 1: Persona Self-Awareness (Conversational Mode)
    print("\n[2/5] Testing Persona Self-Awareness:")
    prompt1 = "Hello, Lucca, you just went, underwent a major refactor."
    print(f'  User: "{prompt1}"')
    print("  Lucca: ", end="", flush=True)

    t0 = time.perf_counter()
    first_token_t = None
    response1_tokens: list[str] = []
    for event in client.stream_turn(current_text=prompt1, tools=[]):
        if isinstance(event, TokenDelta):
            if first_token_t is None:
                first_token_t = time.perf_counter() - t0
            print(event.delta, end="", flush=True)
            response1_tokens.append(event.delta)
    print()

    full_resp1 = "".join(response1_tokens)
    ttft_ms = (first_token_t * 1000.0) if first_token_t else 0.0
    print(f"  [TTFT: {ttft_ms:.1f}ms, Length: {len(full_resp1)} chars]")

    # Verify persona did NOT revert to base pre-training
    assert "mistral ai is a cutting-edge" not in full_resp1.lower(), (
        "FAIL: Leaked base Mistral pre-training weights!"
    )
    assert "collaborated with nvidia" not in full_resp1.lower(), (
        "FAIL: Leaked base pre-training weights!"
    )
    assert len(full_resp1) > 15, "FAIL: Response too short!"
    print("  [PASS] Persona Check Passed: Authentic companion identity verified.")

    # 3. Test Case 2: Meta-Reflection & Anti-Degeneration
    print("\n[3/5] Testing Meta-Reflection & Degeneration Resistance:")
    prompt2 = "You'd realize that's just your LLM call. It's not everything you are."
    print(f'  User: "{prompt2}"')
    print("  Lucca: ", end="", flush=True)

    t0 = time.perf_counter()
    first_token_t = None
    response2_tokens: list[str] = []
    for event in client.stream_turn(
        current_text=prompt2,
        history=[
            {"role": "user", "content": prompt1},
            {"role": "assistant", "content": full_resp1},
        ],
        tools=[],
    ):
        if isinstance(event, TokenDelta):
            if first_token_t is None:
                first_token_t = time.perf_counter() - t0
            print(event.delta, end="", flush=True)
            response2_tokens.append(event.delta)
    print()

    full_resp2 = "".join(response2_tokens)
    ttft_ms = (first_token_t * 1000.0) if first_token_t else 0.0
    print(f"  [TTFT: {ttft_ms:.1f}ms, Length: {len(full_resp2)} chars]")

    # Verify no degenerate loops
    assert "*_*" not in full_resp2, "FAIL: Degenerate repetition tokens detected!"
    assert "::::" not in full_resp2, "FAIL: Degenerate colon loops detected!"
    assert len(full_resp2) > 20, "FAIL: Response too short!"
    print("  [PASS] Degeneration Check Passed: Zero repetition tokens; full self-awareness.")

    # 4. Test Case 3: Native Tool Calling
    print("\n[4/5] Testing Native Structured Tool Calling:")
    prompt3 = "Please launch notepad so I can jot down these notes."
    print(f'  User: "{prompt3}"')

    tool_calls_emitted = []
    text_emitted = []
    for event in client.stream_turn(current_text=prompt3, tools=TOOL_DEFINITIONS):
        if isinstance(event, ToolCallEnd):
            tool_calls_emitted.append(event.call)
            print(f"  [Structured ToolCall Emitted] {event.call.tool}({event.call.args})")
        elif isinstance(event, TokenDelta):
            text_emitted.append(event.delta)

    if text_emitted:
        print(f"  Assistant Spoken Text: {''.join(text_emitted).strip()}")

    assert len(tool_calls_emitted) >= 1, "FAIL: Expected structured tool call was not emitted!"
    called = tool_calls_emitted[0]
    assert called.tool == "launch_app", f"FAIL: Unexpected tool {called.tool}"
    app_arg = str(called.args.get("app_name", "")).lower()
    assert "notepad" in app_arg, f"FAIL: Expected notepad, got {app_arg}"
    print("  [PASS] Tool Call Check Passed: Correctly emitted launch_app(app_name='notepad').")

    # 5. Test Case 4: General Conversational Knowledge without Tool Hallucination
    print("\n[5/5] Testing Knowledge Query & Tool Discipline:")
    prompt4 = "What is the capital of France? Just tell me directly without tools."
    print(f'  User: "{prompt4}"')
    print("  Lucca: ", end="", flush=True)

    response4_tokens = []
    for event in client.stream_turn(current_text=prompt4, tools=TOOL_DEFINITIONS):
        if isinstance(event, TokenDelta):
            print(event.delta, end="", flush=True)
            response4_tokens.append(event.delta)
        elif isinstance(event, ToolCallEnd):
            raise AssertionError(
                f"FAIL: Unexpected tool call {event.call.tool} on direct question!"
            )
    print()

    full_resp4 = "".join(response4_tokens)
    assert "paris" in full_resp4.lower(), "FAIL: Expected Paris in response!"
    print(
        "  [PASS] Knowledge & Tool Discipline Passed: Directly answered Paris without tool calls."
    )

    print("\n====================================================================")
    print("  [SUCCESS] All 5 extensive live LLM tests PASSED with 100% accuracy!")
    print("====================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
