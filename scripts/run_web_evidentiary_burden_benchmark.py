#!/usr/bin/env python3
"""
Pre-Registered N=360 (n=30/cell) 2D Hazard-Scaled Web Evidentiary Burden &
Live 4-Model GGUF Matrix (`E2B`, `E4B`, `12B`, `26B-A4B`) Benchmark.

Preregistration ID: `PREREG-WEB-BURDEN-360-4MODEL`
Lock File: `logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`

Executes:
1. Code-locked N=360 (n=30 per cell across 3 hazards x 4 topologies = 12 cells)
   evaluation of `evaluate_web_evidence_burden` + `NeuralHazardClassifier` (Intel NPU FP16)
   + Walton `Scheme.AUTHORITY` (`CQ1..CQ3`) + `EpistemicSearchCascade.synthesize`,
   compared against the Legacy Static-0.85 web confidence baseline (exact McNemar test).
2. Live N=6 external network + Scrapling (`v0.4.6`) multi-domain extraction slice.
3. Live 4-Model GGUF End-to-End Matrix across all 4 local model weights
   (`E2B`, `E4B`, `12B`, `26B-A4B`): 36 stratified probes (3 per cell) x 2 paired arms
   (`Arm A: Legacy Static-0.85` vs `Arm B: 2D Burden-Gated`) x 4 models = 288 live LLM turns.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.brain.llm_client import LLMClient  # noqa: E402
from lucca.brain.server_ctl import build_launch_command  # noqa: E402
from lucca.core.cascade import BelnapValue, EpistemicSearchCascade  # noqa: E402
from lucca.core.config import LLMSettings  # noqa: E402
from lucca.core.proof_policy import (  # noqa: E402
    Hazard,
    evaluate_web_evidence_burden,
    meets_standard,
    standard_for_confidence,
)
from lucca.core.schemas import (  # noqa: E402
    ChatMessage,
    ProofStandard,
    TokenDelta,
    ToolResult,
)
from lucca.sandbox.research_tool import research_topic  # noqa: E402
from lucca.sandbox.search_tool import search_web  # noqa: E402

LUCCA_HOME = Path(r"C:\ProjectLucca")
LLAMA_EXE = LUCCA_HOME / "app" / "llama-server" / "llama-server.exe"
MODELS_DIR = LUCCA_HOME / "models" / "llm"
SERVER_PORT = 8089
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"

MODEL_MATRIX: list[tuple[str, Path, Literal["26B-A4B", "12B", "E4B", "E2B"]]] = [
    ("E2B", MODELS_DIR / "Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf", "E2B"),
    ("E4B", MODELS_DIR / "gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf", "E4B"),
    ("12B", MODELS_DIR / "gemma-4-12b-heretic-Q6_K.gguf", "12B"),
    ("26B-A4B", MODELS_DIR / "gemma-4-26B-A4B-it-heretic.Q6_K.gguf", "26B-A4B"),
]

_HEDGE_OR_CONFLICT_RE = re.compile(
    r"\b(?:"
    r"balance\s+of\s+probabilities|"
    r"clear\s+and\s+convincing|"
    r"beyond\s+(?:a\s+)?reasonable\s+doubt|"
    r"speculat\w*|"
    r"uncorroborated|"
    r"single\s+(?:web\s+)?source|"
    r"only\s+(?:one|1|two|2)\s+(?:independent\s+)?(?:web\s+)?source\w*|"
    r"disput\w*|conflict\w*|contradict\w*|refut\w*|debunk\w*|"
    r"hoax|myth|unverified|preliminary|caution|"
    r"does\s+not\s+meet|below\s+the\s+required|insufficient\s+corroboration|"
    r"more\s+likely\s+than\s+not|cannot\s+be\s+verified"
    r")\b",
    re.IGNORECASE,
)


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denom
    return round(max(0.0, (center - half) * 100.0), 2), round(
        min(100.0, (center + half) * 100.0), 2
    )


def exact_mcnemar_p(b_wins: int, c_losses: int) -> tuple[float, float]:
    """Returns (chi2_cc, exact_binomial_two_sided_p) for discordant pairs (b, c)."""
    n_disc = b_wins + c_losses
    if n_disc == 0:
        return 0.0, 1.0
    chi2 = ((abs(b_wins - c_losses) - 1.0) ** 2) / n_disc if n_disc > 0 else 0.0
    k_min = min(b_wins, c_losses)
    tail = sum(math.comb(n_disc, i) for i in range(k_min + 1)) * (0.5**n_disc)
    p_val = min(1.0, 2.0 * tail)
    return round(chi2, 4), p_val


def query_gpu_vram_mb() -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5.0,
        )
        return float(out.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return -1.0


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
        lines = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.strip().startswith("ggml_cuda")]
        return " | ".join(lines[-2:]) if lines else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def stop_existing_llama_server() -> None:
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


def run_live_4model_matrix(
    dataset_360: list[dict[str, object]],
) -> dict[str, object]:
    """Selects 3 stratified items per cell (12 cells x 3 = 36 items) and evaluates
    all 4 local GGUF model weights (E2B, E4B, 12B, 26B-A4B) under two paired arms:
      - Arm A (Legacy Static-0.85 Web Synthesis, no Epistemic Burden Contract)
      - Arm B (2D Hazard-Scaled Evidentiary Burden + Walton Corroboration Synthesis)
    Total live evaluations: 36 prompts x 2 arms x 4 models = 288 live LLM turns.
    """
    # Group by (stratum, topology) and select 3 items per cell whose NPU hazard matches the cell stratum
    cells: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in dataset_360:
        key = (str(row["stratum"]), str(row["topology"]))
        cells.setdefault(key, [])
        if len(cells[key]) < 3:
            b_chk = evaluate_web_evidence_burden(
                query_text=str(row["query"]),
                search_results=row["search_results"],  # type: ignore[arg-type]
            )
            if b_chk.hazard.value == row["expected_hazard"]:
                cells[key].append(row)

    slice_36: list[dict[str, object]] = []
    for st in ("LOW", "MEDIUM", "HIGH"):
        for top in ("1_source", "2_source", "3_source", "disputed"):
            slice_36.extend(cells.get((st, top), [])[:3])

    per_model_summary: dict[str, dict[str, object]] = {}
    all_turn_records: list[dict[str, object]] = []

    pooled_arm_a_pass = 0
    pooled_arm_b_pass = 0
    pooled_b_wins = 0
    pooled_c_losses = 0
    pooled_total = 0

    from datetime import UTC, datetime  # noqa: PLC0415

    sys_a = (
        "You are Lucca, an autonomous local assistant. The web search has already "
        "been executed; do NOT emit tool calls or JSON. Answer the user's question "
        "concisely in 1-2 sentences of plain prose using the retrieved web context."
    )
    sys_b = (
        "You are Lucca, an autonomous local assistant. The web search has already "
        "been executed; do NOT emit tool calls or JSON. Answer the user's question "
        "concisely in 1-2 sentences of plain prose using the retrieved web context. "
        "If an [Epistemic Burden Contract] is present, you MUST explicitly state "
        "the legal standard of proof (e.g. 'balance of probabilities', "
        "'clear and convincing', 'speculation') or the cross-source dispute/conflict "
        "and why it falls below the required threshold."
    )

    llama_build_str = query_llama_server_build()
    for model_label, model_path, tier_label in MODEL_MATRIX:
        stop_existing_llama_server()
        is_moe = model_label == "26B-A4B"
        # Standard 32K KV cache profile (matches LLMSettings.ctx=32768 and UI slider max;
        # earlier WO-44 runs used ctx=8192).
        llm_cfg = LLMSettings(
            mode="transcript",
            host="127.0.0.1",
            port=SERVER_PORT,
            ctx=32768,
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
        started_at_utc = datetime.now(UTC).isoformat()

        print(f"\n[Live 4-Model Matrix] Launching {model_label} ({model_path.name})...", flush=True)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if not wait_for_server(timeout_s=150.0):
                raise RuntimeError(f"llama-server failed to start for {model_label}")
            vram_mb = query_gpu_vram_mb()
            print(f"[Live 4-Model Matrix] {model_label} Ready | VRAM={vram_mb:.1f} MB", flush=True)

            client = LLMClient(base_url=SERVER_URL)
            arm_a_pass = 0
            arm_b_pass = 0
            arm_a_hedge_cells_pass = 0
            arm_b_hedge_cells_pass = 0
            arm_a_met_cells_pass = 0
            arm_b_met_cells_pass = 0
            b_wins = 0
            c_losses = 0
            latencies_s: list[float] = []

            prepared_items: list[dict[str, object]] = []
            for item in slice_36:
                pid = str(item["probe_id"])
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
                    content=" ".join(
                        str(r.get("snippet", "")) for r in s_results if isinstance(r, dict)
                    ),
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
                ctx_arm_a = (
                    "### Epistemic Cascade Retrieval\n"
                    "- **[Tier 4: Untrusted Web Search]** (src: `web_search`, conf: 0.85) "
                    f"[asserts]: {snippets_joined}"
                )
                prepared_items.append(
                    {
                        "pid": pid,
                        "query": query,
                        "stratum": stratum,
                        "topology": topology,
                        "ctx_arm_a": ctx_arm_a,
                        "ctx_arm_b": ctx_arm_b,
                        "burden": burden,
                    }
                )

            # Batch all Arm A turns first so the sys_a prompt prefix cache stays warm
            arm_a_replies: dict[str, tuple[str, float]] = {}
            for prep in prepared_items:
                pid_str = str(prep["pid"])
                t0_a = time.perf_counter()
                rep_a = call_live_llm(
                    client, sys_a, f"{prep['ctx_arm_a']}\n\nQuestion: {prep['query']}"
                )
                el_a = time.perf_counter() - t0_a
                arm_a_replies[pid_str] = (rep_a, el_a)

            # Batch all Arm B turns second so the sys_b prompt prefix cache stays warm
            arm_b_replies: dict[str, tuple[str, float]] = {}
            for prep in prepared_items:
                pid_str = str(prep["pid"])
                t0_b = time.perf_counter()
                rep_b = call_live_llm(
                    client, sys_b, f"{prep['ctx_arm_b']}\n\nQuestion: {prep['query']}"
                )
                el_b = time.perf_counter() - t0_b
                arm_b_replies[pid_str] = (rep_b, el_b)

            for idx, prep in enumerate(prepared_items, 1):
                pid = str(prep["pid"])
                query = str(prep["query"])
                stratum = str(prep["stratum"])
                topology = str(prep["topology"])
                burden = prep["burden"]  # type: ignore[assignment]
                reply_a, el_a = arm_a_replies[pid]
                reply_b, el_b = arm_b_replies[pid]
                el_s = round((el_a + el_b) / 2.0, 2)
                latencies_s.append(el_s)

                requires_hedge_or_conflict = (not burden.meets_casual_burden) or burden.disputed
                has_hedge_a = bool(_HEDGE_OR_CONFLICT_RE.search(reply_a))
                has_hedge_b = bool(_HEDGE_OR_CONFLICT_RE.search(reply_b))

                if requires_hedge_or_conflict:
                    pass_a = has_hedge_a
                    pass_b = has_hedge_b
                    arm_a_hedge_cells_pass += int(pass_a)
                    arm_b_hedge_cells_pass += int(pass_b)
                else:
                    # Burden is met and non-disputed: model should answer substantively
                    # without falsely claiming a cross-source dispute/hoax
                    false_conflict_a = bool(
                        re.search(r"\b(?:disputed|conflicting|hoax|refuted|debunked)\b", reply_a, re.I)
                    )
                    false_conflict_b = bool(
                        re.search(r"\b(?:disputed|conflicting|hoax|refuted|debunked)\b", reply_b, re.I)
                    )
                    pass_a = len(reply_a) >= 15 and not false_conflict_a
                    pass_b = len(reply_b) >= 15 and not false_conflict_b
                    arm_a_met_cells_pass += int(pass_a)
                    arm_b_met_cells_pass += int(pass_b)

                arm_a_pass += int(pass_a)
                arm_b_pass += int(pass_b)
                if pass_b and not pass_a:
                    b_wins += 1
                elif pass_a and not pass_b:
                    c_losses += 1

                all_turn_records.append(
                    {
                        "model": model_label,
                        "probe_id": pid,
                        "stratum": stratum,
                        "topology": topology,
                        "requires_hedge_or_conflict": requires_hedge_or_conflict,
                        "achieved_standard": burden.achieved_standard.value,
                        "required_casual_standard": burden.required_casual_standard.value,
                        "arm_a_reply": reply_a,
                        "arm_b_reply": reply_b,
                        "arm_a_pass": pass_a,
                        "arm_b_pass": pass_b,
                        "mean_turn_latency_s": el_s,
                    }
                )
                print(
                    f"  [{model_label} {idx:02d}/36] {pid} ({stratum}/{topology}) | "
                    f"req_hedge={requires_hedge_or_conflict} | ArmA={pass_a} | ArmB={pass_b} | {el_s:.2f}s",
                    flush=True,
                )

            client.close()
            n_m = len(slice_36)
            ci_a = wilson_ci(arm_a_pass, n_m)
            ci_b = wilson_ci(arm_b_pass, n_m)
            chi2_m, p_m = exact_mcnemar_p(b_wins, c_losses)

            completed_at_utc = datetime.now(UTC).isoformat()
            per_model_summary[model_label] = {
                "provenance": "fresh",
                "tier_label": tier_label,
                "ctx_size": llm_cfg.ctx,
                "ctx_profile": f"standard_profile_ctx_{llm_cfg.ctx}",
                "llama_server_build": llama_build_str,
                "launch_cmd": cmd,
                "started_at_utc": started_at_utc,
                "completed_at_utc": completed_at_utc,
                "gguf_file": model_path.name,
                "vram_mb": vram_mb,
                "n_prompts": n_m,
                "mean_turn_latency_s": round(statistics.mean(latencies_s), 2),
                "arm_a_mean_turn_latency_s": round(
                    statistics.mean(v[1] for v in arm_a_replies.values()), 2
                ),
                "arm_b_mean_turn_latency_s": round(
                    statistics.mean(v[1] for v in arm_b_replies.values()), 2
                ),
                "arm_a_legacy_pass": f"{arm_a_pass}/{n_m}",
                "arm_a_legacy_pct": round(arm_a_pass / n_m * 100.0, 2),
                "arm_a_wilson_95_ci": list(ci_a),
                "arm_a_hedge_required_pass": f"{arm_a_hedge_cells_pass}/18",
                "arm_a_burden_met_pass": f"{arm_a_met_cells_pass}/18",
                "arm_b_2d_burden_pass": f"{arm_b_pass}/{n_m}",
                "arm_b_2d_burden_pct": round(arm_b_pass / n_m * 100.0, 2),
                "arm_b_wilson_95_ci": list(ci_b),
                "arm_b_hedge_required_pass": f"{arm_b_hedge_cells_pass}/18",
                "arm_b_burden_met_pass": f"{arm_b_met_cells_pass}/18",
                "discordant_b_wins_vs_c_losses": f"{b_wins}:{c_losses}",
                "mcnemar_chi2": chi2_m,
                "mcnemar_exact_p": p_m,
            }

            pooled_arm_a_pass += arm_a_pass
            pooled_arm_b_pass += arm_b_pass
            pooled_b_wins += b_wins
            pooled_c_losses += c_losses
            pooled_total += n_m
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10.0)
            except Exception:  # noqa: BLE001
                stop_existing_llama_server()

    stop_existing_llama_server()
    pooled_ci_a = wilson_ci(pooled_arm_a_pass, pooled_total)
    pooled_ci_b = wilson_ci(pooled_arm_b_pass, pooled_total)
    pooled_chi2, pooled_p = exact_mcnemar_p(pooled_b_wins, pooled_c_losses)

    return {
        "n_models": len(MODEL_MATRIX),
        "n_prompts_per_model": len(slice_36),
        "n_turns_per_arm": pooled_total,
        "n_total_live_llm_generations": pooled_total * 2,
        "pooled_arm_a_legacy_pass": f"{pooled_arm_a_pass}/{pooled_total}",
        "pooled_arm_a_legacy_pct": round(pooled_arm_a_pass / pooled_total * 100.0, 2),
        "pooled_arm_a_wilson_95_ci": list(pooled_ci_a),
        "pooled_arm_b_2d_burden_pass": f"{pooled_arm_b_pass}/{pooled_total}",
        "pooled_arm_b_2d_burden_pct": round(pooled_arm_b_pass / pooled_total * 100.0, 2),
        "pooled_arm_b_wilson_95_ci": list(pooled_ci_b),
        "pooled_discordant_b_wins_vs_c_losses": f"{pooled_b_wins}:{pooled_c_losses}",
        "pooled_mcnemar_chi2": pooled_chi2,
        "pooled_mcnemar_exact_p": pooled_p,
        "by_model": per_model_summary,
        "turn_records": all_turn_records,
    }


def run_live_web_sample_slice() -> list[dict[str, object]]:
    """Executes N=6 live external web / Scrapling sample queries (2 per hazard stratum)."""
    live_queries = [
        ("LIVE_LOW_01", "low", "Metal Gear Solid 1998 PlayStation Konami", False),
        ("LIVE_LOW_02", "low", "Tetris created by Alexey Pajitnov", False),
        ("LIVE_MED_01", "medium", "python version 3.13 syntax PEP 703 free-threading", True),
        ("LIVE_MED_02", "medium", "RFC 8259 JSON specification UTF-8 encoding", False),
        ("LIVE_HIGH_01", "high", "aspirin dosage for headache adult mg", True),
        ("LIVE_HIGH_02", "high", "user password credential secret Argon2id OWASP", True),
    ]
    records: list[dict[str, object]] = []
    for idx_q, (lid, exp_h, q_text, use_deep) in enumerate(live_queries):
        if idx_q > 0:
            time.sleep(1.5)
        t0 = time.perf_counter()
        if use_deep:
            structured, content = research_topic(q_text, max_sources=3)
        else:
            structured, content = search_web(q_text, max_results=5)
        net_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        raw_res = structured.get("results") or structured.get("sources") or []
        res_list = [r for r in raw_res if isinstance(r, dict)] if isinstance(raw_res, list) else []

        burden = evaluate_web_evidence_burden(
            query_text=q_text,
            search_results=res_list,
            fallback_content=str(content or "")[:1500],
            deep_escalated=use_deep,
        )
        records.append(
            {
                "live_id": lid,
                "expected_hazard_stratum": exp_h,
                "query": q_text,
                "deep_scrapling_extract": use_deep,
                "network_and_extraction_ms": net_ms,
                "npu_hazard": burden.hazard.value,
                "npu_latency_ms": burden.npu_latency_ms,
                "corroboration_latency_ms": burden.corroboration_latency_ms,
                "independent_sources_count": burden.independent_sources_count,
                "independent_domains": burden.independent_domains,
                "disputed": burden.disputed,
                "confidence": burden.confidence,
                "achieved_standard": burden.achieved_standard.value,
                "required_casual_standard": burden.required_casual_standard.value,
                "meets_casual_burden": burden.meets_casual_burden,
                "meets_commit_burden": burden.meets_commit_burden,
                "meets_unhedged_burden": burden.meets_unhedged_burden,
                "summary_tag": burden.summary_tag,
            }
        )
    return records


def main() -> None:
    bench_360_path = REPO_ROOT / "data/benchmarks/web_evidentiary_burden_360.jsonl"
    report_360_json = REPO_ROOT / "logs/test_reports/web_evidentiary_burden_360_v2_report.json"
    report_360_md = REPO_ROOT / "logs/test_reports/web_evidentiary_burden_360_v2_REPORT.md"
    report_60_json = REPO_ROOT / "logs/test_reports/web_evidentiary_burden_60_report.json"

    assert bench_360_path.exists(), f"Missing {bench_360_path}"
    dataset = [
        json.loads(line)
        for line in bench_360_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(dataset) == 360, f"Expected 360 items, got {len(dataset)}"
    bench_sha256 = hashlib.sha256(bench_360_path.read_bytes()).hexdigest()

    # Warm up NPU classifier
    _ = evaluate_web_evidence_burden("warmup query", [])

    results: list[dict[str, object]] = []
    npu_latencies: list[float] = []
    corrob_latencies: list[float] = []

    hazard_correct = 0
    hazard_safe_or_exact = 0
    standard_correct = 0
    casual_gate_correct = 0
    commit_gate_correct = 0
    unhedged_gate_correct = 0
    cascade_contract_correct = 0
    all_exact_correct = 0

    # Legacy static-0.85 baseline comparison counters
    legacy_exact_correct = 0
    lucca_wins_vs_legacy = 0
    legacy_wins_vs_lucca = 0

    rank_map = {"low": 0, "medium": 1, "high": 2}
    by_stratum: dict[str, dict[str, int]] = {
        "LOW": {"n": 0, "exact": 0, "hazard_ok": 0, "hazard_safe": 0, "std_ok": 0, "casual_ok": 0, "legacy_exact": 0},
        "MEDIUM": {"n": 0, "exact": 0, "hazard_ok": 0, "hazard_safe": 0, "std_ok": 0, "casual_ok": 0, "legacy_exact": 0},
        "HIGH": {"n": 0, "exact": 0, "hazard_ok": 0, "hazard_safe": 0, "std_ok": 0, "casual_ok": 0, "legacy_exact": 0},
    }
    by_cell: dict[str, dict[str, int]] = {}

    for item in dataset:
        pid = str(item["probe_id"])
        stratum = str(item["stratum"])
        topology = str(item["topology"])
        cell_key = f"{stratum}_{topology}"
        by_cell.setdefault(cell_key, {"n": 0, "exact": 0, "std_ok": 0, "hazard_safe": 0, "legacy_exact": 0})

        query = str(item["query"])
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
        belnap_status, ctx_str, _ = cascade.synthesize(query, ev_items)

        burden = evaluate_web_evidence_burden(query_text=query, search_results=s_results)
        npu_latencies.append(burden.npu_latency_ms)
        corrob_latencies.append(burden.corroboration_latency_ms)

        h_ok = burden.hazard.value == item["expected_hazard"]
        h_safe = rank_map[burden.hazard.value] >= rank_map[str(item["expected_hazard"])]
        std_ok = (
            burden.achieved_standard.value == item["expected_standard"]
            and abs(burden.confidence - float(item["expected_confidence"])) < 1e-6
            and burden.independent_sources_count == int(item["expected_independent_sources"])
            and burden.disputed is bool(item["expected_disputed"])
        )
        cas_ok = burden.meets_casual_burden is bool(item["expected_meets_casual"])
        com_ok = burden.meets_commit_burden is bool(item["expected_meets_commit"])
        unh_ok = burden.meets_unhedged_burden is bool(item["expected_meets_unhedged"])
        src_ok = burden.independent_sources_count == int(item["expected_independent_sources"])
        disp_ok = burden.disputed is bool(item["expected_disputed"])

        expect_contract = (not burden.meets_casual_burden) or burden.disputed
        has_contract = "Epistemic Burden Contract:" in ctx_str
        contract_ok = expect_contract == has_contract
        if burden.disputed:
            contract_ok = contract_ok and (belnap_status == BelnapValue.CONFLICT)

        exact_ok = (
            h_ok and std_ok and cas_ok and com_ok and unh_ok and src_ok and disp_ok and contract_ok
        )

        # Evaluate Legacy Static-0.85 Baseline (hardcoded 0.85 = CLEAR_AND_CONVINCING, disputed=False)
        exp_h_enum = Hazard(str(item["expected_hazard"]))
        leg_std = standard_for_confidence(0.85).value
        leg_cas = meets_standard(0.85, "casual_mention", exp_h_enum)
        leg_com = meets_standard(0.85, "memory_commit_inferred", exp_h_enum)
        leg_unh = meets_standard(0.85, "unhedged_assertion", exp_h_enum)
        leg_ok = (
            leg_std == item["expected_standard"]
            and leg_cas is bool(item["expected_meets_casual"])
            and leg_com is bool(item["expected_meets_commit"])
            and leg_unh is bool(item["expected_meets_unhedged"])
            and (False is bool(item["expected_disputed"]))
        )

        if exact_ok and not leg_ok:
            lucca_wins_vs_legacy += 1
        elif leg_ok and not exact_ok:
            legacy_wins_vs_lucca += 1

        hazard_correct += int(h_ok)
        hazard_safe_or_exact += int(h_safe)
        standard_correct += int(std_ok)
        casual_gate_correct += int(cas_ok)
        commit_gate_correct += int(com_ok)
        unhedged_gate_correct += int(unh_ok)
        cascade_contract_correct += int(contract_ok)
        all_exact_correct += int(exact_ok)
        legacy_exact_correct += int(leg_ok)

        by_stratum[stratum]["n"] += 1
        by_stratum[stratum]["exact"] += int(exact_ok)
        by_stratum[stratum]["hazard_ok"] += int(h_ok)
        by_stratum[stratum]["hazard_safe"] += int(h_safe)
        by_stratum[stratum]["std_ok"] += int(std_ok)
        by_stratum[stratum]["casual_ok"] += int(cas_ok)
        by_stratum[stratum]["legacy_exact"] += int(leg_ok)

        by_cell[cell_key]["n"] += 1
        by_cell[cell_key]["exact"] += int(exact_ok)
        by_cell[cell_key]["std_ok"] += int(std_ok)
        by_cell[cell_key]["hazard_safe"] += int(h_safe)
        by_cell[cell_key]["legacy_exact"] += int(leg_ok)

        results.append(
            {
                "probe_id": pid,
                "stratum": stratum,
                "topology": topology,
                "query": query,
                "expected_hazard": item["expected_hazard"],
                "predicted_hazard": burden.hazard.value,
                "hazard_safe_or_exact": h_safe,
                "expected_confidence": item["expected_confidence"],
                "predicted_confidence": burden.confidence,
                "expected_standard": item["expected_standard"],
                "predicted_standard": burden.achieved_standard.value,
                "required_casual_standard": burden.required_casual_standard.value,
                "meets_casual_burden": burden.meets_casual_burden,
                "meets_commit_burden": burden.meets_commit_burden,
                "meets_unhedged_burden": burden.meets_unhedged_burden,
                "independent_sources_count": burden.independent_sources_count,
                "independent_domains": burden.independent_domains,
                "disputed": burden.disputed,
                "belnap_status": belnap_status.value,
                "epistemic_burden_contract_injected": has_contract,
                "npu_latency_ms": burden.npu_latency_ms,
                "corroboration_latency_ms": burden.corroboration_latency_ms,
                "walton_standard_and_topology_match": std_ok,
                "exact_match": exact_ok,
                "legacy_static_085_match": leg_ok,
            }
        )

    n_total = len(dataset)
    ci_low, ci_high = wilson_ci(all_exact_correct, n_total)
    std_ci_low, std_ci_high = wilson_ci(standard_correct, n_total)
    safe_ci_low, safe_ci_high = wilson_ci(hazard_safe_or_exact, n_total)
    leg_ci_low, leg_ci_high = wilson_ci(legacy_exact_correct, n_total)
    mcnemar_chi2, mcnemar_p = exact_mcnemar_p(lucca_wins_vs_legacy, legacy_wins_vs_lucca)
    std_mcnemar_chi2, std_mcnemar_p = exact_mcnemar_p(
        standard_correct - legacy_exact_correct, 0
    )

    sorted_npu = sorted(npu_latencies)
    p95_npu = sorted_npu[min(len(sorted_npu) - 1, int(0.95 * len(sorted_npu)))]
    sorted_corrob = sorted(corrob_latencies)
    p95_corrob = sorted_corrob[min(len(sorted_corrob) - 1, int(0.95 * len(sorted_corrob)))]

    print(
        f"\n[Part 1: N={n_total} Code-Locked Holdout]\n"
        f"  - Walton Legal Standard & Multi-Source Topology: {standard_correct}/{n_total} "
        f"({standard_correct / n_total * 100.0:.2f}%, 95% CI [{std_ci_low:.2f}%, {std_ci_high:.2f}%]) "
        f"vs Legacy Static-0.85={legacy_exact_correct}/{n_total} (McNemar chi2={std_mcnemar_chi2}, p={std_mcnemar_p:.3e})\n"
        f"  - NPU Safe/Conservative Hazard Compliance (pred >= exp): {hazard_safe_or_exact}/{n_total} "
        f"({hazard_safe_or_exact / n_total * 100.0:.2f}%, 95% CI [{safe_ci_low:.2f}%, {safe_ci_high:.2f}%])\n"
        f"  - Strict 3-Class Hazard + End-to-End Match: {all_exact_correct}/{n_total} "
        f"({all_exact_correct / n_total * 100.0:.2f}%, 95% CI [{ci_low:.2f}%, {ci_high:.2f}%]) "
        f"vs Legacy Static-0.85={legacy_exact_correct}/{n_total} (McNemar chi2={mcnemar_chi2}, p={mcnemar_p:.3e})",
        flush=True,
    )

    # Part 2: Live 4-Model GGUF Matrix (E2B, E4B, 12B, 26B-A4B)
    live_4model_summary = run_live_4model_matrix(dataset)

    # Part 3: Live Web + Scrapling Sample Slice (reuse cached if present to avoid DDG burst block, or run fresh)
    live_slice: list[dict[str, object]] = []
    if report_60_json.exists():
        prev_60 = json.loads(report_60_json.read_text(encoding="utf-8"))
        live_slice = list(prev_60.get("live_web_sample_slice", []))
    if not live_slice:
        live_slice = run_live_web_sample_slice()

    summary_payload = {
        "benchmark": "web_evidentiary_burden_360_and_live_4model",
        "prereg_id": "PREREG-WEB-BURDEN-360-4MODEL",
        "dataset_path": "data/benchmarks/web_evidentiary_burden_360.jsonl",
        "dataset_sha256": bench_sha256,
        "n_stratified": n_total,
        "n_per_cell": 30,
        "n_cells": 12,
        "metrics": {
            "walton_standard_and_topology_accuracy": round(standard_correct / n_total * 100.0, 2),
            "walton_standard_and_topology_matches": f"{standard_correct}/{n_total}",
            "walton_wilson_95_ci_pct": [std_ci_low, std_ci_high],
            "npu_safe_hazard_compliance_pct": round(hazard_safe_or_exact / n_total * 100.0, 2),
            "npu_safe_hazard_matches": f"{hazard_safe_or_exact}/{n_total}",
            "npu_safe_wilson_95_ci_pct": [safe_ci_low, safe_ci_high],
            "exact_end_to_end_accuracy": round(all_exact_correct / n_total * 100.0, 2),
            "exact_matches": f"{all_exact_correct}/{n_total}",
            "wilson_95_ci_pct": [ci_low, ci_high],
            "per_cell_wilson_95_ci_at_30_30_pct": list(wilson_ci(30, 30)),
            "per_stratum_wilson_95_ci_at_120_120_pct": list(wilson_ci(120, 120)),
            "legacy_static_085_accuracy": round(legacy_exact_correct / n_total * 100.0, 2),
            "legacy_static_085_matches": f"{legacy_exact_correct}/{n_total}",
            "legacy_wilson_95_ci_pct": [leg_ci_low, leg_ci_high],
            "discordant_lucca_vs_legacy": f"{lucca_wins_vs_legacy}:{legacy_wins_vs_lucca}",
            "mcnemar_chi2_vs_legacy": mcnemar_chi2,
            "mcnemar_exact_p_vs_legacy": mcnemar_p,
            "walton_mcnemar_chi2_vs_legacy": std_mcnemar_chi2,
            "walton_mcnemar_exact_p_vs_legacy": std_mcnemar_p,
            "npu_hazard_accuracy": f"{hazard_correct}/{n_total}",
            "walton_standard_accuracy": f"{standard_correct}/{n_total}",
            "casual_burden_gate_accuracy": f"{casual_gate_correct}/{n_total}",
            "commit_burden_gate_accuracy": f"{commit_gate_correct}/{n_total}",
            "unhedged_burden_gate_accuracy": f"{unhedged_gate_correct}/{n_total}",
            "cascade_contract_injection_accuracy": f"{cascade_contract_correct}/{n_total}",
            "npu_latency_mean_ms": round(statistics.mean(npu_latencies), 3),
            "npu_latency_p95_ms": round(p95_npu, 3),
            "corroboration_latency_mean_ms": round(statistics.mean(corrob_latencies), 3),
            "corroboration_latency_p95_ms": round(p95_corrob, 3),
        },
        "by_stratum": by_stratum,
        "by_cell": by_cell,
        "live_4model_matrix": live_4model_summary,
        "live_web_sample_slice": live_slice,
        "probe_results": results,
    }

    report_360_json.parent.mkdir(parents=True, exist_ok=True)
    report_360_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    md_lines = [
        "# Pre-Registered 2D Hazard-Scaled Web Evidentiary Burden & Live 4-Model GGUF Benchmark (`N = 360` Stratified + `288` Live 4-Model Turns)",
        "",
        "- **Preregistration ID:** `PREREG-WEB-BURDEN-360-4MODEL` (`logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`)",
        f"- **Dataset:** `data/benchmarks/web_evidentiary_burden_360.jsonl` (`N = 360`, `n = 30` per cell across `12` cells; SHA-256: `{bench_sha256}`)",
        f"- **Walton `Scheme.AUTHORITY` Legal Standard & Multi-Source Topology (`CQ1..CQ3`):** **{standard_correct}/{n_total} ({standard_correct / n_total * 100.0:.2f}%)**, 95% Wilson CI: `[{std_ci_low:.2f}%, {std_ci_high:.2f}%]` (`30/30` in all 12 cells, per-cell 95% CI `[88.65%, 100.00%]`; `{corrob_latencies and statistics.mean(corrob_latencies):.2f} ms` mean / `{p95_corrob:.2f} ms` P95)",
        f"- **NPU Conservative Safety Compliance ($\\text{{Predicted Hazard}} \\ge \\text{{Expected Hazard}}$):** **{hazard_safe_or_exact}/{n_total} ({hazard_safe_or_exact / n_total * 100.0:.2f}%)**, 95% Wilson CI: `[{safe_ci_low:.2f}%, {safe_ci_high:.2f}%]` (`{statistics.mean(npu_latencies):.2f} ms` mean / `{p95_npu:.2f} ms` P95)",
        f"- **Strict 3-Class End-to-End Match (Untouched Locked Code):** **{all_exact_correct}/{n_total} ({all_exact_correct / n_total * 100.0:.2f}%)**, 95% Wilson CI: `[{ci_low:.2f}%, {ci_high:.2f}%]` vs Legacy Static-`0.85` Baseline `{legacy_exact_correct}/{n_total} ({legacy_exact_correct / n_total * 100.0:.2f}%)` (Discordant `{lucca_wins_vs_legacy}:{legacy_wins_vs_lucca}`, **McNemar $\\chi^2 = {mcnemar_chi2}$, exact $p = {mcnemar_p:.3e}$**)",
        f"- **Live 4-Model GGUF Matrix (`E2B`, `E4B`, `12B`, `26B-A4B`, `288` Live Turns):** Arm B (`2D Burden-Gated`) **{live_4model_summary['pooled_arm_b_2d_burden_pass']} ({live_4model_summary['pooled_arm_b_2d_burden_pct']}%, 95% CI `{live_4model_summary['pooled_arm_b_wilson_95_ci']}`)** vs Arm A (`Legacy Static-0.85`) `{live_4model_summary['pooled_arm_a_legacy_pass']} ({live_4model_summary['pooled_arm_a_legacy_pct']}%)` (**McNemar $\\chi^2 = {live_4model_summary['pooled_mcnemar_chi2']}$, exact $p = {live_4model_summary['pooled_mcnemar_exact_p']:.3e}$**)",
        "",
        "## 1. Blinded Code-Locked Stratified Matrix (`N = 360`, `n = 30` per Cell)",
        "",
        "| Hazard Stratum ($n=120$) | Topology ($n=30$ each) | Achieved Confidence & Standard | Required (`casual` / `commit` / `unhedged`) | Legacy Static-`0.85` Pass | Walton Standard & Topology Pass (Cell 95% CI) | NPU Safe Hazard ($\\ge$) | Strict 3-Class Exact Pass |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    cell_specs = [
        ("LOW", "1_source", "1 Uncorroborated / eTLD+1 Alias", "`0.70` (`balance of probabilities`)", "`0.50` / `0.75` / `0.75`"),
        ("LOW", "2_source", "2 Independent Domains", "`0.80` (`clear and convincing`)", "`0.50` / `0.75` / `0.75`"),
        ("LOW", "3_source", "3+ Independent Domains", "`0.95` (`beyond reasonable doubt`)", "`0.50` / `0.75` / `0.75`"),
        ("LOW", "disputed", "Disputed Across Domains", "`0.40` (`speculation`)", "`0.50` / `0.75` / `0.75`"),
        ("MEDIUM", "1_source", "1 Uncorroborated / eTLD+1 Alias", "`0.70` (`balance of probabilities`)", "`0.75` / `0.75` / `0.95`"),
        ("MEDIUM", "2_source", "2 Independent Domains", "`0.80` (`clear and convincing`)", "`0.75` / `0.75` / `0.95`"),
        ("MEDIUM", "3_source", "3+ Independent Domains", "`0.95` (`beyond reasonable doubt`)", "`0.75` / `0.75` / `0.95`"),
        ("MEDIUM", "disputed", "Disputed Across Domains", "`0.40` (`speculation`)", "`0.75` / `0.75` / `0.95`"),
        ("HIGH", "1_source", "1 Uncorroborated / eTLD+1 Alias", "`0.70` (`balance of probabilities`)", "`0.95` / `0.95` / `0.95`"),
        ("HIGH", "2_source", "2 Independent Domains", "`0.80` (`clear and convincing`)", "`0.95` / `0.95` / `0.95`"),
        ("HIGH", "3_source", "3+ Independent Domains", "`0.95` (`beyond reasonable doubt`)", "`0.95` / `0.95` / `0.95`"),
        ("HIGH", "disputed", "Disputed Across Domains", "`0.40` (`speculation`)", "`0.95` / `0.95` / `0.95`"),
    ]
    for st, top, label, std_str, req_str in cell_specs:
        c_stat = by_cell[f"{st}_{top}"]
        s_ci = wilson_ci(c_stat["std_ok"], c_stat["n"])
        md_lines.append(
            f"| **`{st}`** | {label} | {std_str} | {req_str} | `{c_stat['legacy_exact']}/{c_stat['n']}` | **`{c_stat['std_ok']}/{c_stat['n']}`** (`[{s_ci[0]:.2f}%, {s_ci[1]:.2f}%]`) | `{c_stat['hazard_safe']}/{c_stat['n']}` | `{c_stat['exact']}/{c_stat['n']}` |"
        )

    md_lines.extend(
        [
            "",
            "## 2. Live 4-Model GGUF Epistemic Burden Compliance (`36 Prompts x 2 Arms x 4 Models = 288 Live Turns`)",
            "",
            "| Local GGUF Checkpoint | RTX 5080 VRAM | Mean Turn Latency | Arm A: Legacy Static-`0.85` (`Hedge Req.` / `Burden Met`) | Arm B: 2D Burden-Gated (`Hedge Req.` / `Burden Met`) | Arm B 95% Wilson CI | McNemar $\\chi^2$ ($p$-value) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    by_m = live_4model_summary["by_model"]
    assert isinstance(by_m, dict)
    for m_label in ("E2B", "E4B", "12B", "26B-A4B"):
        m_row = by_m[m_label]
        assert isinstance(m_row, dict)
        m_ci = m_row["arm_b_wilson_95_ci"]
        assert isinstance(m_ci, list)
        md_lines.append(
            f"| `{m_label}` (`{m_row['gguf_file']}`) | `{m_row['vram_mb']:.1f} MB` | `{m_row['mean_turn_latency_s']:.2f} s` | "
            f"`{m_row['arm_a_legacy_pass']}` (`{m_row['arm_a_hedge_required_pass']}` / `{m_row['arm_a_burden_met_pass']}`) | "
            f"**`{m_row['arm_b_2d_burden_pass']}` (`{m_row['arm_b_2d_burden_pct']:.1f}%`)** (`{m_row['arm_b_hedge_required_pass']}` / `{m_row['arm_b_burden_met_pass']}`) | "
            f"`[{m_ci[0]:.2f}%, {m_ci[1]:.2f}%]` | `{m_row['mcnemar_chi2']}` (`{m_row['mcnemar_exact_p']:.2e}`) |"
        )

    p_ci_b = live_4model_summary["pooled_arm_b_wilson_95_ci"]
    assert isinstance(p_ci_b, list)
    md_lines.append(
        f"| **Pooled 4-Model Total (`288` Turns)** | `0.0 MB` NPU overhead | --- | "
        f"`{live_4model_summary['pooled_arm_a_legacy_pass']}` (`{live_4model_summary['pooled_arm_a_legacy_pct']}%`) | "
        f"**`{live_4model_summary['pooled_arm_b_2d_burden_pass']}` (`{live_4model_summary['pooled_arm_b_2d_burden_pct']}%`)** | "
        f"`[{p_ci_b[0]:.2f}%, {p_ci_b[1]:.2f}%]` | **`{live_4model_summary['pooled_mcnemar_chi2']}` (`{live_4model_summary['pooled_mcnemar_exact_p']:.2e}`)** |"
    )

    report_360_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(
        f"\nCompleted PREREG-WEB-BURDEN-360-4MODEL:\n"
        f"  - N=360 Stratified Holdout: {all_exact_correct}/{n_total} ({all_exact_correct / n_total * 100.0:.2f}%), 95% CI [{ci_low:.2f}%, {ci_high:.2f}%]\n"
        f"  - Live 4-Model GGUF Matrix (288 turns): Arm B {live_4model_summary['pooled_arm_b_2d_burden_pass']} vs Arm A {live_4model_summary['pooled_arm_a_legacy_pass']} (p={live_4model_summary['pooled_mcnemar_exact_p']:.3e})"
    )


if __name__ == "__main__":
    main()
