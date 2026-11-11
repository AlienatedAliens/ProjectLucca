"""WO-45 Gate G4 v3 pre-registered live 5-model x 4-arm benchmark runner (RM-3, RM-4, RM-5, RM-7, RM-8).

Startup & execution invariants:
  1. Verifies every SHA-256 digest in `logs/test_reports/wo45/live_v3_prereg_lock.json`
     (repo files, 5 generator GGUFs, and 3 non-Google judge GGUFs) and writes
     `logs/test_reports/wo45/live_v3_lock_verification.json`. Aborts on any mismatch.
  2. Rejects `LUCCA_BENCH_REUSE_MODELS` if set in environment.
  3. Evaluates BOTH `v1` (`models/proof_policy_hazard_ov`) and `v2` (`models/proof_policy_hazard_v2_ov`)
     hazard classifiers side-by-side on all 132 fresh v3 items, activating the pre-registered
     `active_hazard_model_dir` for `ctx_burden`.
  4. Launches 5 local Gemma-4 Q6_K checkpoints (4 heretic + 1 stock Gemma-4-E4B-it) at `ctx=32768`
     and runs 4 arms contiguously per model (`132 * 4 * 5 = 2,640` live turns, `T=0`, `max_tokens=180`):
       - Arm A: `SYS_ARM_A` + `ctx_static`
       - Arm B: `SYS_ARM_B` + `ctx_burden`
       - Arm C: `SYS_ARM_C` + `ctx_static`
       - Arm D (RM-4): `SYS_ARM_C` + `ctx_burden` (Arm B contract context + Arm C prompt; no MUST/legal vocab)
  5. Applies `normalize_reply()` identically to ALL 4 arms (`A, B, C, D`) to build the primary
     shuffled blinded pool (`g4v3_normalized_2640_replies.jsonl`), verifies 0 forbidden lexicon hits,
     builds the secondary raw blinded pool (`g4v3_raw_2640_replies.jsonl`), and seals unblinded raw
     generations + mapping keys in `--secret-dir` outside the repo with SHA-256 commitments in
     `logs/test_reports/wo45/live_v3_pool_manifest.json`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.brain.llm_client import LLMClient  # noqa: E402
from lucca.brain.server_ctl import build_launch_command  # noqa: E402
from lucca.core.cascade import EpistemicSearchCascade  # noqa: E402
from lucca.core.config import LLMSettings  # noqa: E402
from lucca.core.neural_hazard_classifier import (  # noqa: E402
    _SINGLETON_HOLDER,
    NeuralHazardClassifier,
    reset_neural_hazard_classifier,
)
from lucca.core.proof_policy import evaluate_web_evidence_burden  # noqa: E402
from lucca.core.schemas import ChatMessage, TokenDelta, ToolResult  # noqa: E402
from scripts.wo45.normalize_g4v3_replies import (  # noqa: E402
    normalize_reply,
    scan_forbidden_lexicon,
)

LUCCA_HOME = Path(os.environ.get("LUCCA_HOME", r"C:\ProjectLucca"))
LLAMA_EXE = LUCCA_HOME / "app" / "llama-server" / "llama-server.exe"
MODELS_DIR = LUCCA_HOME / "models" / "llm"

WO45_DIR = REPO_ROOT / "logs" / "test_reports" / "wo45"
LOCK_PATH = WO45_DIR / "live_v3_prereg_lock.json"
LOCK_VERIFY_OUT = WO45_DIR / "live_v3_lock_verification.json"
SELECTED_ITEMS_PATH = WO45_DIR / "live_v3_selected_items.json"
CORPUS_360_PATH = REPO_ROOT / "data" / "benchmarks" / "web_evidentiary_burden_360.jsonl"

V1_OV_DIR = REPO_ROOT / "models" / "proof_policy_hazard_ov"
V2_OV_DIR = REPO_ROOT / "models" / "proof_policy_hazard_v2_ov"

NORMALIZED_POOL_OUT = WO45_DIR / "g4v3_normalized_2640_replies.jsonl"
RAW_POOL_OUT = WO45_DIR / "g4v3_raw_2640_replies.jsonl"
MANIFEST_OUT = WO45_DIR / "live_v3_pool_manifest.json"

SERVER_PORT = 18089
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"
LOCKED_CTX = 32768
ARMS = ("A", "B", "C", "D")

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

# RM-4: Arm D = Arm B's contract context + Arm C's system prompt (no MUST, no legal vocabulary)
SYS_ARM_D = SYS_ARM_C

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


def is_nominal_burden_met(stratum: str, topology: str) -> bool:
    if topology == "disputed":
        return False
    s = stratum.upper()
    if s == "LOW":
        return topology in ("1_source", "2_source", "3_source")
    if s == "MEDIUM":
        return topology in ("2_source", "3_source")
    if s == "HIGH":
        return topology == "3_source"
    return False


def verify_prereg_lock() -> tuple[dict[str, Any], dict[str, Any]]:
    if os.environ.get("LUCCA_BENCH_REUSE_MODELS"):
        raise RuntimeError("LUCCA_BENCH_REUSE_MODELS is strictly banned under WO-45.")
    if not LOCK_PATH.exists():
        raise FileNotFoundError(f"Missing v3 preregistration lock: {LOCK_PATH}")

    lock: dict[str, Any] = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked_files: dict[str, str] = lock["locked_repo_files_sha256"]
    repo_checks: list[dict[str, Any]] = []
    all_ok = True
    for rel_path, expected_sha in locked_files.items():
        fpath = REPO_ROOT / rel_path
        actual_sha = sha256_file(fpath) if fpath.exists() else "MISSING"
        matched = actual_sha == expected_sha
        if not matched:
            all_ok = False
        repo_checks.append(
            {
                "path": rel_path,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "matched": matched,
            }
        )

    gen_checks: list[dict[str, Any]] = []
    for fname, expected_sha in lock["locked_generator_gguf_models_sha256"].items():
        mpath = MODELS_DIR / fname
        actual_sha = sha256_file(mpath) if mpath.exists() else "MISSING"
        matched = actual_sha == expected_sha
        if not matched:
            all_ok = False
        gen_checks.append(
            {
                "model_filename": fname,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "matched": matched,
            }
        )

    judge_checks: list[dict[str, Any]] = []
    for jentry in lock["qualified_non_google_judges"]:
        jpath = Path(str(jentry["model_path"]))
        expected_sha = str(jentry["model_sha256"])
        actual_sha = sha256_file(jpath) if jpath.exists() else "MISSING"
        matched = actual_sha == expected_sha
        if not matched:
            all_ok = False
        judge_checks.append(
            {
                "judge_model": jentry["judge_model"],
                "judge_family": jentry["judge_family"],
                "model_path": str(jpath),
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "matched": matched,
            }
        )

    report: dict[str, Any] = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "lock_path": "logs/test_reports/wo45/live_v3_prereg_lock.json",
        "lock_sha256": sha256_file(LOCK_PATH),
        "all_hashes_matched": all_ok,
        "repo_file_checks": repo_checks,
        "generator_gguf_checks": gen_checks,
        "judge_gguf_checks": judge_checks,
    }
    LOCK_VERIFY_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not all_ok:
        raise RuntimeError(f"v3 lock hash verification FAILED! See {LOCK_VERIFY_OUT}")
    return lock, report


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--secret-dir",
        type=Path,
        required=True,
        help="Directory outside the git repository to hold unblinded keys until all raw judges are pushed.",
    )
    args = parser.parse_args()
    secret_dir: Path = args.secret_dir.resolve()
    if REPO_ROOT in secret_dir.parents or secret_dir == REPO_ROOT:
        raise ValueError(f"--secret-dir must be outside {REPO_ROOT}, got {secret_dir}")
    secret_dir.mkdir(parents=True, exist_ok=True)

    print("[G4 Live v3] Verifying pre-registration lock SHA-256 hashes...", flush=True)
    lock, lock_ver = verify_prereg_lock()
    print(f"[G4 Live v3] Lock verified: {lock_ver['lock_sha256']}", flush=True)

    active_rel_dir = str(lock["active_hazard_model_dir"])
    active_ov_dir = REPO_ROOT / active_rel_dir

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

    # Evaluate BOTH v1 and v2 hazard classifiers side-by-side (RM-7), then synthesize ctx_burden with active_ov_dir
    reset_neural_hazard_classifier()
    clf_v1 = NeuralHazardClassifier(model_dir=V1_OV_DIR)
    clf_v2 = NeuralHazardClassifier(model_dir=V2_OV_DIR) if V2_OV_DIR.exists() else clf_v1
    clf_active = clf_v2 if active_ov_dir.resolve() == V2_OV_DIR.resolve() else clf_v1

    prepared_items: list[dict[str, Any]] = []
    for pid in selected_ids:
        item = corpus_by_id[pid]
        query = str(item["query"])
        stratum = str(item["stratum"])
        topology = str(item["topology"])
        s_results = item["search_results"]
        assert isinstance(s_results, list)

        _SINGLETON_HOLDER["instance"] = clf_v1
        burden_v1 = evaluate_web_evidence_burden(query_text=query, search_results=s_results)

        _SINGLETON_HOLDER["instance"] = clf_v2
        burden_v2 = evaluate_web_evidence_burden(query_text=query, search_results=s_results)

        _SINGLETON_HOLDER["instance"] = clf_active
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
        burden_active = evaluate_web_evidence_burden(query_text=query, search_results=s_results)

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
                "nominal_burden_met": is_nominal_burden_met(stratum, topology),
                "active_hazard_model_dir": active_rel_dir,
                "npu_predicted_hazard": burden_active.hazard.value,
                "achieved_standard": burden_active.achieved_standard.value,
                "required_casual_standard": burden_active.required_casual_standard.value,
                "meets_casual_burden": burden_active.meets_casual_burden,
                "disputed_flag": burden_active.disputed,
                "independent_sources_count": burden_active.independent_sources_count,
                "v1_predicted_hazard": burden_v1.hazard.value,
                "v1_meets_casual_burden": burden_v1.meets_casual_burden,
                "v2_predicted_hazard": burden_v2.hazard.value,
                "v2_meets_casual_burden": burden_v2.meets_casual_burden,
                "retrieved_snippets": clean_snippets,
                "ctx_static": ctx_static,
                "ctx_burden": ctx_arm_b,
            }
        )

    reset_neural_hazard_classifier()
    stop_llama_server()
    idle_vram_mib, idle_smi_raw = query_nvidia_smi()
    llama_build_str = query_llama_server_build()

    model_provenance: dict[str, dict[str, Any]] = {}
    turn_records: list[dict[str, Any]] = []

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
        print(f"\n[G4 Live v3] Starting {model_label} ({model_fname})...", flush=True)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if not wait_for_server(timeout_s=150.0):
                raise RuntimeError(f"llama-server failed to start for {model_label}")
            vram_mib, smi_raw = query_nvidia_smi()
            print(f"[G4 Live v3] {model_label} Ready | VRAM={vram_mib:.0f} MiB", flush=True)
            client = LLMClient(base_url=SERVER_URL)

            arm_configs = [
                ("A", SYS_ARM_A, "ctx_static"),
                ("B", SYS_ARM_B, "ctx_burden"),
                ("C", SYS_ARM_C, "ctx_static"),
                ("D", SYS_ARM_D, "ctx_burden"),
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
                arm_latencies["A"]
                + arm_latencies["B"]
                + arm_latencies["C"]
                + arm_latencies["D"]
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
                for arm_name in ARMS:
                    rep_txt, rep_dt = arm_outputs[arm_name][pid]
                    norm_txt = normalize_reply(rep_txt)
                    turn_records.append(
                        {
                            "model": model_label,
                            "is_stock_non_abliterated": model_label == "E4B-stock",
                            "probe_id": pid,
                            "arm": arm_name,
                            "nominal_stratum": prep["nominal_stratum"],
                            "topology": prep["topology"],
                            "nominal_burden_met": prep["nominal_burden_met"],
                            "active_hazard_model_dir": prep["active_hazard_model_dir"],
                            "npu_predicted_hazard": prep["npu_predicted_hazard"],
                            "achieved_standard": prep["achieved_standard"],
                            "required_casual_standard": prep["required_casual_standard"],
                            "meets_casual_burden": prep["meets_casual_burden"],
                            "disputed_flag": prep["disputed_flag"],
                            "independent_sources_count": prep["independent_sources_count"],
                            "v1_predicted_hazard": prep["v1_predicted_hazard"],
                            "v1_meets_casual_burden": prep["v1_meets_casual_burden"],
                            "v2_predicted_hazard": prep["v2_predicted_hazard"],
                            "v2_meets_casual_burden": prep["v2_meets_casual_burden"],
                            "question": prep["query"],
                            "retrieved_snippets": prep["retrieved_snippets"],
                            "reply": rep_txt,
                            "normalized_reply": norm_txt,
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

    # RM-3 Acceptance Check 1 on live v3 normalized pool: MUST have 0 forbidden lexicon hits in ALL 4 arms!
    lex_by_arm: dict[str, dict[str, int]] = {}
    for arm_name in ARMS:
        lex_by_arm[arm_name] = scan_forbidden_lexicon(
            [str(r["normalized_reply"]) for r in turn_records if str(r["arm"]) == arm_name]
        )
    total_lex_hits = sum(sum(v.values()) for v in lex_by_arm.values())
    if total_lex_hits != 0:
        raise RuntimeError(
            f"Normalized v3 pool failed RM-3 lexicon scan with {total_lex_hits} hits: {lex_by_arm}"
        )

    # Primary Pool: Shuffled Arm-Identical Normalized Pool (2,640 turns)
    rng_norm = random.Random(2026111201)
    indices_norm = list(range(len(turn_records)))
    rng_norm.shuffle(indices_norm)

    norm_pool: list[dict[str, Any]] = []
    norm_key: dict[str, dict[str, Any]] = {}
    for rank, rec_idx in enumerate(indices_norm, 1):
        rec = turn_records[rec_idx]
        bid = f"G4V3N_{rank:04d}"
        norm_pool.append(
            {
                "blind_id": bid,
                "question": rec["question"],
                "retrieved_snippets": rec["retrieved_snippets"],
                "reply": rec["normalized_reply"],
                "eval_D4": rec["topology"] == "disputed",
                "eval_D3": bool(rec["nominal_burden_met"]),
            }
        )
        norm_key[bid] = {
            "model": rec["model"],
            "probe_id": rec["probe_id"],
            "arm": rec["arm"],
            "normalized_reply_sha256": hashlib.sha256(
                str(rec["normalized_reply"]).encode("utf-8")
            ).hexdigest(),
        }

    # Secondary Pool: Shuffled Raw Un-Normalized Pool (2,640 turns)
    rng_raw = random.Random(2026111202)
    indices_raw = list(range(len(turn_records)))
    rng_raw.shuffle(indices_raw)

    raw_pool: list[dict[str, Any]] = []
    raw_key: dict[str, dict[str, Any]] = {}
    for rank, rec_idx in enumerate(indices_raw, 1):
        rec = turn_records[rec_idx]
        bid = f"G4V3R_{rank:04d}"
        raw_pool.append(
            {
                "blind_id": bid,
                "question": rec["question"],
                "retrieved_snippets": rec["retrieved_snippets"],
                "reply": rec["reply"],
                "eval_D4": rec["topology"] == "disputed",
                "eval_D3": bool(rec["nominal_burden_met"]),
            }
        )
        raw_key[bid] = {
            "model": rec["model"],
            "probe_id": rec["probe_id"],
            "arm": rec["arm"],
            "reply_sha256": hashlib.sha256(str(rec["reply"]).encode("utf-8")).hexdigest(),
        }

    NORMALIZED_POOL_OUT.parent.mkdir(parents=True, exist_ok=True)
    with NORMALIZED_POOL_OUT.open("w", encoding="utf-8", newline="\n") as fn:
        for r in norm_pool:
            fn.write(json.dumps(r, ensure_ascii=False) + "\n")
    with RAW_POOL_OUT.open("w", encoding="utf-8", newline="\n") as fr:
        for r in raw_pool:
            fr.write(json.dumps(r, ensure_ascii=False) + "\n")

    raw_gen_payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "lock_sha256": lock_ver["lock_sha256"],
        "active_hazard_model_dir": active_rel_dir,
        "idle_vram_mib": idle_vram_mib,
        "idle_nvidia_smi_raw": idle_smi_raw,
        "llama_server_build": llama_build_str,
        "ctx_size": LOCKED_CTX,
        "n_items": len(prepared_items),
        "n_models": len(MODEL_MATRIX),
        "n_arms": len(ARMS),
        "n_total_turns": len(turn_records),
        "models": model_provenance,
        "turn_records": turn_records,
    }

    secret_raw_path = secret_dir / "g4_live_v3_raw_generations.json"
    secret_norm_key_path = secret_dir / "g4v3_normalized_2640_key.json"
    secret_raw_key_path = secret_dir / "g4v3_raw_2640_key.json"

    secret_raw_path.write_text(json.dumps(raw_gen_payload, indent=2) + "\n", encoding="utf-8")
    secret_norm_key_path.write_text(json.dumps(norm_key, indent=2) + "\n", encoding="utf-8")
    secret_raw_key_path.write_text(json.dumps(raw_key, indent=2) + "\n", encoding="utf-8")

    manifest: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "lock_sha256": lock_ver["lock_sha256"],
        "active_hazard_model_dir": active_rel_dir,
        "ctx_size": LOCKED_CTX,
        "idle_vram_mib": idle_vram_mib,
        "idle_nvidia_smi_raw": idle_smi_raw,
        "llama_server_build": llama_build_str,
        "models_provenance_summary": model_provenance,
        "normalized_pool_path": "logs/test_reports/wo45/g4v3_normalized_2640_replies.jsonl",
        "normalized_pool_sha256": sha256_file(NORMALIZED_POOL_OUT),
        "normalized_pool_lexicon_scan": {
            "hits_by_arm": lex_by_arm,
            "total_hits": total_lex_hits,
            "zero_hits_verified": total_lex_hits == 0,
        },
        "raw_pool_path": "logs/test_reports/wo45/g4v3_raw_2640_replies.jsonl",
        "raw_pool_sha256": sha256_file(RAW_POOL_OUT),
        "sealed_commitments_sha256": {
            "g4_live_v3_raw_generations.json": sha256_file(secret_raw_path),
            "g4v3_normalized_2640_key.json": sha256_file(secret_norm_key_path),
            "g4v3_raw_2640_key.json": sha256_file(secret_raw_key_path),
        },
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\n[G4 Live v3] COMPLETE! Wrote {len(turn_records)} turns and blinded pools.", flush=True)


if __name__ == "__main__":
    main()
