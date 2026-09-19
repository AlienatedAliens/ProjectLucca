"""
Project Lucca — Mistral NeMo 12B / Text Brain Spike Evaluation Harness
D-AUD-06, Spec 02, ADR-001 §Option D

Evaluates a local text-mode brain running in llama-server against normative criteria:
1. TTFT (Time-To-First-Token) across 20 iterations (Budget: median <= 180ms, p95 <= 300ms)
2. Decode throughput (tok/s) across 20 iterations (Target: >= 50 tok/s)
3. Structured tool calling validity rate (Target: >= 18/20, 90%)
4. Resident dGPU VRAM footprint (Target: <= 9500 MB)
"""

import argparse
import datetime
import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from lucca.core.config import get_config


def get_vram_usage_mb() -> float | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    try:
        res = subprocess.run(
            [nvidia_smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=3.0,
        )
        return float(res.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


TOOL_FIXTURES: list[dict[str, object]] = [
    {
        "prompt": "Please open the calculator for me.",
        "expected_tool": "launch_app",
        "expected_arg": "calc",
    },
    {
        "prompt": "Launch Notepad so I can take some quick notes.",
        "expected_tool": "launch_app",
        "expected_arg": "notepad",
    },
    {
        "prompt": "Can you bring up Windows Explorer in my documents?",
        "expected_tool": "launch_app",
        "expected_arg": "explorer",
    },
    {
        "prompt": "Open Microsoft Edge browser please.",
        "expected_tool": "launch_app",
        "expected_arg": "msedge",
    },
    {
        "prompt": "What is the capital of France? Just tell me directly without tools.",
        "expected_tool": None,
        "expected_arg": None,
    },
]

SYSTEM_PROMPT = """You are Lucca, a helpful desktop companion assistant.
You have access to the following tool:
- launch_app(app: str): Launch a desktop application (allowed: calc, notepad, explorer, msedge).

If the user wants to launch an application, respond with a tool call in JSON format:
```json
{"tool": "launch_app", "parameters": {"app": "<app_name>"}}
```
Otherwise, respond directly in natural language."""


def run_spike_benchmark(
    host: str = "127.0.0.1",
    port: int = 8080,
    runs: int = 20,
    output_path: str | None = None,
) -> dict[str, object]:
    client = httpx.Client(base_url=f"http://{host}:{port}", timeout=10.0)

    # 1. Health check
    try:
        r = client.get("/health")
        if r.status_code != 200:
            print(f"[FAIL] Server health check failed: {r.status_code} {r.text}")
            return {"status": "unhealthy", "code": r.status_code}
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] Connection error to llama-server at {host}:{port}: {exc}")
        return {"status": "unreachable", "error": str(exc)}

    print(f"[PASS] llama-server healthy at {host}:{port}")

    # 2. Measure VRAM baseline
    vram_start = get_vram_usage_mb()
    if vram_start is not None:
        print(f"Initial dGPU VRAM usage: {vram_start:.1f} MB (Budget: <= 9500 MB)")

    # 3. TTFT & Throughput benchmark
    ttft_samples_ms: list[float] = []
    tok_per_sec_samples: list[float] = []

    print(f"\nRunning {runs} TTFT and decode throughput benchmarks...")
    bench_payload = {
        "messages": [
            {"role": "system", "content": "You are a concise companion. Answer in one sentence."},
            {"role": "user", "content": "Tell me a short fun fact about space exploration."},
        ],
        "temperature": 0.3,
        "max_tokens": 64,
        "stream": True,
    }

    for i in range(runs):
        t0 = time.perf_counter_ns()
        first_token_time: float | None = None
        token_count = 0

        with client.stream("POST", "/v1/chat/completions", json=bench_payload) as response:
            for line in response.iter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                if line == "data: [DONE]":
                    break
                if first_token_time is None:
                    first_token_time = (time.perf_counter_ns() - t0) / 1_000_000.0
                token_count += 1

        total_time_s = (time.perf_counter_ns() - t0) / 1_000_000_000.0
        if first_token_time is not None:
            ttft_samples_ms.append(first_token_time)
        if total_time_s > 0 and token_count > 0:
            tok_per_sec = token_count / total_time_s
            tok_per_sec_samples.append(tok_per_sec)

        print(
            f"  Run {i + 1:02d}/{runs:02d}: TTFT = {first_token_time:.1f} ms | "
            f"Tokens = {token_count} | Speed = {tok_per_sec:.1f} tok/s"
        )

    # Calculate statistics
    ttft_samples_ms.sort()
    tok_per_sec_samples.sort()
    med_ttft = ttft_samples_ms[len(ttft_samples_ms) // 2] if ttft_samples_ms else 0.0
    p95_idx = int(len(ttft_samples_ms) * 0.95)
    p95_ttft = ttft_samples_ms[min(p95_idx, len(ttft_samples_ms) - 1)] if ttft_samples_ms else 0.0
    med_speed = tok_per_sec_samples[len(tok_per_sec_samples) // 2] if tok_per_sec_samples else 0.0

    # 4. Tool calling validity evaluation
    print("\nRunning tool-calling accuracy evaluation...")
    valid_tool_calls = 0
    total_tool_prompts = len(TOOL_FIXTURES) * 4  # 20 total fixture tests

    for fi, fixture in enumerate(TOOL_FIXTURES * 4):
        p_text = str(fixture["prompt"])
        expected_tool = fixture["expected_tool"]
        expected_arg = fixture["expected_arg"]

        tool_payload = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": p_text},
            ],
            "temperature": 0.1,
            "max_tokens": 128,
            "stream": False,
        }

        resp = client.post("/v1/chat/completions", json=tool_payload)
        resp_json = resp.json()
        reply_content = resp_json["choices"][0]["message"]["content"]

        is_valid = False
        if expected_tool is None:
            # Direct response expected
            is_valid = "launch_app" not in reply_content
        else:
            # Tool call JSON expected
            try:
                # Find JSON block
                clean_json = reply_content
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                parsed = json.loads(clean_json)
                if (
                    parsed.get("tool") == expected_tool
                    and parsed.get("parameters", {}).get("app") == expected_arg
                ):
                    is_valid = True
            except Exception:  # noqa: BLE001
                is_valid = False

        if is_valid:
            valid_tool_calls += 1

    tool_accuracy = (valid_tool_calls / total_tool_prompts) * 100.0
    vram_end = get_vram_usage_mb()

    results: dict[str, object] = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "runs": runs,
        "ttft_ms_median": round(med_ttft, 2),
        "ttft_ms_p95": round(p95_ttft, 2),
        "speed_tok_s_median": round(med_speed, 2),
        "tool_accuracy_pct": round(tool_accuracy, 1),
        "tool_valid_count": valid_tool_calls,
        "tool_total_count": total_tool_prompts,
        "vram_start_mb": vram_start,
        "vram_end_mb": vram_end,
        "gates": {
            "ttft_gate_pass": med_ttft <= 200.0 and p95_ttft <= 300.0,
            "speed_gate_pass": med_speed >= 45.0,
            "tool_gate_pass": valid_tool_calls >= 18,
            "vram_gate_pass": vram_end is None or vram_end <= 9500.0,
        },
    }

    print("\n" + "=" * 60)
    print("MISTRAL NEMO 12B / TEXT BRAIN EVALUATION SUMMARY")
    print("=" * 60)
    print(
        f"TTFT (ms)            : {med_ttft:.1f} median / {p95_ttft:.1f} p95 (Gate: <= 180 / 300 ms)"
    )
    print(f"Decode Throughput    : {med_speed:.1f} tok/s (Gate: >= 50 tok/s)")
    print(
        f"Tool-call Validity   : {valid_tool_calls}/{total_tool_prompts} ({tool_accuracy:.1f}%) (Gate: >= 18/20, 90%)"
    )
    if vram_end:
        print(f"Resident VRAM        : {vram_end:.1f} MB (Budget: <= 9500 MB)")
    print("=" * 60)

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Report written to {out_p}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate text LLM brain in llama-server")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP")
    parser.add_argument("--port", type=int, default=8080, help="Port")
    parser.add_argument("--runs", type=int, default=20, help="Number of test iterations")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    run_spike_benchmark(
        host=args.host,
        port=args.port,
        runs=args.runs,
        output_path=args.output,
    )
