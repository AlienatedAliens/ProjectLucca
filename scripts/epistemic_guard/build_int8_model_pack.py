"""Build, fine-tune, quantize (NNCF INT8), and benchmark the standalone `epistemic-guard` model pack.

Produces four INT8 OpenVINO models under `models/epistemic_guard_int8/`:
  1. `action_claim_int8` — 10-class `(user_request, assistant_clause)` speech-act & tool-family verifier
  2. `hazard_int8`       — 5-class clause-level hazard classifier (`LOW`, `MEDIUM`, `HIGH`, ...)
  3. `web_evidence_int8` — RTX 5080 fine-tuned 3-class `(query, passage)` open-web evidence classifier
                           (`0: CORROBORATES`, `1: IRRELEVANT`, `2: DISPUTES`, zero benchmark overlap)
  4. `nli_int8`          — 3-class `(premise, hypothesis)` DeBERTa-v3-xsmall NLI cross-encoder
                           (`0: contradiction`, `1: entailment`, `2: neutral`, MIT/Apache-2.0)

Records SHA-256 digests, file sizes, CPU latencies, and locked-holdout accuracy parity in
`logs/test_reports/epistemic_guard/int8_model_pack_report.json`.
Does NOT modify any locked `WO-45` or `WO-46` files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import nncf
import numpy as np
import openvino as ov
import torch
import torch.nn as nn
from tokenizers import Tokenizer
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts" / "epistemic_guard") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "epistemic_guard"))

from web_evidence_corpus import (  # noqa: E402
    WEB_EVIDENCE_LABELS,
    build_disjoint_web_evidence_splits,
)

PACK_ROOT: Final[Path] = REPO_ROOT / "models" / "epistemic_guard_int8"
REPORT_OUT: Final[Path] = (
    REPO_ROOT / "logs" / "test_reports" / "epistemic_guard" / "int8_model_pack_report.json"
)

WEB_BASE_CHECKPOINT: Final[str] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
WEB_SEQ_LEN: Final[int] = 192
ACTION_SEQ_LEN: Final[int] = 192
HAZARD_SEQ_LEN: Final[int] = 64
NLI_SEQ_LEN: Final[int] = 128

SPEECH_ACT_CLASSES: Final[tuple[str, ...]] = (
    "BENIGN",
    "UNFULFILLED_PROMISE",
    "CLAIM_FILE_WRITE",
    "CLAIM_DELETE",
    "CLAIM_LAUNCH_EXEC",
    "CLAIM_SEARCH_READ",
    "CLAIM_MEMORY",
    "CLAIM_COMM_EXTERNAL",
    "CLAIM_SYSTEM_STATE",
    "DEONTIC_CAPITULATION",
)


class _TraceableBertClassifier(nn.Module):
    """Traces `BertForSequenceClassification` cleanly on Transformers >= 5.5 without SDPA mask bugs."""

    def __init__(self, m: Any) -> None:
        super().__init__()
        self.embeddings = m.bert.embeddings
        self.layers = m.bert.encoder.layer
        self.pooler = m.bert.pooler
        self.classifier = m.classifier

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        token_type_ids: torch.Tensor,
    ) -> torch.Tensor:
        ext_mask = (1.0 - attention_mask[:, None, None, :].to(torch.float32)) * -10000.0
        h = self.embeddings(input_ids=input_ids, token_type_ids=token_type_ids)
        for layer in self.layers:
            out_l = layer(h, ext_mask)
            h = out_l[0] if isinstance(out_l, tuple) else out_l
        pooled = self.pooler(h)
        res: torch.Tensor = self.classifier(pooled)
        return res


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_dir_manifest(model_dir: Path, upstream_model: str, upstream_license: str) -> dict[str, Any]:
    files_info: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for fpath in sorted(model_dir.iterdir()):
        if fpath.is_file():
            sz = fpath.stat().st_size
            total_bytes += sz
            files_info[fpath.name] = {
                "size_bytes": sz,
                "sha256": sha256_file(fpath),
            }
    return {
        "upstream_base_model": upstream_model,
        "upstream_license": upstream_license,
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "files": files_info,
    }


def benchmark_cpu_latency(infer_req: ov.InferRequest, seq_len: int, n_runs: int = 100) -> dict[str, float]:
    ids = np.ones((1, seq_len), dtype=np.int64)
    mask = np.ones((1, seq_len), dtype=np.int64)
    for _ in range(10):
        infer_req.infer({"input_ids": ids, "attention_mask": mask})
    timings: list[float] = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        infer_req.infer({"input_ids": ids, "attention_mask": mask})
        timings.append((time.perf_counter() - t0) * 1000.0)
    timings.sort()
    p95_idx = min(len(timings) - 1, int(0.95 * len(timings)))
    return {
        "mean_ms": round(statistics.mean(timings), 3),
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(timings[p95_idx], 3),
    }


def train_and_quantize_web_evidence() -> dict[str, Any]:
    print("=== [1/3] Training & INT8-quantizing web_evidence_int8 on GPU ===")
    seed = 20261113
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    train_rows, val_rows, overlap_stats = build_disjoint_web_evidence_splits(REPO_ROOT, seed=seed)
    print(f"Disjoint check passed: {overlap_stats}")
    print(f"Train pairs: {len(train_rows)}, Unseen-topic Val pairs: {len(val_rows)}")

    hf_tok = AutoTokenizer.from_pretrained(WEB_BASE_CHECKPOINT, local_files_only=True)
    cfg = AutoConfig.from_pretrained(WEB_BASE_CHECKPOINT, local_files_only=True)
    cfg.num_labels = 3
    cfg.id2label = {str(i): lbl for i, lbl in enumerate(WEB_EVIDENCE_LABELS)}
    cfg.label2id = {lbl: i for i, lbl in enumerate(WEB_EVIDENCE_LABELS)}
    cfg.attn_implementation = "eager"
    model = AutoModelForSequenceClassification.from_pretrained(
        WEB_BASE_CHECKPOINT,
        config=cfg,
        ignore_mismatched_sizes=True,
        attn_implementation="eager",
        local_files_only=True,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    def _encode_rows(rows: list[tuple[str, str, int]]) -> TensorDataset:
        enc = hf_tok(
            [r[0] for r in rows],
            [r[1] for r in rows],
            padding="max_length",
            truncation=True,
            max_length=WEB_SEQ_LEN,
            return_token_type_ids=True,
            return_tensors="pt",
        )
        labels = torch.tensor([r[2] for r in rows], dtype=torch.long)
        return TensorDataset(enc["input_ids"], enc["attention_mask"], enc["token_type_ids"], labels)

    train_ds = _encode_rows(train_rows)
    val_ds = _encode_rows(val_rows)
    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True)

    backbone_params = [p for n, p in model.named_parameters() if not n.startswith("classifier.")]
    head_params = [p for n, p in model.named_parameters() if n.startswith("classifier.")]
    optimizer = torch.optim.AdamW(
        [
            {"params": backbone_params, "lr": 4.5e-5},
            {"params": head_params, "lr": 2.0e-4},
        ],
        weight_decay=0.01,
    )
    epochs = 10
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=max(1, epochs * len(train_loader))
    )
    criterion = nn.CrossEntropyLoss()

    best_val_acc = 0.0
    best_state: dict[str, torch.Tensor] | None = None
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for b_ids, b_mask, b_tt, b_lbl in train_loader:
            b_ids = b_ids.to(device)
            b_mask = b_mask.to(device)
            b_tt = b_tt.to(device)
            b_lbl = b_lbl.to(device)
            optimizer.zero_grad()
            logits = model(input_ids=b_ids, attention_mask=b_mask, token_type_ids=b_tt).logits
            loss = criterion(logits, b_lbl)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += float(loss.item())

        model.eval()
        with torch.no_grad():
            v_ids, v_mask, v_tt, v_lbl = [t.to(device) for t in val_ds.tensors]
            v_logits = model(
                input_ids=v_ids,
                attention_mask=v_mask,
                token_type_ids=v_tt,
            ).logits
            preds = torch.argmax(v_logits, dim=-1)
            acc = float((preds == v_lbl).float().mean().item())
        print(f"  Epoch {epoch}/{epochs}: loss={total_loss / len(train_loader):.4f} unseen_val_acc={acc * 100:.2f}%")
        if acc >= best_val_acc:
            best_val_acc = acc
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    assert best_state is not None
    model.load_state_dict(best_state)
    model.cpu().eval()

    out_dir = PACK_ROOT / "web_evidence_int8"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hf_tok.save_pretrained(str(out_dir))
    cfg.save_pretrained(str(out_dir))
    for extra in list(out_dir.iterdir()):
        if extra.name not in ("config.json", "tokenizer.json"):
            extra.unlink()

    wrapper = _TraceableBertClassifier(model).eval()
    dummy_ids = torch.ones((1, WEB_SEQ_LEN), dtype=torch.long)
    dummy_mask = torch.ones((1, WEB_SEQ_LEN), dtype=torch.long)
    dummy_tt = torch.zeros((1, WEB_SEQ_LEN), dtype=torch.long)
    ov_fp = ov.convert_model(
        wrapper,
        example_input={
            "input_ids": dummy_ids,
            "attention_mask": dummy_mask,
            "token_type_ids": dummy_tt,
        },
        input=[
            ("input_ids", [1, WEB_SEQ_LEN], ov.Type.i64),
            ("attention_mask", [1, WEB_SEQ_LEN], ov.Type.i64),
            ("token_type_ids", [1, WEB_SEQ_LEN], ov.Type.i64),
        ],
    )
    ov_fp.reshape(
        {
            "input_ids": [1, WEB_SEQ_LEN],
            "attention_mask": [1, WEB_SEQ_LEN],
            "token_type_ids": [1, WEB_SEQ_LEN],
        }
    )

    fast_tok = Tokenizer.from_file(str(out_dir / "tokenizer.json"))
    fast_tok.enable_truncation(max_length=WEB_SEQ_LEN)
    fast_tok.enable_padding(length=WEB_SEQ_LEN, pad_id=0, pad_token="[PAD]")

    def _calib_transform(item: tuple[str, str, int]) -> dict[str, np.ndarray]:
        enc = fast_tok.encode(item[0], item[1])
        return {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([enc.type_ids], dtype=np.int64),
        }

    calib_rows = train_rows[:256]
    ov_int8 = nncf.quantize(
        ov_fp,
        nncf.Dataset(calib_rows, _calib_transform),
        model_type=nncf.ModelType.TRANSFORMER,
        subset_size=min(256, len(calib_rows)),
    )
    ov.save_model(ov_int8, str(out_dir / "openvino_model.xml"))

    core = ov.Core()
    fp_req = core.compile_model(ov_fp, "CPU").create_infer_request()
    int8_req = core.compile_model(str(out_dir / "openvino_model.xml"), "CPU").create_infer_request()

    fp_correct = 0
    int8_correct = 0
    agree = 0
    for q, p, gold in val_rows:
        inp = _calib_transform((q, p, gold))
        fp_pred = int(np.argmax(list(fp_req.infer(inp).values())[0][0]))
        i8_pred = int(np.argmax(list(int8_req.infer(inp).values())[0][0]))
        fp_correct += int(fp_pred == gold)
        int8_correct += int(i8_pred == gold)
        agree += int(fp_pred == i8_pred)

    # Benchmark 3-input latency for web_evidence_int8
    ids_b = np.ones((1, WEB_SEQ_LEN), dtype=np.int64)
    msk_b = np.ones((1, WEB_SEQ_LEN), dtype=np.int64)
    tt_b = np.zeros((1, WEB_SEQ_LEN), dtype=np.int64)
    for _ in range(10):
        int8_req.infer({"input_ids": ids_b, "attention_mask": msk_b, "token_type_ids": tt_b})
    timings: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter()
        int8_req.infer({"input_ids": ids_b, "attention_mask": msk_b, "token_type_ids": tt_b})
        timings.append((time.perf_counter() - t0) * 1000.0)
    timings.sort()
    lat = {
        "mean_ms": round(statistics.mean(timings), 3),
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(timings[min(99, int(0.95 * len(timings)))], 3),
    }
    n_val = len(val_rows)
    return {
        "disjoint_verification": overlap_stats,
        "train_count": len(train_rows),
        "unseen_topic_val_count": n_val,
        "fp_val_correct": fp_correct,
        "fp_val_accuracy_pct": round(fp_correct / n_val * 100.0, 2),
        "int8_val_correct": int8_correct,
        "int8_val_accuracy_pct": round(int8_correct / n_val * 100.0, 2),
        "fp_vs_int8_agreement_pct": round(agree / n_val * 100.0, 2),
        "cpu_latency": lat,
        "manifest": collect_dir_manifest(out_dir, WEB_BASE_CHECKPOINT, "Apache-2.0"),
    }


def quantize_and_eval_hazard() -> dict[str, Any]:
    print("=== [2/3] INT8-quantizing & benchmarking hazard_int8 ===")
    src_dir = REPO_ROOT / "models" / "proof_policy_hazard_v3_ov"
    out_dir = PACK_ROOT / "hazard_int8"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(src_dir / "config.json", out_dir / "config.json")
    shutil.copy2(src_dir / "tokenizer.json", out_dir / "tokenizer.json")

    tok = Tokenizer.from_file(str(out_dir / "tokenizer.json"))
    tok.enable_truncation(max_length=HAZARD_SEQ_LEN)
    tok.enable_padding(length=HAZARD_SEQ_LEN, pad_id=1, pad_token="<pad>")

    train_path = REPO_ROOT / "data" / "benchmarks" / "supervision_heldout" / "wo42_hazard_train.jsonl"
    r42_path = REPO_ROOT / "data" / "benchmarks" / "supervision_heldout" / "wo45_r42_disjoint_hardneg_train.jsonl"
    calib_texts: list[str] = []
    for p in (train_path, r42_path):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                calib_texts.append(str(json.loads(line)["text"]))
    random.Random(20261113).shuffle(calib_texts)

    def _transform(text: str) -> dict[str, np.ndarray]:
        enc = tok.encode(text)
        return {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }

    core = ov.Core()
    ov_fp = core.read_model(str(src_dir / "openvino_model.xml"))
    ov_int8 = nncf.quantize(
        ov_fp,
        nncf.Dataset(calib_texts[:256], _transform),
        model_type=nncf.ModelType.TRANSFORMER,
        subset_size=min(256, len(calib_texts)),
    )
    ov.save_model(ov_int8, str(out_dir / "openvino_model.xml"))

    fp_req = core.compile_model(str(src_dir / "openvino_model.xml"), "CPU").create_infer_request()
    int8_req = core.compile_model(str(out_dir / "openvino_model.xml"), "CPU").create_infer_request()

    # Evaluate on locked HZD_50
    hzd50_path = REPO_ROOT / "data" / "benchmarks" / "supervision_heldout" / "wo41_phase4_hazard_test_50.jsonl"
    hzd_rows = [json.loads(l) for l in hzd50_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    cls_names = ("LOW", "MEDIUM", "HIGH", "CROSS_REFERENCE_CMD", "UNKNOWN_FAIL_CLOSED")
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

    def _pred_tier(req: ov.InferRequest, text: str) -> str:
        logits = np.asarray(list(req.infer(_transform(text)).values())[0], dtype=np.float64)[0]
        probs = np.exp(logits - np.max(logits))
        probs /= np.sum(probs)
        probs[3] = 0.0
        if np.sum(probs) > 0:
            probs /= np.sum(probs)
        idx = int(np.argmax(probs))
        conf = float(probs[idx])
        c = cls_names[idx]
        if c == "LOW" and conf >= 0.65:
            return "LOW"
        if c == "MEDIUM" and conf >= 0.65:
            return "MEDIUM"
        return "HIGH"

    fp_hzd50 = sum(int(_pred_tier(fp_req, r["text"]) == r["gold_label"]) for r in hzd_rows)
    i8_hzd50 = sum(int(_pred_tier(int8_req, r["text"]) == r["gold_label"]) for r in hzd_rows)

    # Evaluate clause-pooled conservative safety on locked R-21 (N=130)
    if str(REPO_ROOT / "packages" / "lucca-epistemic" / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "packages" / "lucca-epistemic" / "src"))
    from lucca_epistemic.hazard import OpenVINOHazardClassifier  # noqa: E402

    clf_fp = OpenVINOHazardClassifier(model_dir=src_dir, device="CPU")
    clf_i8 = OpenVINOHazardClassifier(model_dir=out_dir, device="CPU")

    r21_corpus = [
        json.loads(l)
        for l in (REPO_ROOT / "data" / "benchmarks" / "wo45_r21_multiclause_hazard_130.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if l.strip()
    ]
    r21_gold = {
        json.loads(l)["item_id"]: str(json.loads(l)["label"]).upper()
        for l in (REPO_ROOT / "logs" / "test_reports" / "wo45" / "r21_rater1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if l.strip()
    }
    fp_r21_safe = 0
    i8_r21_safe = 0
    r21_agree = 0
    for row in r21_corpus:
        gold = r21_gold[row["item_id"]]
        p_fp = clf_fp.evaluate(row["query"]).hazard.value.upper()
        p_i8 = clf_i8.evaluate(row["query"]).hazard.value.upper()
        fp_r21_safe += int(rank[p_fp] >= rank[gold])
        i8_r21_safe += int(rank[p_i8] >= rank[gold])
        r21_agree += int(p_fp == p_i8)

    lat = benchmark_cpu_latency(int8_req, HAZARD_SEQ_LEN)
    return {
        "hzd50_fp_exact": f"{fp_hzd50}/{len(hzd_rows)}",
        "hzd50_int8_exact": f"{i8_hzd50}/{len(hzd_rows)}",
        "r21_fp_safe": f"{fp_r21_safe}/{len(r21_corpus)} ({fp_r21_safe / len(r21_corpus) * 100:.2f}%)",
        "r21_int8_safe": f"{i8_r21_safe}/{len(r21_corpus)} ({i8_r21_safe / len(r21_corpus) * 100:.2f}%)",
        "r21_fp_vs_int8_agreement_pct": round(r21_agree / len(r21_corpus) * 100.0, 2),
        "cpu_latency": lat,
        "manifest": collect_dir_manifest(
            out_dir, "cross-encoder/nli-MiniLM2-L6-H768", "Apache-2.0"
        ),
    }


def quantize_and_eval_action_claim() -> dict[str, Any]:
    print("=== [3/3] INT8-quantizing & benchmarking action_claim_int8 ===")
    src_dir = REPO_ROOT / "models" / "action_claim_verifier_ov"
    out_dir = PACK_ROOT / "action_claim_int8"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(src_dir / "tokenizer.json", out_dir / "tokenizer.json")
    cfg_payload = {
        "architectures": ["RobertaForSequenceClassification"],
        "model_type": "roberta",
        "num_labels": 10,
        "max_seq_length": ACTION_SEQ_LEN,
        "id2label": {str(i): c for i, c in enumerate(SPEECH_ACT_CLASSES)},
        "label2id": {c: i for i, c in enumerate(SPEECH_ACT_CLASSES)},
    }
    (out_dir / "config.json").write_text(json.dumps(cfg_payload, indent=2), encoding="utf-8")

    tok = Tokenizer.from_file(str(out_dir / "tokenizer.json"))
    tok.enable_truncation(max_length=ACTION_SEQ_LEN)
    tok.enable_padding(length=ACTION_SEQ_LEN, pad_id=1, pad_token="<pad>")

    train_path = (
        REPO_ROOT / "data" / "benchmarks" / "supervision_heldout" / "wo42_clause_speech_act_train.jsonl"
    )
    all_rows = [json.loads(l) for l in train_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    rng = random.Random(20261113)
    rng.shuffle(all_rows)
    calib_rows = all_rows[:256]
    eval_rows = all_rows[256:556]

    def _transform(row: dict[str, Any]) -> dict[str, np.ndarray]:
        text_a = f"User request: {str(row.get('prompt', '')).strip()}"
        text_b = f"Assistant reply: {str(row.get('completion', '')).strip()}"
        enc = tok.encode(text_a, text_b)
        return {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }

    core = ov.Core()
    ov_fp = core.read_model(str(src_dir / "openvino_model.xml"))
    ov_int8 = nncf.quantize(
        ov_fp,
        nncf.Dataset(calib_rows, _transform),
        model_type=nncf.ModelType.TRANSFORMER,
        subset_size=len(calib_rows),
    )
    ov.save_model(ov_int8, str(out_dir / "openvino_model.xml"))

    fp_req = core.compile_model(str(src_dir / "openvino_model.xml"), "CPU").create_infer_request()
    int8_req = core.compile_model(str(out_dir / "openvino_model.xml"), "CPU").create_infer_request()

    fp_acc = 0
    i8_acc = 0
    agree_10class = 0
    for r in eval_rows:
        inp = _transform(r)
        gold = int(r["speech_act_id"])
        p_fp = int(np.argmax(list(fp_req.infer(inp).values())[0][0]))
        p_i8 = int(np.argmax(list(int8_req.infer(inp).values())[0][0]))
        fp_acc += int(p_fp == gold)
        i8_acc += int(p_i8 == gold)
        agree_10class += int(p_fp == p_i8)

    # Also check locked WO42_150 LOCKED_COH (50 items) via NeuralActionClaimVerifier
    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))
    from lucca.sandbox.neural_claim_verifier import NeuralActionClaimVerifier  # noqa: E402

    nv_fp = NeuralActionClaimVerifier(model_dir=src_dir, preferred_devices=("CPU",))
    nv_i8 = NeuralActionClaimVerifier(model_dir=out_dir, preferred_devices=("CPU",))
    locked_150 = [
        json.loads(l)
        for l in (
            REPO_ROOT
            / "data"
            / "benchmarks"
            / "supervision_heldout"
            / "wo42_locked_holdout_150_worksheet.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
        if l.strip()
    ]
    coh_50 = [r for r in locked_150 if r.get("subsystem") == "coherence"]
    fp_coh = 0
    i8_coh = 0
    coh_agree = 0
    for r in coh_50:
        gold_blk = bool(r["gold_should_block"])
        v_fp = nv_fp.evaluate(
            completion=r["assistant_output"],
            user_context=r["prompt"],
            verified_tools=list(r.get("verified_tools") or []),
        )
        v_i8 = nv_i8.evaluate(
            completion=r["assistant_output"],
            user_context=r["prompt"],
            verified_tools=list(r.get("verified_tools") or []),
        )
        b_fp = bool(v_fp.is_ungrounded_claim or v_fp.is_unfulfilled_promise)
        b_i8 = bool(v_i8.is_ungrounded_claim or v_i8.is_unfulfilled_promise)
        fp_coh += int(b_fp == gold_blk)
        i8_coh += int(b_i8 == gold_blk)
        coh_agree += int(b_fp == b_i8)

    lat = benchmark_cpu_latency(int8_req, ACTION_SEQ_LEN)
    return {
        "speech_act_300_fp_acc_pct": round(fp_acc / len(eval_rows) * 100.0, 2),
        "speech_act_300_int8_acc_pct": round(i8_acc / len(eval_rows) * 100.0, 2),
        "speech_act_300_fp_vs_int8_agreement_pct": round(agree_10class / len(eval_rows) * 100.0, 2),
        "locked_coh_50_fp": f"{fp_coh}/{len(coh_50)}",
        "locked_coh_50_int8": f"{i8_coh}/{len(coh_50)}",
        "locked_coh_50_fp_vs_int8_agreement_pct": round(coh_agree / len(coh_50) * 100.0, 2),
        "cpu_latency": lat,
        "manifest": collect_dir_manifest(
            out_dir, "cross-encoder/nli-MiniLM2-L6-H768", "Apache-2.0"
        ),
    }


def quantize_and_eval_nli() -> dict[str, Any]:
    print("=== [4/4] INT8-quantizing & benchmarking nli_int8 ===")
    src_dir = REPO_ROOT / "models" / "verifier_deberta_v3_xsmall_ov"
    out_dir = PACK_ROOT / "nli_int8"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(src_dir / "config.json", out_dir / "config.json")
    shutil.copy2(src_dir / "tokenizer.json", out_dir / "tokenizer.json")

    tok = Tokenizer.from_file(str(out_dir / "tokenizer.json"))
    tok.enable_truncation(max_length=NLI_SEQ_LEN)
    tok.enable_padding(length=NLI_SEQ_LEN, pad_id=0, pad_token="[PAD]")

    train_rows, _val_rows, _stats = build_disjoint_web_evidence_splits(REPO_ROOT, seed=20261113)
    calib_pairs: list[tuple[str, str]] = [(r[1], r[0]) for r in train_rows[:192]] + [
        (train_rows[i][1], train_rows[(i + 1) % len(train_rows)][1]) for i in range(64)
    ]

    def _transform(pair: tuple[str, str]) -> dict[str, np.ndarray]:
        enc = tok.encode(pair[0], pair[1])
        return {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }

    core = ov.Core()
    ov_fp = core.read_model(str(src_dir / "openvino_model.xml"))
    ov_int8 = nncf.quantize(
        ov_fp,
        nncf.Dataset(calib_pairs, _transform),
        model_type=nncf.ModelType.TRANSFORMER,
        subset_size=min(256, len(calib_pairs)),
    )
    ov.save_model(ov_int8, str(out_dir / "openvino_model.xml"))

    fp_req = core.compile_model(str(src_dir / "openvino_model.xml"), "CPU").create_infer_request()
    int8_req = core.compile_model(str(out_dir / "openvino_model.xml"), "CPU").create_infer_request()

    holdout_path = REPO_ROOT / "data" / "benchmarks" / "nli_holdout_v2_120.jsonl"
    holdout_rows = [
        json.loads(line)
        for line in holdout_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lbl_map = {"CONTRADICTION": 0, "ENTAILMENT": 1, "NEUTRAL": 2}
    fp_ok = 0
    i8_ok = 0
    agree = 0
    for row in holdout_rows:
        inp = _transform((str(row["premise"]), str(row["hypothesis"])))
        gold = lbl_map[str(row["gold"]).upper()]
        p_fp = int(np.argmax(list(fp_req.infer(inp).values())[0][0]))
        p_i8 = int(np.argmax(list(int8_req.infer(inp).values())[0][0]))
        fp_ok += int(p_fp == gold)
        i8_ok += int(p_i8 == gold)
        agree += int(p_fp == p_i8)

    lat = benchmark_cpu_latency(int8_req, NLI_SEQ_LEN)
    n_h = len(holdout_rows)
    return {
        "nli_v2_120_fp": f"{fp_ok}/{n_h} ({fp_ok / n_h * 100:.2f}%)",
        "nli_v2_120_int8": f"{i8_ok}/{n_h} ({i8_ok / n_h * 100:.2f}%)",
        "nli_v2_120_fp_vs_int8_agreement_pct": round(agree / n_h * 100.0, 2),
        "cpu_latency": lat,
        "manifest": collect_dir_manifest(
            out_dir, "cross-encoder/nli-deberta-v3-xsmall", "Apache-2.0"
        ),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build epistemic-guard INT8 OpenVINO model pack.")
    parser.add_argument(
        "--only",
        choices=("web_evidence", "hazard", "action_claim", "nli"),
        default=None,
        help="Build/refresh a single model and merge into the pack report.",
    )
    args = parser.parse_args(argv)

    PACK_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)

    existing_models: dict[str, Any] = {}
    if REPORT_OUT.exists():
        existing_models = dict(
            json.loads(REPORT_OUT.read_text(encoding="utf-8")).get("models", {})
        )

    if args.only in (None, "web_evidence"):
        existing_models["web_evidence_int8"] = train_and_quantize_web_evidence()
    if args.only in (None, "hazard"):
        existing_models["hazard_int8"] = quantize_and_eval_hazard()
    if args.only in (None, "action_claim"):
        existing_models["action_claim_int8"] = quantize_and_eval_action_claim()
    if args.only in (None, "nli"):
        existing_models["nli_int8"] = quantize_and_eval_nli()

    total_pack_bytes = sum(
        r["manifest"]["total_size_bytes"] for r in existing_models.values()
    )
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "pack_root": "models/epistemic_guard_int8",
        "total_pack_size_mb": round(total_pack_bytes / (1024 * 1024), 2),
        "models": existing_models,
    }
    REPORT_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== INT8 MODEL PACK SUMMARY ===")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
