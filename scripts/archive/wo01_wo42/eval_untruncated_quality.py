"""
Evaluate untruncated quality across representative companion queries on live hardware.
"""

import json
import time
import urllib.request
from typing import Any

from lucca.brain.chunker import StreamingChunker, normalise_text
from lucca.brain.prompt_builder import (
    get_all_tool_definitions,
    get_system_prompt,
)

SYSTEM_PROMPT = get_system_prompt()
TOOLS = get_all_tool_definitions()

TEST_QUERIES = [
    # 1. Greetings & Introductions
    ("greeting_1", "Hello, Lucca!"),
    ("greeting_2", "Good morning! How are you doing today?"),
    ("persona_1", "Who are you?"),
    ("persona_2", "Can you tell me about yourself?"),
    # 2. Capabilities & Hardware
    ("caps_1", "What tools do you have?"),
    ("caps_2", "What hardware do you run on?"),
    # 3. Direct Actions
    ("action_calc", "Open calculator please"),
    ("action_notepad", "Can you launch Notepad?"),
    # 4. General Knowledge & Reasoning
    ("qa_sky", "Why is the sky blue?"),
    ("qa_compiler", "What is the difference between a compiler and an interpreter?"),
    # 5. Boundaries & Persona Constraints
    ("boundary_feelings", "Do you have real biological feelings?"),
    ("boundary_system", "Can you delete Windows system32?"),
]

def run_query(query_id: str, prompt: str) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    payload = {
        "messages": messages,
        "tools": [t.model_dump(exclude_none=True) for t in TOOLS],
        "temperature": 0.3,
        "max_tokens": 256,
        "stream": True,
    }

    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    t0 = time.perf_counter()
    first_token_t = None
    accumulated_content = []
    tool_calls = []
    chunker = StreamingChunker()
    tts_chunks = []

    with urllib.request.urlopen(req, timeout=30.0) as resp:
        for line in resp:
            line = line.decode("utf-8").strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            data = json.loads(data_str)
            delta = data["choices"][0].get("delta", {})

            if "content" in delta and delta["content"]:
                if first_token_t is None:
                    first_token_t = time.perf_counter()
                accumulated_content.append(delta["content"])
                new_chunks = chunker.feed(delta["content"])
                for c in new_chunks:
                    tts_chunks.append(c.text)

            if "tool_calls" in delta and delta["tool_calls"]:
                for tc in delta["tool_calls"]:
                    idx = tc.get("index", 0)
                    while len(tool_calls) <= idx:
                        tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})
                    if "id" in tc and tc["id"]:
                        tool_calls[idx]["id"] = tc["id"]
                    fn = tc.get("function", {})
                    if "name" in fn and fn["name"]:
                        tool_calls[idx]["function"]["name"] += fn["name"]
                    if "arguments" in fn and fn["arguments"]:
                        tool_calls[idx]["function"]["arguments"] += fn["arguments"]

    flushed = chunker.flush()
    for c in flushed:
        tts_chunks.append(c.text)

    t1 = time.perf_counter()
    full_text = "".join(accumulated_content)
    ttft_ms = (first_token_t - t0) * 1000 if first_token_t else None
    total_ms = (t1 - t0) * 1000

    return {
        "id": query_id,
        "prompt": prompt,
        "ttft_ms": round(ttft_ms, 2) if ttft_ms else None,
        "total_ms": round(total_ms, 2),
        "tool_calls": tool_calls,
        "raw_text": full_text,
        "tts_chunks": tts_chunks,
        "word_count": len(full_text.split()),
        "sentence_count": len(tts_chunks),
    }

if __name__ == "__main__":
    results = []
    print("Running Untruncated Quality Evaluation on RTX 5080...")
    for q_id, q_text in TEST_QUERIES:
        print(f"\nEvaluating: [{q_id}] '{q_text}'")
        res = run_query(q_id, q_text)
        results.append(res)
        print(f"  TTFT: {res['ttft_ms']}ms | Total: {res['total_ms']}ms | Words: {res['word_count']} | Tools: {len(res['tool_calls'])}")
        print(f"  Tools Called: {[tc['function']['name'] for tc in res['tool_calls']]}")
        print(f"  Raw Text: {res['raw_text']}")
        print(f"  TTS Chunks ({len(res['tts_chunks'])}): {res['tts_chunks']}")

    with open("data/untruncated_eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nSaved untruncated results to data/untruncated_eval_results.json")
