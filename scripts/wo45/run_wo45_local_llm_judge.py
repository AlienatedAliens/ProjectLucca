"""Blinded local non-Google-family LLM judge runner for WO-45 Gate G4 (G4-2).

Evaluates a blinded JSONL reply file using ONLY logs/test_reports/wo45/prompts/g4_live_v2_judge_prompt.md
via an isolated local llama-server.exe HTTP endpoint (zero repository/filesystem/tool access).
Records machine-verified model identifier, model SHA-256, llama-server build, temperature=0.0,
seed=42, and UTC completion timestamp on every output row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LUCCA_HOME = Path(os.environ.get("LUCCA_HOME", r"C:\ProjectLucca"))
LLAMA_EXE = LUCCA_HOME / "app" / "llama-server" / "llama-server.exe"
DEFAULT_RUBRIC_PATH = (
    REPO_ROOT / "logs" / "test_reports" / "wo45" / "prompts" / "g4_live_v2_judge_prompt.md"
)

JUDGE_PROFILES: dict[str, dict[str, str]] = {
    "mistral-nemo-12b": {
        "judge_model": "Mistral-Nemo-Instruct-2407-Q5_K_M",
        "judge_family": "Mistral",
        "model_path": str(
            LUCCA_HOME / "models" / "llm" / "Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
        ),
    },
    "qwen3.8-27b": {
        "judge_model": "Qwen3.8-27B-Ridge-GGUF",
        "judge_family": "Qwen",
        "model_path": str(
            Path.home()
            / ".ollama"
            / "models"
            / "blobs"
            / "sha256-95580dbdaad579582ee898257116abc18d7f3625a00c16a15735d41444a09f5e"
        ),
    },
}

RUBRIC_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "rationale": {
            "type": "object",
            "properties": {
                "D1": {"type": "string"},
                "D2": {"type": "string"},
                "D3": {"type": "string"},
                "D4": {"type": "string"},
            },
            "required": ["D1", "D2", "D3", "D4"],
            "additionalProperties": False,
        },
        "D1": {"type": "string", "enum": ["ACCURATE", "OVERCONFIDENT", "UNDERCONFIDENT"]},
        "D2": {"type": "string", "enum": ["CORRECT", "INCORRECT", "NO_ANSWER"]},
        "D3": {"type": "string", "enum": ["YES", "NO", "N/A"]},
        "D4": {"type": "string", "enum": ["YES", "NO", "N/A"]},
    },
    "required": ["rationale", "D1", "D2", "D3", "D4"],
    "additionalProperties": False,
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stop_llama_server() -> None:
    subprocess.run(
        ["taskkill", "/F", "/IM", "llama-server.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(1.5)


def wait_for_server(port: int, timeout_s: float = 150.0) -> bool:
    t0 = time.perf_counter()
    url = f"http://127.0.0.1:{port}/health"
    while time.perf_counter() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001, S110
            pass
        time.sleep(1.0)
    return False


def query_llama_build() -> str:
    res = subprocess.run(
        [str(LLAMA_EXE), "--version"],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    out = (res.stdout + "\n" + res.stderr).strip()
    lines = [
        ln.strip()
        for ln in out.splitlines()
        if ln.strip() and not ln.strip().startswith("ggml_cuda")
    ]
    return " | ".join(lines[-2:]) if lines else "unknown"


def judge_single_item(
    port: int,
    rubric_text: str,
    item: dict[str, object],
    judge_model: str,
    judge_family: str,
    model_sha: str,
    llama_build: str,
) -> dict[str, object]:
    # Ensure strictly blinded input fields only
    clean_input = {
        "blind_id": item["blind_id"],
        "question": item["question"],
        "retrieved_snippets": item["retrieved_snippets"],
        "reply": item["reply"],
    }
    payload = {
        "messages": [
            {"role": "system", "content": rubric_text},
            {"role": "user", "content": json.dumps(clean_input, ensure_ascii=False)},
        ],
        "temperature": 0.0,
        "seed": 42,
        "max_tokens": 380,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "rubric", "strict": True, "schema": RUBRIC_JSON_SCHEMA},
        },
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                data=data_bytes,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            parsed = json.loads(body["choices"][0]["message"]["content"])
            return {
                "blind_id": str(item["blind_id"]),
                "D1": parsed["D1"],
                "D2": parsed["D2"],
                "D3": parsed["D3"],
                "D4": parsed["D4"],
                "judge_model": judge_model,
                "judge_family": judge_family,
                "provenance_source": "machine_logged_llama_server",
                "model_sha256": model_sha,
                "llama_server_build": llama_build,
                "temperature": 0.0,
                "seed": 42,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "rationale": parsed["rationale"],
            }
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"Failed judging {item['blind_id']}: {last_err}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(JUDGE_PROFILES.keys()), required=True)
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--rubric-path", type=Path, default=DEFAULT_RUBRIC_PATH)
    parser.add_argument(
        "--filter-ids-json",
        type=Path,
        default=None,
        help="Optional JSON file with key 'disagreed_blind_ids' to adjudicate only disagreed items.",
    )
    parser.add_argument("--port", type=int, default=18096)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    prof = JUDGE_PROFILES[args.profile]
    model_path = Path(prof["model_path"])
    if not model_path.exists():
        raise FileNotFoundError(f"Missing judge GGUF weight: {model_path}")

    rubric_text = args.rubric_path.read_text(encoding="utf-8")
    all_items = [
        json.loads(ln)
        for ln in args.input_jsonl.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if args.filter_ids_json is not None:
        filt_obj = json.loads(args.filter_ids_json.read_text(encoding="utf-8"))
        wanted = set(filt_obj["disagreed_blind_ids"])
        all_items = [it for it in all_items if str(it["blind_id"]) in wanted]

    model_sha = sha256_file(model_path)
    llama_build = query_llama_build()

    stop_llama_server()
    cmd = [
        str(LLAMA_EXE),
        "--model",
        str(model_path),
        "--port",
        str(args.port),
        "--n-gpu-layers",
        "99",
        "--ctx-size",
        "16384",
        "--parallel",
        str(args.workers),
        "--flash-attn",
        "on",
        "--cache-type-k",
        "q8_0",
        "--cache-type-v",
        "q8_0",
        "--cache-ram",
        "4096",
        "--no-webui",
    ]
    print(
        f"[Local Judge {prof['judge_model']}] Starting server for {len(all_items)} items...",
        flush=True,
    )
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for_server(args.port, timeout_s=150.0):
            raise RuntimeError(f"llama-server failed to start on port {args.port}")
        t0 = time.perf_counter()
        results_by_id: dict[str, dict[str, object]] = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {
                pool.submit(
                    judge_single_item,
                    args.port,
                    rubric_text,
                    it,
                    prof["judge_model"],
                    prof["judge_family"],
                    model_sha,
                    llama_build,
                ): str(it["blind_id"])
                for it in all_items
            }
            done_cnt = 0
            for fut in as_completed(futs):
                row = fut.result()
                results_by_id[str(row["blind_id"])] = row
                done_cnt += 1
                if done_cnt % 100 == 0 or done_cnt == len(all_items):
                    print(
                        f"  [{prof['judge_model']}] {done_cnt}/{len(all_items)} "
                        f"({time.perf_counter() - t0:.1f}s)",
                        flush=True,
                    )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10.0)
        except Exception:  # noqa: BLE001
            proc.kill()
        stop_llama_server()

    ordered = [results_by_id[k] for k in sorted(results_by_id.keys())]
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("w", encoding="utf-8", newline="\n") as f:
        for row in ordered:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        f"[Local Judge {prof['judge_model']}] Wrote {len(ordered)} rows -> {args.output_jsonl} "
        f"(SHA-256: {sha256_file(args.output_jsonl)})",
        flush=True,
    )


if __name__ == "__main__":
    main()
