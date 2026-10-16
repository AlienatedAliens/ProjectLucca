#!/usr/bin/env python3
"""
Project Lucca — LongMemEval End-to-End Pipeline Benchmark Runner
Evaluates Lucca's real compound memory subsystem (SQLite-vec KNN + FTS5 BM25 RRF)
against bare sliding-window conversational truncation on resident local models.

Compares:
- Arm A (Bare History Truncation Baseline): Only recent conversational session in context.
- Arm B (Lucca Compound Memory Pipeline): Past sessions ingested into Lucca SQLite store,
  queried via HybridRetriever (sqlite-vec + FTS5 + RRF), rendered via canonical prompt context.

Measures:
1. Retrieval Recall@k (needle identification)
2. End-to-End Answer Accuracy
3. Discordant pairs (b, c) & exact two-sided McNemar p-value
4. Latencies, token counts, and truncation statistics
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


@dataclass
class PipelineResult:
    question_id: str
    question_type: str
    question: str
    ground_truth: str
    # Arm A: Truncation
    trunc_needle_in_context: bool
    trunc_prediction: str
    trunc_correct: bool
    trunc_latency_s: float
    trunc_finish_reason: str
    trunc_tokens: int
    # Arm B: Lucca Memory Pipeline
    pipeline_retrieval_ms: float
    pipeline_hits_count: int
    pipeline_needle_retrieved: bool
    pipeline_prediction: str
    pipeline_correct: bool
    pipeline_latency_s: float
    pipeline_finish_reason: str
    pipeline_tokens: int


def query_llm(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
    enable_thinking: bool = False,
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
    if not enable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        res = client.post(SERVER_URL, json=payload)
        res.raise_for_status()
        data = res.json()
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason") or "unknown"
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        msg = choice["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        if content.strip() and reasoning.strip():
            text = f"{content}\n[REASONING]\n{reasoning}"
        else:
            text = content if content.strip() else reasoning
        return text, finish_reason, completion_tokens


def evaluate_memory_answer(prediction: str, ground_truth: str | int) -> bool:
    if not prediction:
        return False
    pred_lower = prediction.lower()
    gt_lower = str(ground_truth).lower()

    # Abstention equivalence check (for _abs unanswerable items)
    if ("not enough" in gt_lower or "did not mention" in gt_lower) and (
        "not have enough information" in pred_lower
        or "not enough information" in pred_lower
        or "cannot be determined" in pred_lower
        or "didn't mention" in pred_lower
        or "did not mention" in pred_lower
    ):
        return True

    # Direct substring check
    if gt_lower in pred_lower:
        return True

    # Check key alternative phrases if ground truth has 'or' / 'acceptable'
    for part in re.split(r"\s+or\s+|\.|\(|\)", gt_lower):
        part = part.strip()
        if len(part) > 3 and part in pred_lower:
            return True

    # Check numeric extraction if ground truth contains numbers (e.g. "4 days", "25:50")
    gt_nums = re.findall(r"\b\d+(?::\d+)?\b", gt_lower)
    if gt_nums:
        pred_nums = re.findall(r"\b\d+(?::\d+)?\b", pred_lower)
        if any(gn in pred_nums for gn in gt_nums):
            keywords = [w for w in re.findall(r"\b\w{4,}\b", gt_lower) if w not in ("days", "time", "date", "acceptable")]
            if not keywords or any(kw in pred_lower for kw in keywords):
                return True

    # Entity keyword overlap
    gt_words = set(re.findall(r"\b\w{3,}\b", gt_lower)) - {"the", "and", "was", "for", "with", "also", "acceptable"}
    pred_words = set(re.findall(r"\b\w{3,}\b", pred_lower))
    if gt_words and (len(gt_words & pred_words) / len(gt_words) >= 0.75):
        return True

    return False


def parse_session_date(dt_str: str) -> float:
    """Parses date string into unix epoch timestamp."""
    m = re.match(r"^(\d{4})[/-](\d{2})[/-](\d{2}).*?(\d{2}):(\d{2})", dt_str.strip())
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()
    return 1680000000.0


def run_pipeline_benchmark(
    limit_per_type: int = 10,
    seed: int = 42,
    model_tag: str = "12B",
    top_k: int = 12,
    direct_cap: int = 512,
    thinking_cap: int = 2048,
    enable_thinking: bool = False,
    question_types: list[str] | None = None,
) -> None:
    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: LongMemEval FULL PIPELINE BENCHMARK (Compound vs Bare) ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    mode_str = f"Extended Thinking (cap={thinking_cap})" if enable_thinking else f"Direct Zero-Shot (cap={direct_cap})"
    print(f"Model: {model_tag} | Mode: {mode_str} | Top-K: {top_k}", flush=True)
    print(f"Dataset: {DATA_FILE.name} (limit={limit_per_type} per type, seed={seed})\n", flush=True)

    data = json.load(open(DATA_FILE, encoding="utf-8"))
    types = question_types or ["knowledge-update", "temporal-reasoning", "multi-session"]

    rng = random.Random(seed)
    selected_items: list[dict[str, Any]] = []

    for t in types:
        sub = [x for x in data if x.get("question_type") == t]
        rng.shuffle(sub)
        selected_items.extend(sub[:limit_per_type])

    # Shared OpenVINO embedding port for memory indexing
    embed_port = LocalEmbeddingPort(worker=EmbedWorker(device="CPU"))
    user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)
    assistant_signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)

    results: list[PipelineResult] = []

    for idx, item in enumerate(selected_items, start=1):
        qid = item["question_id"]
        qtype = item.get("question_type", "unknown")
        q_text = item["question"]
        gt = item["answer"]
        q_date_str = item.get("question_date", "2023/06/01 (Thu) 12:00")
        q_ts = parse_session_date(q_date_str)

        dates = item.get("haystack_dates", [])
        sessions = item.get("haystack_sessions", [])

        print(f"[{idx}/{len(selected_items)}] [{qtype}] ID: {qid}", flush=True)
        print(f"  Question: {q_text}", flush=True)
        print(f"  Target: {gt}", flush=True)

        # ---------------------------------------------------------
        # Arm A: Bare History Truncation (Sliding Window Baseline)
        # ---------------------------------------------------------
        recent_session = sessions[-1] if sessions else []
        recent_date = dates[-1] if dates else q_date_str
        trunc_needle = any(turn.get("has_answer", False) for turn in recent_session)

        trunc_lines = [f"[Recent Session - Date: {recent_date}]"]
        for turn in recent_session:
            role_label = "User" if turn["role"] == "user" else "Assistant"
            trunc_lines.append(f"{role_label}: {turn['content']}")
        trunc_context = "\n".join(trunc_lines)

        trunc_prompt = (
            f"--- RECENT CONVERSATIONAL HISTORY ---\n"
            f"{trunc_context}\n\n"
            f"--- CURRENT QUERY ---\n"
            f"Current Date: {q_date_str}\n"
            f"User Question: {q_text}\n\n"
            f"Answer the question directly based on past memory:"
        )

        t0 = time.perf_counter()
        try:
            cap = thinking_cap if enable_thinking else direct_cap
            temp = 0.6 if enable_thinking else 0.0
            t_out, t_fin, t_tok = query_llm(trunc_prompt, max_tokens=cap, temperature=temp, enable_thinking=enable_thinking)
            t_sec = time.perf_counter() - t0
            t_ok = evaluate_memory_answer(t_out, gt)
        except Exception as exc:
            t_out, t_fin, t_tok, t_ok, t_sec = f"Error: {exc}", "error", 0, False, 0.0

        # ---------------------------------------------------------
        # Arm B: Lucca Compound Memory Pipeline (Hybrid RRF Store)
        # ---------------------------------------------------------
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "memory_eval.sqlite"
            db = DatabaseManager(db_path)
            db.migrate()
            store = MemoryStore(db=db, master_key=TEST_MASTER_KEY, embedding_port=embed_port)

            has_answer_by_mid: dict[int | str, bool] = {}

            # Ingest all sessions into Lucca store
            for s_idx, (dt_str, s_turns) in enumerate(zip(dates, sessions), start=1):
                s_ts = parse_session_date(dt_str)
                s_id = f"sess_{s_idx}"
                for t_idx, turn in enumerate(s_turns):
                    is_user = (turn.get("role") == "user")
                    role_str = "User" if is_user else "Assistant"
                    turn_content = f"[Date: {dt_str}] {role_str}: {turn['content']}"

                    if is_user:
                        unsigned = UnsignedPayload(
                            provenance=Provenance.USER_EXPLICIT,
                            kind="transcript",
                            content=turn_content,
                            created_at=s_ts + (t_idx * 5.0),
                            session_id=s_id,
                            trace_id=f"{s_id}:turn_{t_idx}",
                            nonce=uuid.uuid4().hex,
                        )
                        signed = user_signer.sign(unsigned)
                    else:
                        unsigned = UnsignedPayload(
                            provenance=Provenance.ASSISTANT_UTTERANCE,
                            kind="assistant_utterance",
                            content=turn_content,
                            created_at=s_ts + (t_idx * 5.0),
                            session_id=s_id,
                            trace_id=f"{s_id}:turn_{t_idx}",
                            nonce=uuid.uuid4().hex,
                        )
                        signed = assistant_signer.sign(unsigned)

                    mid = store.commit(signed, now=s_ts + (t_idx * 5.0))
                    has_answer_by_mid[mid] = bool(turn.get("has_answer", False))

            # Query Lucca Hybrid Retriever
            t_ret0 = time.perf_counter()
            retrieval_query = RetrievalQuery(query_text=q_text, k=top_k)
            hits = store.retriever.search(retrieval_query, now=q_ts)
            retrieval_ms = (time.perf_counter() - t_ret0) * 1000.0

            pipeline_needle = any(has_answer_by_mid.get(h.memory_id, False) for h in hits)
            rendered_memories = format_memory_context(hits, max_tokens=2048, now=q_ts, max_content_chars=500, max_items=top_k)
            db.close()

        pipeline_prompt = (
            f"--- PAST MEMORIES (Retrieved from Lucca Hybrid Store, Grouped by Session) ---\n"
            f"<memory>\n"
            f"{rendered_memories}\n"
            f"</memory>\n\n"
            f"--- CURRENT QUERY ---\n"
            f"Current Date: {q_date_str}\n"
            f"User Question: {q_text}\n\n"
            f"Instructions: Synthesize facts across all retrieved sessions chronologically. "
            f"When asked for a total, sum, or difference across sessions, combine every relevant session's numbers carefully.\n"
            f"Answer the question directly based on past memory:"
        )

        t0 = time.perf_counter()
        try:
            p_out, p_fin, p_tok = query_llm(pipeline_prompt, max_tokens=cap, temperature=temp, enable_thinking=enable_thinking)
            p_sec = time.perf_counter() - t0
            p_ok = evaluate_memory_answer(p_out, gt)
        except Exception as exc:
            p_out, p_fin, p_tok, p_ok, p_sec = f"Error: {exc}", "error", 0, False, 0.0

        r = PipelineResult(
            question_id=qid,
            question_type=qtype,
            question=q_text,
            ground_truth=gt,
            trunc_needle_in_context=trunc_needle,
            trunc_prediction=t_out[:120].replace("\n", " "),
            trunc_correct=t_ok,
            trunc_latency_s=round(t_sec, 2),
            trunc_finish_reason=t_fin,
            trunc_tokens=t_tok,
            pipeline_retrieval_ms=round(retrieval_ms, 1),
            pipeline_hits_count=len(hits),
            pipeline_needle_retrieved=pipeline_needle,
            pipeline_prediction=p_out[:120].replace("\n", " "),
            pipeline_correct=p_ok,
            pipeline_latency_s=round(p_sec, 2),
            pipeline_finish_reason=p_fin,
            pipeline_tokens=p_tok,
        )
        results.append(r)

        t_needle_str = "NEEDLE_IN" if trunc_needle else "NEEDLE_OUT"
        p_needle_str = "RECALL_HIT" if pipeline_needle else "RECALL_MISS"
        print(
            f"  [Truncation]: {'PASS' if t_ok else 'FAIL'} ({t_needle_str}) [{t_sec:.2f}s] | "
            f"[Lucca Pipeline]: {'PASS' if p_ok else 'FAIL'} ({p_needle_str}, {retrieval_ms:.0f}ms ret) [{p_sec:.2f}s]",
            flush=True,
        )

    # ---------------------------------------------------------
    # Comprehensive Summary & McNemar Statistics
    # ---------------------------------------------------------
    print("\n" + "=" * 75)
    print("=== PROJECT LUCCA: LongMemEval FULL PIPELINE EVALUATION SUMMARY ===")
    print("=" * 75)
    n = len(results)

    for t in types:
        t_res = [r for r in results if r.question_type == t]
        sub_n = len(t_res)
        if sub_n == 0:
            continue
        t_trunc_rec = sum(1 for r in t_res if r.trunc_needle_in_context)
        t_trunc_acc = sum(1 for r in t_res if r.trunc_correct)
        t_pipe_rec = sum(1 for r in t_res if r.pipeline_needle_retrieved)
        t_pipe_acc = sum(1 for r in t_res if r.pipeline_correct)

        print(
            f"Category {t:<22} (n={sub_n}): "
            f"Trunc Recall {t_trunc_rec}/{sub_n} ({t_trunc_rec/sub_n*100:4.1f}%) -> Acc {t_trunc_acc}/{sub_n} ({t_trunc_acc/sub_n*100:4.1f}%) | "
            f"Pipe Recall {t_pipe_rec}/{sub_n} ({t_pipe_rec/sub_n*100:4.1f}%) -> Acc {t_pipe_acc}/{sub_n} ({t_pipe_acc/sub_n*100:4.1f}%)"
        )

    tot_trunc_rec = sum(1 for r in results if r.trunc_needle_in_context)
    tot_trunc_acc = sum(1 for r in results if r.trunc_correct)
    tot_pipe_rec = sum(1 for r in results if r.pipeline_needle_retrieved)
    tot_pipe_acc = sum(1 for r in results if r.pipeline_correct)

    b = sum(1 for r in results if r.trunc_correct and not r.pipeline_correct)
    c = sum(1 for r in results if not r.trunc_correct and r.pipeline_correct)

    try:
        from scipy.stats import binomtest
        p_val = binomtest(min(b, c), b + c, 0.5).pvalue if (b + c) > 0 else 1.0
    except ImportError:
        p_val = math.erfc((abs(b - c) - 1) / math.sqrt(2 * (b + c))) if (b + c) > 0 else 1.0

    print("-" * 75)
    print(f"TOTAL RETRIEVAL RECALL@k: Truncation = {tot_trunc_rec}/{n} ({tot_trunc_rec/n*100:.1f}%) | Lucca Pipeline = {tot_pipe_rec}/{n} ({tot_pipe_rec/n*100:.1f}%)")
    print(f"TOTAL ANSWER ACCURACY:   Truncation = {tot_trunc_acc}/{n} ({tot_trunc_acc/n*100:.1f}%) | Lucca Pipeline = {tot_pipe_acc}/{n} ({tot_pipe_acc/n*100:.1f}%)")
    print(f"McNemar Discordant Pairs: b (Trunc+, Pipe-)={b}, c (Trunc-, Pipe+)={c} | p-value = {p_val:.4f}")
    avg_ret_ms = sum(r.pipeline_retrieval_ms for r in results) / n
    print(f"Average Hybrid Retrieval Latency: {avg_ret_ms:.1f} ms")
    print("=" * 75)

    out_dir = REPO_ROOT / "logs" / "test_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"longmemeval_pipeline_{model_tag}_{int(time.time())}.json"
    report_data = {
        "benchmark": "LongMemEval-Pipeline",
        "model_tag": model_tag,
        "mode": "Extended Thinking" if enable_thinking else "Direct Zero-Shot",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_problems": n,
        "top_k": top_k,
        "truncation_needle_recall_pct": round(tot_trunc_rec / n * 100, 1),
        "truncation_accuracy_pct": round(tot_trunc_acc / n * 100, 1),
        "pipeline_needle_recall_pct": round(tot_pipe_rec / n * 100, 1),
        "pipeline_accuracy_pct": round(tot_pipe_acc / n * 100, 1),
        "discordant_b": b,
        "discordant_c": c,
        "mcnemar_p_value": round(p_val, 4),
        "avg_retrieval_ms": round(avg_ret_ms, 1),
        "per_category": {
            t: {
                "trunc_recall_pct": sum(1 for r in results if r.question_type == t and r.trunc_needle_in_context) / len([r for r in results if r.question_type == t]) * 100.0,
                "trunc_acc_pct": sum(1 for r in results if r.question_type == t and r.trunc_correct) / len([r for r in results if r.question_type == t]) * 100.0,
                "pipeline_recall_pct": sum(1 for r in results if r.question_type == t and r.pipeline_needle_retrieved) / len([r for r in results if r.question_type == t]) * 100.0,
                "pipeline_acc_pct": sum(1 for r in results if r.question_type == t and r.pipeline_correct) / len([r for r in results if r.question_type == t]) * 100.0,
            }
            for t in types
        },
        "results": [asdict(r) for r in results],
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\n[+] Saved full benchmark report to: {report_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LongMemEval End-to-End Pipeline Benchmark Runner")
    parser.add_argument("--limit", type=int, default=10, help="Items per category (default: 10)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed (default: 42)")
    parser.add_argument("--model-tag", type=str, default="12B", help="Model tier tag (default: 12B)")
    parser.add_argument("--top-k", type=int, default=8, help="Retrieval top-k (default: 8)")
    parser.add_argument("--direct-cap", type=int, default=512, help="Direct token cap (default: 512)")
    parser.add_argument("--thinking-cap", type=int, default=2048, help="Thinking token cap (default: 2048)")
    parser.add_argument("--thinking", action="store_true", help="Enable extended thinking")
    parser.add_argument("--types", nargs="+", default=None, help="Filter by question types (e.g. temporal-reasoning)")
    args = parser.parse_args()

    run_pipeline_benchmark(
        limit_per_type=args.limit,
        seed=args.seed,
        model_tag=args.model_tag,
        top_k=args.top_k,
        direct_cap=args.direct_cap,
        thinking_cap=args.thinking_cap,
        enable_thinking=args.thinking,
        question_types=args.types,
    )
