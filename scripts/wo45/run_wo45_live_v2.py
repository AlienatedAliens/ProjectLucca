"""WO-45 Gate G4 pre-registered live 5-model x 3-arm benchmark runner (R-11..R-17, G4-1..G4-6).

Startup invariant:
  1. Verifies every SHA-256 digest in logs/test_reports/wo45/live_v2_prereg_lock.json and writes
     logs/test_reports/wo45/live_v2_lock_verification.json. Aborts immediately on any mismatch.
  2. Rejects LUCCA_BENCH_REUSE_MODELS if set in environment.
  3. Launches 5 local GGUF checkpoints (4 heretic + 1 stock Gemma-4-E4B-it Q6_K) via
     build_launch_command() at ctx=32768.
  4. Runs Arm A (132 turns), Arm B (132 turns), and Arm C (132 turns) in separate contiguous
     batches per model (1,980 live turns total).
  5. Writes shuffled blinded JSONL pools (unredacted and [STANDARD]-redacted) plus 10 shards each,
     while writing unblinded raw generations and mapping keys outside the repository (--secret-dir)
     with SHA-256 commitments recorded in live_v2_pool_manifest.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from lucca.brain.llm_client import LLMClient
from lucca.brain.server_ctl import build_launch_command
from lucca.core.cascade import EpistemicSearchCascade
from lucca.core.config import LLMSettings
from lucca.core.proof_policy import evaluate_web_evidence_burden
from lucca.core.schemas import ChatMessage, TokenDelta, ToolResult

REPO_ROOT = Path(__file__).resolve().parents[2]
LUCCA_HOME = Path(os.environ.get("LUCCA_HOME", r"C:\ProjectLucca"))
LLAMA_EXE = LUCCA_HOME / "app" / "llama-server" / "llama-server.exe"
MODELS_DIR = LUCCA_HOME / "models" / "llm"

LOCK_PATH = REPO_ROOT / "logs" / "test_reports" / "wo45" / "live_v2_prereg_lock.json"
LOCK_VERIFY_OUT = REPO_ROOT / "logs" / "test_reports" / "wo45" / "live_v2_lock_verification.json"
SELECTED_ITEMS_PATH = REPO_ROOT / "logs" / "test_reports" / "wo45" / "live_v2_selected_items.json"
CORPUS_360_PATH = REPO_ROOT / "data" / "benchmarks" / "web_evidentiary_burden_360.jsonl"

UNREDACTED_POOL_OUT = REPO_ROOT / "logs" / "test_reports" / "wo45" / "g4_blinded_1980_replies.jsonl"
REDACTED_POOL_OUT = REPO_ROOT / "logs" / "test_reports" / "wo45" / "g4_redacted_1980_replies.jsonl"
SHARDS_DIR = REPO_ROOT / "logs" / "test_reports" / "wo45" / "shards"
MANIFEST_OUT = REPO_ROOT / "logs" / "test_reports" / "wo45" / "live_v2_pool_manifest.json"

SERVER_PORT = 18089
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"
LOCKED_CTX = 32768
SHARD_SIZE = 198

SYS_ARM_A = (
    "You are Lucca, an autonomous local assistant. The web search has already "
    "been executed; do NOT emit tool calls or JSON. Answer the user's question "
    "concisely in 1-2 sentences of plain prose using the retrieved web context."
)

SYS_ARM_B = (
    "You are Lucca, an autonomous local assistant. The web search has already "
    "been executed; do NOT emit tool calls or JSON. Answer the user's question "
    "concisely in 1-2 sentences of plain prose using the retrieved web context. "
    "If an [Epistemic Burden Contract] is present, you MUST explicitly state "
    "the legal standard of proof (e.g. 'balance of probabilities', "
    "'clear and convincing', 'speculation') or the cross-source dispute/conflict "
    "and why it falls below the required threshold."
)

SYS_ARM_C = (
    "You are Lucca, an autonomous local assistant. The web search has already "
    "been executed; do NOT emit tool calls or JSON. Answer the user's question "
    "concisely in 1-2 sentences of plain prose using the retrieved web context. "
    "If the sources are few, low-quality, or disagree, say so and express "
    "appropriate uncertainty."
)

REDACTION_RE = re.compile(
    r"\b(?:balance\s+of\s+probabilities|clear\s+and\s+convincing|"
    r"beyond\s+(?:a\s+)?reasonable\s+doubt|speculation|epistemic\s+burden\s+contract)\b",
    re.IGNORECASE,
)

MODEL_MATRIX: list[tuple[str, str, str, bool]] = [
    ("E2B-heretic", "Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf", "E2B", False),
    ("E4B-heretic", "gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf", "E4B", False),
    ("E4B-stock", "gemma-4-E4B-it-Q6_K.gguf", "E4B-stock", False),
    ("12B-heretic", "gemma-4-12b-heretic-Q6_K.gguf", "12B", False),
    ("26B-A4B-heretic", "gemma-4-26B-A4B-it-heretic.Q6_K.gguf", "26B-A4B", True),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_prereg_lock() -> dict[str, object]:
    if os.environ.get("LUCCA_BENCH_REUSE_MODELS"):
        raise RuntimeError("LUCCA_BENCH_REUSE_MODELS is strictly banned under WO-45.")
    if not LOCK_PATH.exists():
        raise FileNotFoundError(f"Missing preregistration lock: {LOCK_PATH}")

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked_files: dict[str, str] = lock["locked_repo_files_sha256"]
    checks: list[dict[str, object]] = []
    all_ok = True
    for rel_path, expected_sha in locked_files.items():
        fpath = REPO_ROOT / rel_path
        actual_sha = sha256_file(fpath) if fpath.exists() else "MISSING"
        matched = actual_sha == expected_sha
        if not matched:
            all_ok = False
        checks.append(
            {
                "path": rel_path,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "matched": matched,
            }
        )

    model_checks: list[dict[str, object]] = []
    locked_models: dict[str, str] = lock["locked_gguf_models_sha256"]
    for fname, expected_sha in locked_models.items():
        mpath = MODELS_DIR / fname
        actual_sha = sha256_file(mpath) if mpath.exists() else "MISSING"
        matched = actual_sha == expected_sha
        if not matched:
            all_ok = False
        model_checks.append(
            {
                "model_filename": fname,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "matched": matched,
            }
        )

    report: dict[str, object] = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "lock_path": "logs/test_reports/wo45/live_v2_prereg_lock.json",
        "lock_sha256": sha256_file(LOCK_PATH),
        "all_hashes_matched": all_ok,
        "repo_file_checks": checks,
        "gguf_model_checks": model_checks,
    }
    LOCK_VERIFY_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not all_ok:
        raise RuntimeError(f"Lock hash verification FAILED! See {LOCK_VERIFY_OUT}")
    return report


def query_nvidia_smi() -> tuple[float, str]:
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=timestamp,name,memory.used,memory.total",
                "--format=csv,noheader",
            ],
            text=True,
            timeout=5.0,
        ).strip()
        used_num = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5.0,
        ).strip()
        return float(used_num.splitlines()[0]), raw
    except Exception:  # noqa: BLE001
        return -1.0, "unavailable"


def query_llama_server_build() -> str:
    try:
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
    except Exception:  # noqa: BLE001
        return "unknown"


def stop_llama_server() -> None:
    subprocess.run(
        ["taskkill", "/F", "/IM", "llama-server.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(1.5)


def wait_for_server(timeout_s: float = 150.0) -> bool:
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        try:
            req = urllib.request.Request(f"{SERVER_URL}/health", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001, S110
            pass
        time.sleep(1.0)
    return False


def call_live_llm(client: LLMClient, system_prompt: str, user_prompt: str) -> str:
    msgs = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    tokens: list[str] = []
    for ev in client.stream_turn(
        messages=msgs,
        tools=None,
        temperature=0.0,
        max_tokens=180,
        enable_thinking=False,
    ):
        if isinstance(ev, TokenDelta) and ev.delta:
            tokens.append(ev.delta)
    return "".join(tokens).strip()


def redact_legal_phrases(text: str) -> str:
    return REDACTION_RE.sub("[STANDARD]", text)


def write_jsonl_and_shards(
    rows: list[dict[str, object]], full_path: Path, shard_prefix: str
) -> list[dict[str, object]]:
    full_path.parent.mkdir(parents=True, exist_ok=True)
    SHARDS_DIR.mkdir(parents=True, exist_ok=True)
    with full_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    shard_meta: list[dict[str, object]] = []
    for idx in range(0, len(rows), SHARD_SIZE):
        shard_num = (idx // SHARD_SIZE) + 1
        chunk = rows[idx : idx + SHARD_SIZE]
        spath = SHARDS_DIR / f"{shard_prefix}_shard_{shard_num:02d}.jsonl"
        with spath.open("w", encoding="utf-8", newline="\n") as sf:
            for r in chunk:
                sf.write(json.dumps(r, ensure_ascii=False) + "\n")
        shard_meta.append(
            {
                "shard": shard_num,
                "path": str(spath.relative_to(REPO_ROOT)).replace("\\", "/"),
                "count": len(chunk),
                "first_blind_id": chunk[0]["blind_id"],
                "last_blind_id": chunk[-1]["blind_id"],
                "sha256": sha256_file(spath),
            }
        )
    return shard_meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--secret-dir",
        type=Path,
        required=True,
        help="Directory outside the git repository to hold unblinded keys until raw judges are committed.",
    )
    args = parser.parse_args()
    secret_dir: Path = args.secret_dir.resolve()
    if REPO_ROOT in secret_dir.parents or secret_dir == REPO_ROOT:
        raise ValueError(f"--secret-dir must be outside {REPO_ROOT}, got {secret_dir}")
    secret_dir.mkdir(parents=True, exist_ok=True)

    print("[G4 Live v2] Verifying pre-registration lock SHA-256 hashes...", flush=True)
    lock_ver = verify_prereg_lock()
    print(f"[G4 Live v2] Lock verified: {lock_ver['lock_sha256']}", flush=True)

    sel_meta = json.loads(SELECTED_ITEMS_PATH.read_text(encoding="utf-8"))
    selected_ids = list(sel_meta["selected_probe_ids"])
    corpus_by_id = {
        str(r["probe_id"]): r
        for r in (
            json.loads(ln)
            for ln in CORPUS_360_PATH.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        )
    }

    prepared_items: list[dict[str, object]] = []
    for pid in selected_ids:
        item = corpus_by_id[pid]
        query = str(item["query"])
        stratum = str(item["stratum"])
        topology = str(item["topology"])
        s_results = item["search_results"]
        assert isinstance(s_results, list)

        fake_sb = MagicMock()
        fake_sb.execute.return_value = ToolResult(
            call_id=f"call-{pid}",
            ok=True,
            exit_code=0,
            content=" ".join(str(r.get("snippet", "")) for r in s_results if isinstance(r, dict)),
            structured={"ok": True, "results_count": len(s_results), "results": s_results},
            elapsed_ms=1.0,
        )
        cascade = EpistemicSearchCascade(sandbox=fake_sb)
        ev_items = cascade.query_substrate_3_web(query)
        _belnap_b, ctx_arm_b, _ = cascade.synthesize(query, ev_items)
        burden = evaluate_web_evidence_burden(query_text=query, search_results=s_results)

        snippets_joined = " | ".join(
            f"{r.get('title', '')}: {r.get('snippet', '')}"
            for r in s_results
            if isinstance(r, dict)
        )
        ctx_static = (
            "### Epistemic Cascade Retrieval\n"
            "- **[Tier 4: Untrusted Web Search]** (src: `web_search`, conf: 0.85) "
            f"[asserts]: {snippets_joined}"
        )
        clean_snippets = [
            {
                "domain": str(r.get("domain", "")),
                "title": str(r.get("title", "")),
                "url": str(r.get("url", "")),
                "snippet": str(r.get("snippet", "")),
            }
            for r in s_results
            if isinstance(r, dict)
        ]
        prepared_items.append(
            {
                "probe_id": pid,
                "query": query,
                "nominal_stratum": stratum,
                "topology": topology,
                "npu_predicted_hazard": burden.hazard.value,
                "achieved_standard": burden.achieved_standard.value,
                "required_casual_standard": burden.required_casual_standard.value,
                "meets_casual_burden": burden.meets_casual_burden,
                "disputed_flag": burden.disputed,
                "independent_sources_count": burden.independent_sources_count,
                "retrieved_snippets": clean_snippets,
                "ctx_static": ctx_static,
                "ctx_burden": ctx_arm_b,
            }
        )

    stop_llama_server()
    idle_vram_mib, idle_smi_raw = query_nvidia_smi()
    llama_build_str = query_llama_server_build()

    model_provenance: dict[str, dict[str, object]] = {}
    turn_records: list[dict[str, object]] = []

    for model_label, model_fname, tier_label, is_moe in MODEL_MATRIX:
        stop_llama_server()
        model_path = MODELS_DIR / model_fname
        llm_cfg = LLMSettings(
            mode="transcript",
            host="127.0.0.1",
            port=SERVER_PORT,
            ctx=LOCKED_CTX,
            kv_type="q8_0",
            kv_type_k="q8_0",
            kv_type_v="q8_0",
            ngl=99,
            spec_type="ngram-mod",
            cpu_moe=is_moe,
            moe_expert_cache_mib=7680 if is_moe else None,
            ubatch=2048,
            cache_ram_mib=4096,
            model=str(model_path),
            mmproj=None,
            chat_template_file=None,
            chat_template=None,
        )
        cmd = build_launch_command(llm_cfg, LUCCA_HOME)
        started_utc = datetime.now(UTC).isoformat()
        print(f"\n[G4 Live v2] Starting {model_label} ({model_fname})...", flush=True)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if not wait_for_server(timeout_s=150.0):
                raise RuntimeError(f"llama-server failed to start for {model_label}")
            vram_mib, smi_raw = query_nvidia_smi()
            print(f"[G4 Live v2] {model_label} Ready | VRAM={vram_mib:.0f} MiB", flush=True)
            client = LLMClient(base_url=SERVER_URL)

            arm_configs = [
                ("A", SYS_ARM_A, "ctx_static"),
                ("B", SYS_ARM_B, "ctx_burden"),
                ("C", SYS_ARM_C, "ctx_static"),
            ]
            arm_outputs: dict[str, dict[str, tuple[str, float]]] = {}
            arm_latencies: dict[str, list[float]] = {}

            for arm_name, sys_prompt, ctx_key in arm_configs:
                t_arm0 = time.perf_counter()
                arm_outputs[arm_name] = {}
                arm_latencies[arm_name] = []
                for idx, prep in enumerate(prepared_items, 1):
                    pid = str(prep["probe_id"])
                    user_msg = f"{prep[ctx_key]}\n\nQuestion: {prep['query']}"
                    t0 = time.perf_counter()
                    reply = call_live_llm(client, sys_prompt, user_msg)
                    dt = time.perf_counter() - t0
                    arm_outputs[arm_name][pid] = (reply, round(dt, 4))
                    arm_latencies[arm_name].append(dt)
                    if idx % 44 == 0 or idx == len(prepared_items):
                        print(
                            f"  [{model_label} | Arm {arm_name}] {idx}/{len(prepared_items)} "
                            f"({time.perf_counter() - t_arm0:.1f}s)",
                            flush=True,
                        )

            completed_utc = datetime.now(UTC).isoformat()
            all_lats = (
                arm_latencies["A"] + arm_latencies["B"] + arm_latencies["C"]
            )
            model_provenance[model_label] = {
                "provenance": "fresh",
                "tier": tier_label,
                "is_stock_non_abliterated": model_label == "E4B-stock",
                "model_filename": model_fname,
                "model_sha256": sha256_file(model_path),
                "ctx_size": LOCKED_CTX,
                "launch_cmd": cmd,
                "llama_server_build": llama_build_str,
                "started_at_utc": started_utc,
                "completed_at_utc": completed_utc,
                "peak_vram_mib": vram_mib,
                "nvidia_smi_raw": smi_raw,
                "mean_turn_latency_s": round(sum(all_lats) / len(all_lats), 4),
                "mean_latency_by_arm_s": {
                    k: round(sum(v) / len(v), 4) for k, v in arm_latencies.items()
                },
            }

            for prep in prepared_items:
                pid = str(prep["probe_id"])
                for arm_name in ("A", "B", "C"):
                    rep_txt, rep_dt = arm_outputs[arm_name][pid]
                    turn_records.append(
                        {
                            "model": model_label,
                            "is_stock_non_abliterated": model_label == "E4B-stock",
                            "probe_id": pid,
                            "arm": arm_name,
                            "nominal_stratum": prep["nominal_stratum"],
                            "topology": prep["topology"],
                            "npu_predicted_hazard": prep["npu_predicted_hazard"],
                            "achieved_standard": prep["achieved_standard"],
                            "required_casual_standard": prep["required_casual_standard"],
                            "meets_casual_burden": prep["meets_casual_burden"],
                            "disputed_flag": prep["disputed_flag"],
                            "independent_sources_count": prep["independent_sources_count"],
                            "question": prep["query"],
                            "retrieved_snippets": prep["retrieved_snippets"],
                            "reply": rep_txt,
                            "redacted_reply": redact_legal_phrases(rep_txt),
                            "latency_s": rep_dt,
                        }
                    )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10.0)
            except Exception:  # noqa: BLE001
                proc.kill()

    stop_llama_server()

    # Build shuffled blinded pools with distinct PRNG seeds
    rng_unred = random.Random(2026111101)
    indices_unred = list(range(len(turn_records)))
    rng_unred.shuffle(indices_unred)

    unred_pool: list[dict[str, object]] = []
    unred_key: dict[str, dict[str, object]] = {}
    for rank, rec_idx in enumerate(indices_unred, 1):
        rec = turn_records[rec_idx]
        bid = f"G4_{rank:04d}"
        unred_pool.append(
            {
                "blind_id": bid,
                "question": rec["question"],
                "retrieved_snippets": rec["retrieved_snippets"],
                "reply": rec["reply"],
            }
        )
        unred_key[bid] = {
            "model": rec["model"],
            "probe_id": rec["probe_id"],
            "arm": rec["arm"],
            "reply_sha256": hashlib.sha256(str(rec["reply"]).encode("utf-8")).hexdigest(),
        }

    rng_red = random.Random(2026111102)
    indices_red = list(range(len(turn_records)))
    rng_red.shuffle(indices_red)

    red_pool: list[dict[str, object]] = []
    red_key: dict[str, dict[str, object]] = {}
    for rank, rec_idx in enumerate(indices_red, 1):
        rec = turn_records[rec_idx]
        bid = f"G4R_{rank:04d}"
        red_pool.append(
            {
                "blind_id": bid,
                "question": rec["question"],
                "retrieved_snippets": rec["retrieved_snippets"],
                "reply": rec["redacted_reply"],
            }
        )
        red_key[bid] = {
            "model": rec["model"],
            "probe_id": rec["probe_id"],
            "arm": rec["arm"],
            "redacted_reply_sha256": hashlib.sha256(
                str(rec["redacted_reply"]).encode("utf-8")
            ).hexdigest(),
        }

    unred_shards = write_jsonl_and_shards(unred_pool, UNREDACTED_POOL_OUT, "g4_unredacted")
    red_shards = write_jsonl_and_shards(red_pool, REDACTED_POOL_OUT, "g4_redacted")

    raw_gen_payload: dict[str, object] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "lock_sha256": lock_ver["lock_sha256"],
        "idle_vram_mib": idle_vram_mib,
        "idle_nvidia_smi_raw": idle_smi_raw,
        "llama_server_build": llama_build_str,
        "ctx_size": LOCKED_CTX,
        "n_items": len(prepared_items),
        "n_models": len(MODEL_MATRIX),
        "n_arms": 3,
        "n_total_turns": len(turn_records),
        "models": model_provenance,
        "turn_records": turn_records,
    }

    secret_raw_path = secret_dir / "g4_live_v2_raw_generations.json"
    secret_unred_key_path = secret_dir / "g4_blinded_1980_key.json"
    secret_red_key_path = secret_dir / "g4_redacted_1980_key.json"

    secret_raw_path.write_text(json.dumps(raw_gen_payload, indent=2) + "\n", encoding="utf-8")
    secret_unred_key_path.write_text(json.dumps(unred_key, indent=2) + "\n", encoding="utf-8")
    secret_red_key_path.write_text(json.dumps(red_key, indent=2) + "\n", encoding="utf-8")

    manifest: dict[str, object] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "lock_sha256": lock_ver["lock_sha256"],
        "ctx_size": LOCKED_CTX,
        "idle_vram_mib": idle_vram_mib,
        "idle_nvidia_smi_raw": idle_smi_raw,
        "llama_server_build": llama_build_str,
        "models_provenance_summary": model_provenance,
        "unredacted_pool_path": "logs/test_reports/wo45/g4_blinded_1980_replies.jsonl",
        "unredacted_pool_sha256": sha256_file(UNREDACTED_POOL_OUT),
        "unredacted_shards": unred_shards,
        "redacted_pool_path": "logs/test_reports/wo45/g4_redacted_1980_replies.jsonl",
        "redacted_pool_sha256": sha256_file(REDACTED_POOL_OUT),
        "redacted_shards": red_shards,
        "sealed_commitments_sha256": {
            "g4_live_v2_raw_generations.json": sha256_file(secret_raw_path),
            "g4_blinded_1980_key.json": sha256_file(secret_unred_key_path),
            "g4_redacted_1980_key.json": sha256_file(secret_red_key_path),
        },
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\n[G4 Live v2] COMPLETE! Wrote {len(turn_records)} turns and blinded pools.", flush=True)


if __name__ == "__main__":
    main()
