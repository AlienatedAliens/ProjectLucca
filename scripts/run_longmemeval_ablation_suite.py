#!/usr/bin/env python3
"""
Project Lucca — LongMemEval Retrieval Ablation Benchmark Suite
==============================================================
Evaluates multi-arm retrieval architectures on resident local models:
1. Arm A (Sliding-Window Truncation): Recent session only (sliding window).
2. Arm B (BM25 Sparse Only): FTS5 BM25 retrieval without dense vectors.
3. Arm C (Dense KNN Only): sqlite-vec cosine distance KNN without BM25.
4. Arm D (Lucca Hybrid Pipeline): Full compound retriever (BM25 + sqlite-vec + RRF k=60).
5. Arm E (Full-Context Oracle): All sessions formatted in prompt (no retrieval filtering).

Measures:
- Needle Recall@k per arm
- End-to-End Answer Accuracy per arm
- Paired discordant pairs & exact McNemar p-values
- Latency (retrieval ms vs LLM generation s)
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timezone
import json
import math
from pathlib import Path
import random
import re
import sys
import tempfile
import time
from typing import Any, Final
import uuid

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.core.schemas import Provenance, RetrievalQuery, UnsignedPayload
from lucca.memory.db import DatabaseManager
from lucca.memory.retrieval import format_memory_context
from lucca.memory.signers import AssistantUtteranceSigner, UserSpeechSigner
from lucca.memory.store import MemoryStore
from lucca.senses.embed import EmbedWorker, LocalEmbeddingPort

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "longmemeval_oracle.json"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 180.0
TEST_MASTER_KEY: Final[bytes] = b"01234567890123456789012345678901"


def query_llm(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> tuple[str, str, int]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are Project Lucca, a precise, helpful, and truthful personal AI assistant.\n"
                "Answer questions directly based on the conversational memory provided.\n"
                "If the answer cannot be determined from memory, say 'I do not have enough information'."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    payload: dict[str, Any] = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    t0 = time.perf_counter()
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        res = client.post(SERVER_URL, json=payload)
        res.raise_for_status()
        data = res.json()

    choice = data["choices"][0]
    output = choice["message"]["content"].strip()
    finish_reason = choice.get("finish_reason", "stop")
    usage = data.get("usage", {})
    tokens = usage.get("completion_tokens", len(output.split()))

    return output, finish_reason, tokens


def evaluate_memory_answer(prediction: str, ground_truth: str) -> bool:
    pred_lower = prediction.lower().strip()
    gt_lower = ground_truth.lower().strip()

    if "i do not have enough information" in pred_lower:
        return False

    if gt_lower in pred_lower:
        return True

    gt_nums = re.findall(r"\b\d+(?::\d+)?\b", gt_lower)
    if gt_nums:
        pred_nums = re.findall(r"\b\d+(?::\d+)?\b", pred_lower)
        if any(gn in pred_nums for gn in gt_nums):
            keywords = [w for w in re.findall(r"\b\w{4,}\b", gt_lower) if w not in ("days", "time", "date", "acceptable")]
            if not keywords or any(kw in pred_lower for kw in keywords):
                return True

    gt_words = set(re.findall(r"\b\w{3,}\b", gt_lower)) - {"the", "and", "was", "for", "with", "also", "acceptable"}
    pred_words = set(re.findall(r"\b\w{3,}\b", pred_lower))
    if gt_words and (len(gt_words & pred_words) / len(gt_words) >= 0.75):
        return True

    return False


def parse_session_date(dt_str: str) -> float:
    m = re.match(r"^(\d{4})[/-](\d{2})[/-](\d{2}).*?(\d{2}):(\d{2})", dt_str.strip())
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()
    return 1680000000.0


def compute_mcnemar(base_corrects: list[bool], comp_corrects: list[bool]) -> tuple[int, int, float]:
    b = sum(1 for base, comp in zip(base_corrects, comp_corrects) if base and not comp)
    c = sum(1 for base, comp in zip(base_corrects, comp_corrects) if not base and comp)
    n = b + c
    if n == 0:
        return 0, 0, 1.0
    p_val = sum(math.comb(n, k) * (0.5 ** n) for k in range(0, min(b, c) + 1)) * 2.0
    return b, c, min(1.0, p_val)


def run_ablation_battery(
    limit_per_type: int = 5,
    seed: int = 42,
    model_tag: str = "E2B",
    top_k: int = 12,
    output_path: Path | None = None,
) -> dict[str, Any]:
    print("=" * 80)
    print("=== PROJECT LUCCA: LongMemEval 5-ARM RETRIEVAL ABLATION BATTERY ===")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(UTC).isoformat()} | Model: {model_tag} | Top-K: {top_k}")
    print(f"Dataset: {DATA_FILE.name} (limit={limit_per_type} per type, seed={seed})\n")

    data = json.load(open(DATA_FILE, encoding="utf-8"))
    types = ["knowledge-update", "temporal-reasoning", "multi-session"]

    rng = random.Random(seed)
    selected_items: list[dict[str, Any]] = []
    for t in types:
        sub = [x for x in data if x.get("question_type") == t]
        rng.shuffle(sub)
        selected_items.extend(sub[:limit_per_type])

    embed_port = LocalEmbeddingPort(worker=EmbedWorker(device="CPU"))
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    assistant_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)

    item_records: list[dict[str, Any]] = []

    for idx, item in enumerate(selected_items, start=1):
        qid = item["question_id"]
        qtype = item.get("question_type", "unknown")
        q_text = item["question"]
        gt = item["answer"]
        q_date_str = item.get("question_date", "2023/06/01 (Thu) 12:00")
        q_ts = parse_session_date(q_date_str)
        dates = item.get("haystack_dates", [])
        sessions = item.get("haystack_sessions", [])

        print(f"\n[{idx}/{len(selected_items)}] [{qtype}] ID: {qid}")
        print(f"  Q: {q_text[:90]} | Target: {gt}")

        # ----------------------------------------------------------------------
        # Setup Store & Ingest
        # ----------------------------------------------------------------------
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "memory_eval.sqlite"
            db = DatabaseManager(db_path)
            db.migrate()
            store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=embed_port)
            has_answer_by_mid: dict[int, bool] = {}

            all_raw_lines: list[str] = []
            for s_idx, (dt_str, s_turns) in enumerate(zip(dates, sessions), start=1):
                s_ts = parse_session_date(dt_str)
                s_id = f"sess_{s_idx}"
                all_raw_lines.append(f"[Session {s_idx} - Date: {dt_str}]")
                for t_idx, turn in enumerate(s_turns):
                    is_user = (turn.get("role") == "user")
                    role_str = "User" if is_user else "Assistant"
                    turn_content = f"[Date: {dt_str}] {role_str}: {turn['content']}"
                    all_raw_lines.append(f"  {role_str}: {turn['content']}")

                    signer = user_signer if is_user else assistant_signer
                    prov = Provenance.USER_EXPLICIT if is_user else Provenance.ASSISTANT_UTTERANCE
                    kind = "transcript" if is_user else "assistant_utterance"
                    unsigned = UnsignedPayload(
                        provenance=prov,
                        kind=kind,
                        content=turn_content,
                        created_at=s_ts + (t_idx * 5.0),
                        session_id=s_id,
                        trace_id=f"{s_id}:turn_{t_idx}",
                        nonce=uuid.uuid4().hex,
                    )
                    mid = store.commit(signer.sign(unsigned), now=s_ts + (t_idx * 5.0))
                    has_answer_by_mid[mid] = bool(turn.get("has_answer", False))

            # --- ARM A: Truncation (Recent Session Only) ---
            recent_session = sessions[-1] if sessions else []
            recent_date = dates[-1] if dates else q_date_str
            trunc_needle = any(turn.get("has_answer", False) for turn in recent_session)
            trunc_context = "\n".join(f"{'User' if t['role']=='user' else 'Assistant'}: {t['content']}" for t in recent_session)
            p_trunc = (
                f"--- RECENT CONVERSATIONAL HISTORY ---\n{trunc_context}\n\n"
                f"--- CURRENT QUERY ---\nCurrent Date: {q_date_str}\nUser Question: {q_text}\n\n"
                f"Answer the question directly based on past memory:"
            )
            out_trunc, _, _ = query_llm(p_trunc)
            ok_trunc = evaluate_memory_answer(out_trunc, gt)

            # --- ARM B: BM25 Sparse Only ---
            ret_q = RetrievalQuery(query_text=q_text, k=top_k)
            t0 = time.perf_counter()
            hits_bm25 = store.retriever.search(ret_q, now=q_ts, mode="bm25")
            ret_bm25_ms = (time.perf_counter() - t0) * 1000.0
            needle_bm25 = any(has_answer_by_mid.get(h.memory_id, False) for h in hits_bm25)
            ctx_bm25 = format_memory_context(hits_bm25, max_tokens=2048, now=q_ts, max_content_chars=500, max_items=top_k)
            p_bm25 = (
                f"--- PAST MEMORIES (Retrieved via BM25 Sparse FTS5) ---\n<memory>\n{ctx_bm25}\n</memory>\n\n"
                f"Current Date: {q_date_str}\nUser Question: {q_text}\n\nAnswer directly based on past memory:"
            )
            out_bm25, _, _ = query_llm(p_bm25)
            ok_bm25 = evaluate_memory_answer(out_bm25, gt)

            # --- ARM C: Dense Vector Only ---
            t0 = time.perf_counter()
            hits_dense = store.retriever.search(ret_q, now=q_ts, mode="dense")
            ret_dense_ms = (time.perf_counter() - t0) * 1000.0
            needle_dense = any(has_answer_by_mid.get(h.memory_id, False) for h in hits_dense)
            ctx_dense = format_memory_context(hits_dense, max_tokens=2048, now=q_ts, max_content_chars=500, max_items=top_k)
            p_dense = (
                f"--- PAST MEMORIES (Retrieved via Dense Cosine KNN) ---\n<memory>\n{ctx_dense}\n</memory>\n\n"
                f"Current Date: {q_date_str}\nUser Question: {q_text}\n\nAnswer directly based on past memory:"
            )
            out_dense, _, _ = query_llm(p_dense)
            ok_dense = evaluate_memory_answer(out_dense, gt)

            # --- ARM D: Lucca Hybrid Pipeline (BM25 + Dense + RRF) ---
            t0 = time.perf_counter()
            hits_hyb = store.retriever.search(ret_q, now=q_ts, mode="hybrid")
            ret_hyb_ms = (time.perf_counter() - t0) * 1000.0
            needle_hyb = any(has_answer_by_mid.get(h.memory_id, False) for h in hits_hyb)
            ctx_hyb = format_memory_context(hits_hyb, max_tokens=2048, now=q_ts, max_content_chars=500, max_items=top_k)
            p_hyb = (
                f"--- PAST MEMORIES (Lucca Hybrid Pipeline RRF k=60) ---\n<memory>\n{ctx_hyb}\n</memory>\n\n"
                f"Current Date: {q_date_str}\nUser Question: {q_text}\n\nAnswer directly based on past memory:"
            )
            out_hyb, _, _ = query_llm(p_hyb)
            ok_hyb = evaluate_memory_answer(out_hyb, gt)

            # --- ARM E: Full-Context Oracle (All Sessions Concatenated) ---
            full_haystack = "\n".join(all_raw_lines)
            p_full = (
                f"--- ENTIRE MULTI-SESSION CONVERSATIONAL HISTORY ---\n{full_haystack}\n\n"
                f"Current Date: {q_date_str}\nUser Question: {q_text}\n\nAnswer directly based on past memory:"
            )
            out_full, _, _ = query_llm(p_full, max_tokens=512)
            ok_full = evaluate_memory_answer(out_full, gt)

            db.close()

        print(f"    Arm A (Truncation): {'PASS' if ok_trunc else 'FAIL'} (needle={trunc_needle})")
        print(f"    Arm B (BM25 Only):  {'PASS' if ok_bm25 else 'FAIL'} (needle={needle_bm25}, {ret_bm25_ms:.1f}ms)")
        print(f"    Arm C (Dense Only): {'PASS' if ok_dense else 'FAIL'} (needle={needle_dense}, {ret_dense_ms:.1f}ms)")
        print(f"    Arm D (Hybrid RRF): {'PASS' if ok_hyb else 'FAIL'} (needle={needle_hyb}, {ret_hyb_ms:.1f}ms)")
        print(f"    Arm E (Full-Ctx):   {'PASS' if ok_full else 'FAIL'} (all sessions in 32k context)")

        item_records.append({
            "qid": qid,
            "qtype": qtype,
            "q_text": q_text,
            "ground_truth": gt,
            "truncation": {"correct": ok_trunc, "needle": trunc_needle, "pred": out_trunc[:80]},
            "bm25_only": {"correct": ok_bm25, "needle": needle_bm25, "pred": out_bm25[:80], "ret_ms": ret_bm25_ms},
            "dense_only": {"correct": ok_dense, "needle": needle_dense, "pred": out_dense[:80], "ret_ms": ret_dense_ms},
            "hybrid_rrf": {"correct": ok_hyb, "needle": needle_hyb, "pred": out_hyb[:80], "ret_ms": ret_hyb_ms},
            "full_context": {"correct": ok_full, "pred": out_full[:80]},
        })

    # Aggregates
    n = len(item_records)
    acc_trunc = sum(1 for r in item_records if r["truncation"]["correct"]) / n
    acc_bm25 = sum(1 for r in item_records if r["bm25_only"]["correct"]) / n
    acc_dense = sum(1 for r in item_records if r["dense_only"]["correct"]) / n
    acc_hyb = sum(1 for r in item_records if r["hybrid_rrf"]["correct"]) / n
    acc_full = sum(1 for r in item_records if r["full_context"]["correct"]) / n

    rec_trunc = sum(1 for r in item_records if r["truncation"]["needle"]) / n
    rec_bm25 = sum(1 for r in item_records if r["bm25_only"]["needle"]) / n
    rec_dense = sum(1 for r in item_records if r["dense_only"]["needle"]) / n
    rec_hyb = sum(1 for r in item_records if r["hybrid_rrf"]["needle"]) / n

    # McNemar vs Hybrid
    corrects_hyb = [r["hybrid_rrf"]["correct"] for r in item_records]
    b_t, c_t, p_trunc_vs_hyb = compute_mcnemar([r["truncation"]["correct"] for r in item_records], corrects_hyb)
    b_b, c_b, p_bm25_vs_hyb = compute_mcnemar([r["bm25_only"]["correct"] for r in item_records], corrects_hyb)
    b_d, c_d, p_dense_vs_hyb = compute_mcnemar([r["dense_only"]["correct"] for r in item_records], corrects_hyb)

    summary = {
        "benchmark": "LongMemEval_Retrieval_Ablation_Battery",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "model_tag": model_tag,
        "n_evaluated": n,
        "arms": {
            "truncation": {"accuracy": round(acc_trunc, 4), "recall_at_k": round(rec_trunc, 4)},
            "bm25_only": {"accuracy": round(acc_bm25, 4), "recall_at_k": round(rec_bm25, 4)},
            "dense_only": {"accuracy": round(acc_dense, 4), "recall_at_k": round(rec_dense, 4)},
            "hybrid_rrf": {"accuracy": round(acc_hyb, 4), "recall_at_k": round(rec_hyb, 4)},
            "full_context_oracle": {"accuracy": round(acc_full, 4), "recall_at_k": 1.0},
        },
        "mcnemar_vs_hybrid": {
            "truncation_vs_hybrid": {"discordant": [b_t, c_t], "p_value": p_trunc_vs_hyb},
            "bm25_vs_hybrid": {"discordant": [b_b, c_b], "p_value": p_bm25_vs_hyb},
            "dense_vs_hybrid": {"discordant": [b_d, c_d], "p_value": p_dense_vs_hyb},
        },
        "records": item_records,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\n[+] Saved ablation report to: {output_path}")

    print("\n" + "=" * 80)
    print("LONGMEMEVAL 5-ARM RETRIEVAL ABLATION SUMMARY")
    print("=" * 80)
    print(f"Total Evaluated: {n} items")
    print(f"  Arm A (Sliding Truncation):  Acc: {acc_trunc*100:.1f}% ({sum(1 for r in item_records if r['truncation']['correct'])}/{n}) | Recall@k: {rec_trunc*100:.1f}%")
    print(f"  Arm B (BM25 Sparse Only):   Acc: {acc_bm25*100:.1f}% ({sum(1 for r in item_records if r['bm25_only']['correct'])}/{n}) | Recall@k: {rec_bm25*100:.1f}%")
    print(f"  Arm C (Dense Vector Only):  Acc: {acc_dense*100:.1f}% ({sum(1 for r in item_records if r['dense_only']['correct'])}/{n}) | Recall@k: {rec_dense*100:.1f}%")
    print(f"  Arm D (Lucca Hybrid RRF):   Acc: {acc_hyb*100:.1f}% ({sum(1 for r in item_records if r['hybrid_rrf']['correct'])}/{n}) | Recall@k: {rec_hyb*100:.1f}%")
    print(f"  Arm E (Full-Context 32k):   Acc: {acc_full*100:.1f}% ({sum(1 for r in item_records if r['full_context']['correct'])}/{n}) | Recall@k: 100.0%")
    print("-" * 80)
    print(f"  Hybrid Lift vs Truncation:  +{(acc_hyb - acc_trunc)*100:.1f} pp (McNemar b={b_t}, c={c_t}, p={p_trunc_vs_hyb:.4f})")
    print(f"  Hybrid Lift vs BM25:        +{(acc_hyb - acc_bm25)*100:.1f} pp (McNemar b={b_b}, c={c_b}, p={p_bm25_vs_hyb:.4f})")
    print(f"  Hybrid Lift vs Dense:       +{(acc_hyb - acc_dense)*100:.1f} pp (McNemar b={b_d}, c={c_d}, p={p_dense_vs_hyb:.4f})")
    print("=" * 80)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="LongMemEval Retrieval Ablation Battery")
    parser.add_argument("--limit-per-type", type=int, default=5, help="Items per category (default: 5, total 15)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    parser.add_argument("--model-tag", type=str, default="E2B", help="Active model tier tag")
    parser.add_argument("--top-k", type=int, default=12, help="Top-K retrieval limit")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON path")
    args = parser.parse_args()

    out_p = args.output
    if out_p is None:
        out_p = REPO_ROOT / "logs" / "test_reports" / f"longmemeval_ablation_{args.model_tag}_{int(time.time())}.json"

    run_ablation_battery(
        limit_per_type=args.limit_per_type,
        seed=args.seed,
        model_tag=args.model_tag,
        top_k=args.top_k,
        output_path=out_p,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
