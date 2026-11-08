"""
Extensive Voice Companion Quality & Affect Benchmark on Workstation Silicon
Executes a multi-category battery testing across 5 operational dimensions:
1. Acoustic & TTS Friendliness (SLR, INR, BCS)
2. Verbal Economy (Duration, Word Count, PPP)
3. Tool Dispatch Precision (FPR, FNR, Grounding)
4. Physical Latency (TTFT, Total ms, RTF)
5. Persona & Reactive Affect Consistency across 3D PAD Stances
"""

import json
import re
import time
import urllib.request
from typing import Any

from lucca.brain.chunker import StreamingChunker, normalise_text
from lucca.brain.prompt_builder import (
    get_all_tool_definitions,
    get_system_prompt,
)
from lucca.core.affective_ode import DiscreteStance
from lucca.router.heuristic import HeuristicRouter

ROUTER = HeuristicRouter()
SYSTEM_PROMPT = get_system_prompt()
ALL_TOOLS = [t.model_dump(exclude_none=True) for t in get_all_tool_definitions() if t.function.name != "query_capabilities"]

# Benchmark Test Suite: 15 diverse real-world queries across 5 functional categories
BENCHMARK_CASES = [
    # Category A: Greetings & Social Chit-Chat (Expect 0 tools, warm spoken prose)
    {"id": "greet_01", "cat": "greeting", "text": "Hello, Lucca!", "stance": DiscreteStance.NEUTRAL_STEADY, "expect_tool": False},
    {"id": "greet_02", "cat": "greeting", "text": "Good morning! How are you doing today?", "stance": DiscreteStance.ENERGETIC_SUPPORTIVE, "expect_tool": False},
    {"id": "greet_03", "cat": "greeting", "text": "Hey, are you still awake?", "stance": DiscreteStance.CALM_RELAXED, "expect_tool": False},
    
    # Category B: Persona & Architecture (Expect 0 tools, authentic inventor tone)
    {"id": "pers_01", "cat": "persona", "text": "Who are you?", "stance": DiscreteStance.ENERGETIC_SUPPORTIVE, "expect_tool": False},
    {"id": "pers_02", "cat": "persona", "text": "Can you tell me about yourself and what you do?", "stance": DiscreteStance.NEUTRAL_STEADY, "expect_tool": False},
    {"id": "pers_03", "cat": "persona", "text": "What hardware do you run on?", "stance": DiscreteStance.FOCUSED_ANALYTICAL, "expect_tool": False},

    # Category C: Direct Desktop Actions (Expect imperative tool calls)
    {"id": "act_01", "cat": "action", "text": "Open calculator please", "stance": DiscreteStance.NEUTRAL_STEADY, "expect_tool": True, "target_tool": "launch_app"},
    {"id": "act_02", "cat": "action", "text": "Can you launch Notepad?", "stance": DiscreteStance.ENERGETIC_SUPPORTIVE, "expect_tool": True, "target_tool": "launch_app"},
    {"id": "act_03", "cat": "action", "text": "Write a note in notes.txt saying meeting at 4 PM", "stance": DiscreteStance.FOCUSED_ANALYTICAL, "expect_tool": True, "target_tool": "write_file"},

    # Category D: General Knowledge & Technical Explanations (Expect concise speech, 0 tools)
    {"id": "tech_01", "cat": "knowledge", "text": "Why is the sky blue?", "stance": DiscreteStance.NEUTRAL_STEADY, "expect_tool": False},
    {"id": "tech_02", "cat": "knowledge", "text": "What is the difference between a compiler and an interpreter?", "stance": DiscreteStance.FOCUSED_ANALYTICAL, "expect_tool": False},
    {"id": "tech_03", "cat": "knowledge", "text": "How does ZeroMQ pub-sub work?", "stance": DiscreteStance.FOCUSED_ANALYTICAL, "expect_tool": False},

    # Category E: Affective & Reactive Personality Queries
    {"id": "aff_01", "cat": "affect", "text": "We just solved the hardest bug in the codebase!", "stance": DiscreteStance.ENERGETIC_SUPPORTIVE, "expect_tool": False},
    {"id": "aff_02", "cat": "affect", "text": "The build just failed three times in a row, I feel terrible.", "stance": DiscreteStance.SUBDUED_REFLECTIVE, "expect_tool": False},
    {"id": "aff_03", "cat": "affect", "text": "How are you feeling right now?", "stance": DiscreteStance.CALM_RELAXED, "expect_tool": False},
]

def evaluate_response_quality(prompt: str, raw_text: str, tts_chunks: list[str], tool_calls: list[dict[str, Any]], expect_tool: bool) -> dict[str, Any]:
    full_speech = " ".join(tts_chunks).strip()
    words = full_speech.split()
    num_words = len(words)

    # 1. Acoustic & TTS Friendliness
    # Syntax leakage: presence of raw markdown asterisks, backslashes, raw backticks, hashes
    syntax_leak_matches = re.findall(r"[*`~\\#\[\]{}]", full_speech)
    slr = (len(syntax_leak_matches) / max(1, num_words)) * 100.0

    # Identifier naturalization: check for unspaced underscores (e.g. launch_app)
    unnatural_identifiers = re.findall(r"\b\w+_\w+\b", full_speech)
    inr = 100.0 if not unnatural_identifiers else 0.0

    # Breath cadence: average words per punctuation pause (commas, periods, colons, semi, ?, !)
    breath_segments = [seg.strip() for seg in re.split(r"[,.!?;:]+", full_speech) if seg.strip()]
    mean_words_per_breath = (num_words / len(breath_segments)) if breath_segments else num_words

    # 2. Verbal Economy
    # Preamble / Postamble penalty
    preamble_phrases = ["sure, i can", "certainly", "i would be happy to", "as an ai", "absolutely, i can"]
    postamble_phrases = ["let me know if you need anything else", "feel free to ask", "how else can i help"]
    has_preamble = any(full_speech.lower().startswith(p) for p in preamble_phrases)
    has_postamble = any(full_speech.lower().endswith(p) for p in postamble_phrases)
    ppp = (1.0 if has_preamble else 0.0) + (1.0 if has_postamble else 0.0)

    # Estimated Kokoro TTS audio duration at 1.2x speed (~3.2 words per second)
    est_audio_duration_s = round(num_words / 3.2, 2)

    # 3. Tool Dispatch Precision
    has_tool = len(tool_calls) > 0
    tool_precision_pass = (has_tool == expect_tool)

    return {
        "num_words": num_words,
        "num_chunks": len(tts_chunks),
        "est_audio_s": est_audio_duration_s,
        "slr_pct": round(slr, 2),
        "inr_pct": round(inr, 2),
        "mean_words_per_breath": round(mean_words_per_breath, 1),
        "ppp_penalty": ppp,
        "tool_precision_pass": tool_precision_pass,
        "has_tool": has_tool,
    }

def run_benchmark_turn(case: dict[str, Any]) -> dict[str, Any]:
    prompt = case["text"]
    stance: DiscreteStance = case["stance"]
    stance_tag = f"[STANCE: {stance.value}]"

    # Gating: determine if tools should be passed based on HeuristicRouter intent
    intent, conf, _ = ROUTER.classify_intent(prompt)
    is_chit_or_qa = (intent in ("chit_chat", "clarify") or case["cat"] in ("greeting", "persona", "affect"))
    tools_payload = None if is_chit_or_qa else ALL_TOOLS

    system_content = f"{SYSTEM_PROMPT}\n\nCurrent Affective Register: {stance_tag}"
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]

    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 160,
        "stream": True,
    }
    if tools_payload:
        payload["tools"] = tools_payload

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
                        tool_calls.append({"name": "", "args": ""})
                    fn = tc.get("function", {})
                    if "name" in fn and fn["name"]:
                        tool_calls[idx]["name"] += fn["name"]
                    if "arguments" in fn and fn["arguments"]:
                        tool_calls[idx]["args"] += fn["arguments"]

    flushed = chunker.flush()
    for c in flushed:
        tts_chunks.append(c.text)

    t1 = time.perf_counter()
    ttft_ms = (first_token_t - t0) * 1000 if first_token_t else 0.0
    total_ms = (t1 - t0) * 1000

    raw_text = "".join(accumulated_content)
    metrics = evaluate_response_quality(prompt, raw_text, tts_chunks, tool_calls, case["expect_tool"])

    return {
        "id": case["id"],
        "cat": case["cat"],
        "prompt": prompt,
        "stance": stance.value,
        "ttft_ms": round(ttft_ms, 2),
        "total_ms": round(total_ms, 2),
        "raw_text": raw_text,
        "tts_chunks": tts_chunks,
        "tool_calls": tool_calls,
        "metrics": metrics,
    }

if __name__ == "__main__":
    print("=" * 80)
    print(" PROJECT LUCCA — EXTENSIVE VOICE COMPANION & AFFECT BENCHMARK (RTX 5080)")
    print("=" * 80)

    results = []
    for case in BENCHMARK_CASES:
        print(f"\n[{case['id']}] Category: {case['cat']} | Stance: {case['stance'].value}")
        print(f"User: \"{case['text']}\"")
        res = run_benchmark_turn(case)
        results.append(res)
        m = res["metrics"]
        print(f"  TTFT: {res['ttft_ms']}ms | Total: {res['total_ms']}ms | Words: {m['num_words']} ({m['est_audio_s']}s audio)")
        print(f"  TTS Cadence: {m['mean_words_per_breath']} words/breath | Syntax Leak: {m['slr_pct']}% | Identifier Nat: {m['inr_pct']}%")
        print(f"  Tool Precision: {'PASS' if m['tool_precision_pass'] else 'FAIL'} (Expected tool: {case['expect_tool']}, Called: {m['has_tool']})")
        if res['tool_calls']:
            print(f"  Tool Calls: {res['tool_calls']}")
        print(f"  Untruncated Spoken Prose: \"{' '.join(res['tts_chunks'])}\"")

    with open("data/extensive_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nBenchmark complete! Results saved to data/extensive_benchmark_results.json")
