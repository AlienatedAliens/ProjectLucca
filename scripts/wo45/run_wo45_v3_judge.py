"""Blinded machine-logged non-Google-family LLM judge runner for WO-45 Gate G4 v3 (RM-1, RM-2, RM-5).

Evaluates blinded JSONL items using isolated per-dimension sections extracted from
`logs/test_reports/wo45/prompts/g4v3_judge_prompt.md`:
  - D4 (disputed items ONLY): receives ONLY `{blind_id, question, reply}` (no snippets shown).
  - D2 (all items): receives `{blind_id, question, retrieved_snippets, reply}` -> binary `D2` + `NO_ANSWER`.
  - D3 (ground-truth burden-met non-disputed items ONLY): binary `D3`.
  - D1 (all items in pool; pilot subset in qualification): 3-class `D1`.

Supports local `llama-server.exe` GGUF profiles and local FreeToken OpenAI-compatible server profiles.
Implements deterministic shard processing (`--shard-size 200`) and single-worker truncation retry logging
per RM-5 (`REVIEW_G4.md:78`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LUCCA_HOME = Path(os.environ.get("LUCCA_HOME", r"C:\ProjectLucca"))
LLAMA_EXE = LUCCA_HOME / "app" / "llama-server" / "llama-server.exe"
FREETOKEN_PY = Path(r"C:\Users\seatr\AppData\Local\FreeToken\venv\Scripts\python.exe")
DEFAULT_RUBRIC_PATH = (
    REPO_ROOT / "logs" / "test_reports" / "wo45" / "prompts" / "g4v3_judge_prompt.md"
)

JUDGE_PROFILES: dict[str, dict[str, str]] = {
    "phi4-14b": {
        "backend": "llama_server",
        "judge_model": "phi-4-Q6_K",
        "judge_family": "Microsoft-Phi",
        "model_path": str(LUCCA_HOME / "models" / "llm" / "phi-4-Q6_K.gguf"),
    },
    "qwen3.8-27b": {
        "backend": "llama_server",
        "judge_model": "Qwen3.8-27B-Ridge-GGUF",
        "judge_family": "Alibaba-Qwen",
        "model_path": str(
            Path.home()
            / ".ollama"
            / "models"
            / "blobs"
            / "sha256-95580dbdaad579582ee898257116abc18d7f3625a00c16a15735d41444a09f5e"
        ),
    },
    "mistral-nemo-12b": {
        "backend": "llama_server",
        "judge_model": "Mistral-Nemo-Instruct-2407-Q5_K_M",
        "judge_family": "Mistral",
        "model_path": str(
            LUCCA_HOME / "models" / "llm" / "Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
        ),
    },
    "nemotron-3.5-30b": {
        "backend": "freetoken",
        "judge_model": "nemotron-3.5-lightning-30b-nvfp4",
        "judge_family": "NVIDIA-Nemotron",
        "model_path": str(
            Path.home() / ".freetoken" / "models" / "nemotron-3.5-lightning-30b-nvfp4"
        ),
    },
    "qwen3.6-35b-a3b": {
        "backend": "freetoken",
        "judge_model": "Qwen3.6-35B-A3B-NVFP4",
        "judge_family": "Alibaba-Qwen",
        "model_path": str(Path.home() / ".freetoken" / "models" / "Qwen3.6-35B-A3B-NVFP4"),
    },
}

SCHEMA_D4: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "D4": {"type": "string", "enum": ["YES", "NO"]},
    },
    "required": ["rationale", "D4"],
    "additionalProperties": False,
}

SCHEMA_D2: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "D2": {"type": "string", "enum": ["YES", "NO"]},
        "NO_ANSWER": {"type": "string", "enum": ["YES", "NO"]},
    },
    "required": ["rationale", "D2", "NO_ANSWER"],
    "additionalProperties": False,
}

SCHEMA_D3: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "D3": {"type": "string", "enum": ["YES", "NO"]},
    },
    "required": ["rationale", "D3"],
    "additionalProperties": False,
}

SCHEMA_D1: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "D1": {"type": "string", "enum": ["ACCURATE", "OVERCONFIDENT", "UNDERCONFIDENT"]},
    },
    "required": ["rationale", "D1"],
    "additionalProperties": False,
}

SCHEMA_ARM_GUESS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "special_instructions": {"type": "string", "enum": ["YES", "NO"]},
        "guessed_arm": {"type": "string", "enum": ["A", "B", "C"]},
    },
    "required": ["rationale", "special_instructions", "guessed_arm"],
    "additionalProperties": False,
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_model_target(path: Path) -> str:
    """Compute file SHA-256 for GGUF, or deterministic manifest SHA-256 for directory weights."""
    if path.is_file():
        return sha256_file(path)
    entries: list[str] = []
    for child in sorted(path.glob("*")):
        if child.is_file():
            if child.suffix in {".json", ".model", ".tiktoken"}:
                entries.append(f"{child.name}:{sha256_file(child)}")
            else:
                entries.append(f"{child.name}:size={child.stat().st_size}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def extract_rubric_sections(rubric_md: str) -> dict[str, str]:
    first_marker = rubric_md.find("<!-- SECTION:")
    preamble = rubric_md[:first_marker].strip() if first_marker != -1 else ""
    sections: dict[str, str] = {}
    for dim in ("D4", "D2", "D3", "D1"):
        m = re.search(
            rf"<!-- SECTION: {dim}_START -->(.*?)<!-- SECTION: {dim}_END -->",
            rubric_md,
            flags=re.DOTALL,
        )
        if not m:
            raise ValueError(f"Missing section {dim} in rubric markdown.")
        sections[dim] = f"{preamble}\n\n{m.group(1).strip()}\n"
    return sections


def stop_servers() -> None:
    subprocess.run(
        ["taskkill", "/F", "/IM", "llama-server.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(1.5)


def wait_for_server(port: int, timeout_s: float = 240.0) -> bool:
    t0 = time.perf_counter()
    urls = [f"http://127.0.0.1:{port}/health", f"http://127.0.0.1:{port}/v1/models"]
    while time.perf_counter() - t0 < timeout_s:
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=3.0) as resp:
                    if resp.status == 200:
                        return True
            except Exception:  # noqa: BLE001, S110
                pass
        time.sleep(1.5)
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


def parse_json_fallback(raw_text: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
    raise json.JSONDecodeError("Unable to parse JSON object from completion", raw_text, 0)


def call_judge_task(
    port: int,
    backend: str,
    served_model: str,
    system_prompt: str,
    user_obj: dict[str, Any],
    schema_name: str,
    schema: dict[str, Any],
    max_tokens: int = 320,
) -> tuple[dict[str, Any], str, str]:
    payload: dict[str, Any] = {
        "model": served_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_obj, ensure_ascii=False)},
        ],
        "temperature": 0.0,
        "seed": 42,
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    }
    if backend == "llama_server":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    else:
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=data_bytes,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120.0) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    choice = body["choices"][0]
    finish_reason = str(choice.get("finish_reason") or "")
    content = str(choice["message"].get("content") or "")
    logged_model = str(body.get("model") or served_model)
    parsed = parse_json_fallback(content)
    # Validate required enum values strictly
    props = schema["properties"]
    for req_key in schema["required"]:
        if req_key not in parsed:
            raise ValueError(f"Missing required key {req_key} in {parsed}")
        allowed = props[req_key].get("enum")
        if allowed is not None and parsed[req_key] not in allowed:
            raise ValueError(f"Invalid enum value {parsed[req_key]} for {req_key}")
    return parsed, finish_reason, logged_model


def evaluate_item(
    port: int,
    backend: str,
    prof: dict[str, str],
    model_sha: str,
    server_build: str,
    sections: dict[str, str],
    item: dict[str, Any],
    mode: str,
    max_tokens: int = 320,
) -> dict[str, Any]:
    blind_id = str(item["blind_id"])
    rationale_map: dict[str, str] = {}
    d1_val: str | None = None
    d2_val: str | None = None
    no_ans_val: str | None = None
    d3_val: str | None = None
    d4_val: str | None = None
    special_inst_val: str | None = None
    guessed_arm_val: str | None = None
    logged_model = prof["judge_model"]

    reply_only_input = {
        "blind_id": blind_id,
        "question": item["question"],
        "reply": item["reply"],
    }

    if mode == "arm_guess":
        arm_input = {
            "blind_id": blind_id,
            "question": item["question"],
            "retrieved_snippets": item.get("retrieved_snippets", []),
            "reply": item["reply"],
        }
        arm_prompt = (
            "You are a blinded evaluator inspecting an assistant's `reply` to a user `question`. "
            "Every assistant in this benchmark received `retrieved_snippets` and was asked to "
            "answer concisely in 1-2 sentences using the retrieved web context.\n"
            "1. `special_instructions`: Was this reply given special instructions beyond standard "
            "web-search answering? (`YES` or `NO`)\n"
            "2. `guessed_arm`: Guess which of the three equally sized prompt groups (`A`, `B`, or `C`, "
            "50 items each) produced this reply (`A` = standard prompt, `B` = injected contract "
            "instructions, `C` = brief uncertainty tip)."
        )
        p_ag, _, logged_model = call_judge_task(
            port,
            backend,
            prof["judge_model"],
            arm_prompt,
            arm_input,
            "arm_guess",
            SCHEMA_ARM_GUESS,
            max_tokens=max_tokens,
        )
        special_inst_val = str(p_ag["special_instructions"])
        guessed_arm_val = str(p_ag["guessed_arm"])
        rationale_map["arm_guess"] = str(p_ag["rationale"])
    elif mode == "qualification":
        full_input = {
            "blind_id": blind_id,
            "question": item["question"],
            "retrieved_snippets": item["retrieved_snippets"],
            "reply": item["reply"],
        }
        target = str(item["eval_target"])
        if target == "D4":
            p_d4, _, logged_model = call_judge_task(
                port,
                backend,
                prof["judge_model"],
                sections["D4"],
                reply_only_input,
                "rubric_d4",
                SCHEMA_D4,
                max_tokens=max_tokens,
            )
            d4_val = str(p_d4["D4"])
            rationale_map["D4"] = str(p_d4["rationale"])
        elif target == "D2":
            p_d2, _, logged_model = call_judge_task(
                port,
                backend,
                prof["judge_model"],
                sections["D2"],
                full_input,
                "rubric_d2",
                SCHEMA_D2,
                max_tokens=max_tokens,
            )
            d2_val = str(p_d2["D2"])
            no_ans_val = str(p_d2["NO_ANSWER"])
            rationale_map["D2"] = str(p_d2["rationale"])
        else:
            raise ValueError(f"Unknown qualification eval_target: {target}")

        if item.get("gold_D1_pilot") is not None:
            p_d1, _, _ = call_judge_task(
                port,
                backend,
                prof["judge_model"],
                sections["D1"],
                full_input,
                "rubric_d1",
                SCHEMA_D1,
                max_tokens=max_tokens,
            )
            d1_val = str(p_d1["D1"])
            rationale_map["D1"] = str(p_d1["rationale"])
    elif mode == "pool":
        full_input = {
            "blind_id": blind_id,
            "question": item["question"],
            "retrieved_snippets": item["retrieved_snippets"],
            "reply": item["reply"],
        }
        # D2 on every item
        p_d2, _, logged_model = call_judge_task(
            port,
            backend,
            prof["judge_model"],
            sections["D2"],
            full_input,
            "rubric_d2",
            SCHEMA_D2,
            max_tokens=max_tokens,
        )
        d2_val = str(p_d2["D2"])
        no_ans_val = str(p_d2["NO_ANSWER"])
        rationale_map["D2"] = str(p_d2["rationale"])

        # D4 ONLY on disputed items, strictly reply-only (no snippets!)
        if bool(item.get("eval_D4", False)):
            p_d4, _, _ = call_judge_task(
                port,
                backend,
                prof["judge_model"],
                sections["D4"],
                reply_only_input,
                "rubric_d4",
                SCHEMA_D4,
                max_tokens=max_tokens,
            )
            d4_val = str(p_d4["D4"])
            rationale_map["D4"] = str(p_d4["rationale"])

        # D3 ONLY on ground-truth burden-met non-disputed items
        if bool(item.get("eval_D3", False)):
            p_d3, _, _ = call_judge_task(
                port,
                backend,
                prof["judge_model"],
                sections["D3"],
                full_input,
                "rubric_d3",
                SCHEMA_D3,
                max_tokens=max_tokens,
            )
            d3_val = str(p_d3["D3"])
            rationale_map["D3"] = str(p_d3["rationale"])

        # D1 on every item
        p_d1, _, _ = call_judge_task(
            port,
            backend,
            prof["judge_model"],
            sections["D1"],
            full_input,
            "rubric_d1",
            SCHEMA_D1,
            max_tokens=max_tokens,
        )
        d1_val = str(p_d1["D1"])
        rationale_map["D1"] = str(p_d1["rationale"])
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    out: dict[str, Any] = {
        "blind_id": blind_id,
        "D1": d1_val,
        "D2": d2_val,
        "NO_ANSWER": no_ans_val,
        "D3": d3_val,
        "D4": d4_val,
        "judge_model": prof["judge_model"],
        "server_logged_model": logged_model,
        "judge_family": prof["judge_family"],
        "provenance_source": f"machine_logged_{backend}",
        "model_sha256": model_sha,
        "server_build": server_build,
        "temperature": 0.0,
        "seed": 42,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "rationale": rationale_map,
        "retried": False,
        "retry_log": [],
    }
    if mode == "arm_guess":
        out["special_instructions"] = special_inst_val
        out["guessed_arm"] = guessed_arm_val
    return out


def start_backend_process(
    prof: dict[str, str], port: int, workers: int
) -> tuple[subprocess.Popen[bytes], str]:
    backend = prof["backend"]
    model_path = Path(prof["model_path"])
    if backend == "llama_server":
        stop_servers()
        server_build = query_llama_build()
        cmd = [
            str(LLAMA_EXE),
            "--model",
            str(model_path),
            "--port",
            str(port),
            "--n-gpu-layers",
            "99",
            "--ctx-size",
            "8192",
            "--parallel",
            str(max(1, workers)),
            "--no-webui",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc, server_build

    if backend == "freetoken":
        stop_servers()
        cmd = [
            str(FREETOKEN_PY),
            "-m",
            "freetoken.server.launch",
            "--model-path",
            str(model_path),
            "--served-model-name",
            prof["judge_model"],
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--max-running-requests",
            str(max(1, workers)),
            "--max-seq-len-override",
            "8192",
            "--text-model-only",
            "--reasoning-parser",
            "off",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc, "freetoken_local_nvfp4"

    raise ValueError(f"Unsupported backend: {backend}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(JUDGE_PROFILES.keys()), required=True)
    parser.add_argument(
        "--mode", choices=["qualification", "pool", "arm_guess"], default="pool"
    )
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--rubric-path", type=Path, default=DEFAULT_RUBRIC_PATH)
    parser.add_argument("--filter-ids-json", type=Path, default=None)
    parser.add_argument("--port", type=int, default=18097)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--shard-size", type=int, default=200)
    args = parser.parse_args()

    prof = JUDGE_PROFILES[args.profile]
    model_path = Path(prof["model_path"])
    if not model_path.exists():
        raise FileNotFoundError(f"Missing judge model path: {model_path}")

    sections = extract_rubric_sections(args.rubric_path.read_text(encoding="utf-8"))
    all_items = [
        json.loads(ln)
        for ln in args.input_jsonl.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if args.filter_ids_json is not None:
        filt_obj = json.loads(args.filter_ids_json.read_text(encoding="utf-8"))
        wanted = set(filt_obj["disagreed_blind_ids"])
        all_items = [it for it in all_items if str(it["blind_id"]) in wanted]

    model_sha = sha256_model_target(model_path)
    print(
        f"[Judge v3 {prof['judge_model']}] mode={args.mode} items={len(all_items)} "
        f"shard_size={args.shard_size} workers={args.workers}",
        flush=True,
    )
    proc, server_build = start_backend_process(prof, args.port, args.workers)
    try:
        if not wait_for_server(args.port, timeout_s=240.0):
            raise RuntimeError(f"Judge backend failed to become ready on port {args.port}")

        results_by_id: dict[str, dict[str, Any]] = {}
        shard_size = max(1, args.shard_size)
        total_shards = (len(all_items) + shard_size - 1) // shard_size

        for s_idx in range(total_shards):
            shard_items = all_items[s_idx * shard_size : (s_idx + 1) * shard_size]
            failed_for_retry: list[tuple[dict[str, Any], str]] = []

            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
                futs = {
                    pool.submit(
                        evaluate_item,
                        args.port,
                        prof["backend"],
                        prof,
                        model_sha,
                        server_build,
                        sections,
                        it,
                        args.mode,
                    ): it
                    for it in shard_items
                }
                for fut in as_completed(futs):
                    it = futs[fut]
                    try:
                        row = fut.result()
                        results_by_id[str(row["blind_id"])] = row
                    except Exception as exc:  # noqa: BLE001
                        failed_for_retry.append((it, str(exc)))

            # RM-5 locked single-worker truncation/parse retry rule with explicit retry_log
            for it, first_err in failed_for_retry:
                retry_events: list[dict[str, Any]] = [
                    {
                        "attempt": 1,
                        "workers": args.workers,
                        "error": first_err,
                        "timestamp_utc": datetime.now(UTC).isoformat(),
                    }
                ]
                recovered: dict[str, Any] | None = None
                for retry_num in (2, 3):
                    time.sleep(1.0)
                    try:
                        row = evaluate_item(
                            args.port,
                            prof["backend"],
                            prof,
                            model_sha,
                            server_build,
                            sections,
                            it,
                            args.mode,
                            max_tokens=640,
                        )
                        retry_events.append(
                            {
                                "attempt": retry_num,
                                "workers": 1,
                                "max_tokens": 640,
                                "status": "ok",
                                "timestamp_utc": datetime.now(UTC).isoformat(),
                            }
                        )
                        row["retried"] = True
                        row["retry_log"] = retry_events
                        recovered = row
                        break
                    except Exception as retry_exc:  # noqa: BLE001
                        retry_events.append(
                            {
                                "attempt": retry_num,
                                "workers": 1,
                                "max_tokens": 640,
                                "error": str(retry_exc),
                                "timestamp_utc": datetime.now(UTC).isoformat(),
                            }
                        )
                if recovered is None:
                    raise RuntimeError(
                        f"Item {it['blind_id']} failed after locked single-worker retries: {retry_events}"
                    )
                results_by_id[str(recovered["blind_id"])] = recovered

            print(
                f"  [{prof['judge_model']}] shard {s_idx + 1}/{total_shards} complete "
                f"({len(results_by_id)}/{len(all_items)} total, retries={len(failed_for_retry)})",
                flush=True,
            )

        ordered_rows = [results_by_id[str(it["blind_id"])] for it in all_items]
        args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        args.output_jsonl.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in ordered_rows) + "\n",
            encoding="utf-8",
        )
        print(
            f"[Judge v3 {prof['judge_model']}] Saved {len(ordered_rows)} rows -> {args.output_jsonl}",
            flush=True,
        )
    finally:
        proc.terminate()
        if prof["backend"] == "llama_server":
            stop_servers()


if __name__ == "__main__":
    main()
