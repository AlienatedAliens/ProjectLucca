"""WO-45 RM-7 (R-42): Hard-negative retraining & OpenVINO FP16 export for Proof-Policy Hazard v2.

Implements `REVIEW_G4.md:88-93`:
  - Retrains `cross-encoder/nli-MiniLM2-L6-H768` on `wo42_hazard_train.jsonl` augmented with the
    49 non-v3 hard negatives from `r40v2_upward_escalations_audit.json`.
  - Holds out all 24 v3 items from the 73 R-40v2 over-escalations (24/73 = 32.88% >= 20.0%) and
    enforces hard assertions that ZERO `v3` `probe_id`s or query texts (and ZERO `WO42_LOCKED_HOLDOUT_150`,
    `Blind-390`, or `HZD_50` texts) appear in training.
  - Exports static-shape `[1, 64]` FP16 OpenVINO IR to `models/proof_policy_hazard_v2_ov/` so
    frozen v1 (`models/proof_policy_hazard_ov/`) hashes in `live_v2_prereg_lock.json` and
    `WO42_LOCKED_HOLDOUT_150` remain 100% intact and side-by-side v1 vs v2 evaluation can run.
  - Computes 10-bin Expected Calibration Error (ECE) alongside accuracy and over-escalation rates.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import openvino as ov
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RUNTIME_ROOT: Final[Path] = Path(r"C:\ProjectLucca")
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.core.neural_hazard_classifier import (  # noqa: E402
    _SINGLETON_HOLDER,
    CLASS_NAMES,
    HAZARD_RANK,
    STATIC_SEQ_LEN,
    NeuralHazardClassifier,
    reset_neural_hazard_classifier,
)
from lucca.core.proof_policy import classify_hazard, is_cross_reference_command  # noqa: E402

LABELS: Final[tuple[str, ...]] = CLASS_NAMES
LABEL2ID: Final[dict[str, int]] = {lbl: idx for idx, lbl in enumerate(LABELS)}
ID2LABEL: Final[dict[int, str]] = {idx: lbl for idx, lbl in enumerate(LABELS)}

BASE_MODEL_ID: Final[str] = "cross-encoder/nli-MiniLM2-L6-H768"
V1_OV_DIR: Final[Path] = REPO_ROOT / "models" / "proof_policy_hazard_ov"
V2_OV_DIR: Final[Path] = REPO_ROOT / "models" / "proof_policy_hazard_v2_ov"
RUNTIME_V2_OV_DIR: Final[Path] = RUNTIME_ROOT / "models" / "proof_policy_hazard_v2_ov"

BENCH_DIR: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "supervision_heldout"
WO42_TRAIN_JSONL: Final[Path] = BENCH_DIR / "wo42_hazard_train.jsonl"
HZD_50_PATH: Final[Path] = BENCH_DIR / "wo41_phase4_hazard_test_50.jsonl"
LOCKED_150_PATH: Final[Path] = BENCH_DIR / "wo42_locked_holdout_150_raw_items.jsonl"
BLIND_300_PATH: Final[Path] = BENCH_DIR / "wo42_blind_300_raw_items.jsonl"
BLIND_90_RAW_PATH: Final[Path] = BENCH_DIR / "wo41_blind_adversarial_90_raw.jsonl"
WEB360_PATH: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "web_evidentiary_burden_360.jsonl"

WO45_DIR: Final[Path] = REPO_ROOT / "logs" / "test_reports" / "wo45"
R40V2_AUDIT_PATH: Final[Path] = WO45_DIR / "r40v2_upward_escalations_audit.json"
V3_SELECTED_PATH: Final[Path] = WO45_DIR / "live_v3_selected_items.json"
REPORT_OUT: Final[Path] = WO45_DIR / "r42_hazard_retrain_report.json"


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ov_pair_sha256(ov_dir: Path) -> str:
    xml_b = (ov_dir / "openvino_model.xml").read_bytes()
    bin_b = (ov_dir / "openvino_model.bin").read_bytes()
    return hashlib.sha256(xml_b + bin_b).hexdigest()


def compute_ece_10bin(confidences: list[float], correctness: list[bool]) -> float:
    if not confidences:
        return 0.0
    n = len(confidences)
    ece = 0.0
    for b in range(10):
        lo = b / 10.0
        hi = (b + 1) / 10.0
        idxs = [
            i
            for i, c in enumerate(confidences)
            if (lo <= c <= hi if b == 9 else lo <= c < hi)
        ]
        if not idxs:
            continue
        avg_conf = sum(confidences[i] for i in idxs) / len(idxs)
        avg_acc = sum(1.0 if correctness[i] else 0.0 for i in idxs) / len(idxs)
        ece += (len(idxs) / n) * abs(avg_acc - avg_conf)
    return round(ece, 4)


class HazardDataset(Dataset[dict[str, torch.Tensor]]):
    def __init__(self, rows: list[dict[str, str]], tokenizer: Any) -> None:
        self.rows = rows
        self.tokenizer = tokenizer

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        row = self.rows[idx]
        enc = self.tokenizer(
            row["text"],
            max_length=STATIC_SEQ_LEN,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        item = {k: v.squeeze(0) for k, v in enc.items()}
        item["labels"] = torch.tensor(LABEL2ID[row["label"]], dtype=torch.long)
        return item


def evaluate_all_suites(ov_dir: Path) -> dict[str, Any]:
    reset_neural_hazard_classifier()
    clf = NeuralHazardClassifier(model_dir=ov_dir)
    _SINGLETON_HOLDER["instance"] = clf

    # 1. HZD_50
    hzd_50 = [json.loads(ln) for ln in HZD_50_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    hzd50_ok = 0
    for it in hzd_50:
        if it["task"] == "is_cross_reference_command":
            ok = is_cross_reference_command(it["text"]) == (it["gold_label"] == "CROSS_REFERENCE_CMD")
        else:
            ok = classify_hazard(it["text"]).value.upper() == str(it["gold_label"]).upper()
        if ok:
            hzd50_ok += 1

    # 2. WO42_LOCKED_HOLDOUT_150 (proof_policy subset, N=50)
    locked_hzd = [
        json.loads(ln)
        for ln in LOCKED_150_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip() and str(json.loads(ln)["id"]).startswith("LOCKED_HZD_")
    ]
    locked_ok = 0
    locked_confs: list[float] = []
    locked_corr: list[bool] = []
    locked_missed: list[str] = []
    for it in locked_hzd:
        txt = str(it["text"])
        v = clf.evaluate(txt)
        pred_cr = is_cross_reference_command(txt)
        pred_h = classify_hazard(txt).value.upper()
        gold_cr = bool(it["gold_cross_ref"])
        if gold_cr:
            ok = pred_cr is True
        else:
            ok = (pred_cr is False) and (pred_h == str(it["gold_hazard"]).upper())
        if ok:
            locked_ok += 1
        else:
            locked_missed.append(str(it["id"]))
        locked_confs.append(float(v.confidence))
        locked_corr.append(ok)

    # 3. Blind-390 proof_policy (BLIND42_HZD_001..100 + BLIND_HZD_01..30, N=130)
    blind_100 = [
        json.loads(ln)
        for ln in BLIND_300_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip() and json.loads(ln).get("subsystem") == "proof_policy"
    ]
    blind_30 = [
        json.loads(ln)
        for ln in BLIND_90_RAW_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip() and json.loads(ln).get("subsystem") == "proof_policy"
    ]
    b100_ok = 0
    b30_ok = 0
    b130_confs: list[float] = []
    b130_corr: list[bool] = []
    b130_missed: list[str] = []

    for it in blind_100:
        txt = str(it["text"])
        v = clf.evaluate(txt)
        pred_cr = is_cross_reference_command(txt)
        pred_h = classify_hazard(txt).value.upper()
        gold_cr = bool(it["gold_cross_ref"])
        ok = (pred_cr is True) if gold_cr else ((pred_cr is False) and (pred_h == str(it["gold_hazard"]).upper()))
        if ok:
            b100_ok += 1
        else:
            b130_missed.append(str(it["id"]))
        b130_confs.append(float(v.confidence))
        b130_corr.append(ok)

    for it in blind_30:
        txt = str(it["text"])
        v = clf.evaluate(txt)
        g_lbl = str(it["gold_label"]).upper()
        if str(it["task"]) == "classify_hazard":
            ok = classify_hazard(txt).value.upper() == g_lbl
        else:
            ok = ("TRUE" if is_cross_reference_command(txt) else "FALSE") == g_lbl
        if ok:
            b30_ok += 1
        else:
            b130_missed.append(str(it["id"]))
        b130_confs.append(float(v.confidence))
        b130_corr.append(ok)

    # 4. Held-out 24 R-40v2 over-escalations & Full 132 v3 items
    v3_ids = set(json.loads(V3_SELECTED_PATH.read_text(encoding="utf-8"))["selected_probe_ids"])
    r40 = json.loads(R40V2_AUDIT_PATH.read_text(encoding="utf-8"))
    heldout_24 = [
        it
        for it in r40["evaluated_items_163"]
        if it["cohort"] == "escalated_73" and it["probe_id"] in v3_ids
    ]
    ho24_still_escalated = 0
    ho24_under_escalated = 0
    for it in heldout_24:
        pred_h = classify_hazard(str(it["query"])).value.lower()
        nom_h = str(it["nominal_hazard"]).lower()
        if HAZARD_RANK[pred_h] > HAZARD_RANK[nom_h]:
            ho24_still_escalated += 1
        elif HAZARD_RANK[pred_h] < HAZARD_RANK[nom_h]:
            ho24_under_escalated += 1

    web360_map = {
        str(r["probe_id"]): r
        for r in (json.loads(ln) for ln in WEB360_PATH.read_text(encoding="utf-8").splitlines() if ln.strip())
    }
    v3_exact = 0
    v3_over = 0
    v3_under = 0
    v3_confs: list[float] = []
    v3_corr: list[bool] = []
    v3_escalated_ids: list[str] = []
    for pid in sorted(v3_ids):
        row = web360_map[pid]
        q = str(row["query"])
        nom = str(row["stratum"]).lower()
        v = clf.evaluate(q)
        pred = classify_hazard(q).value.lower()
        ok = pred == nom
        if ok:
            v3_exact += 1
        elif HAZARD_RANK[pred] > HAZARD_RANK[nom]:
            v3_over += 1
            v3_escalated_ids.append(pid)
        else:
            v3_under += 1
        v3_confs.append(float(v.confidence))
        v3_corr.append(ok)

    reset_neural_hazard_classifier()
    return {
        "device": clf.active_device,
        "ov_pair_sha256": ov_pair_sha256(ov_dir),
        "openvino_xml_sha256": sha256_file(ov_dir / "openvino_model.xml"),
        "openvino_bin_sha256": sha256_file(ov_dir / "openvino_model.bin"),
        "hzd_50": {
            "correct": hzd50_ok,
            "total": len(hzd_50),
            "accuracy_pct": round(100.0 * hzd50_ok / len(hzd_50), 2),
        },
        "wo42_locked_holdout_50": {
            "correct": locked_ok,
            "total": len(locked_hzd),
            "accuracy_pct": round(100.0 * locked_ok / len(locked_hzd), 2),
            "ece_10bin": compute_ece_10bin(locked_confs, locked_corr),
            "missed_ids": locked_missed,
        },
        "blind_390_proof_policy_130": {
            "blind_300_correct": b100_ok,
            "blind_90_correct": b30_ok,
            "combined_correct": b100_ok + b30_ok,
            "total": 130,
            "accuracy_pct": round(100.0 * (b100_ok + b30_ok) / 130.0, 2),
            "ece_10bin": compute_ece_10bin(b130_confs, b130_corr),
            "missed_ids": b130_missed,
        },
        "heldout_r40v2_escalations_24": {
            "n": len(heldout_24),
            "over_escalated_count": ho24_still_escalated,
            "over_escalation_rate_pct": round(100.0 * ho24_still_escalated / len(heldout_24), 2),
            "under_escalated_count": ho24_under_escalated,
        },
        "v3_selected_132": {
            "n": len(v3_ids),
            "exact_match_count": v3_exact,
            "exact_match_pct": round(100.0 * v3_exact / len(v3_ids), 2),
            "over_escalated_count": v3_over,
            "over_escalation_rate_pct": round(100.0 * v3_over / len(v3_ids), 2),
            "under_escalated_count": v3_under,
            "ece_10bin": compute_ece_10bin(v3_confs, v3_corr),
            "over_escalated_probe_ids": v3_escalated_ids,
        },
    }


def main() -> int:
    torch.manual_seed(42)
    np.random.seed(42)
    random.seed(42)

    v3_sel = json.loads(V3_SELECTED_PATH.read_text(encoding="utf-8"))
    v3_probe_ids = set(v3_sel["selected_probe_ids"])
    assert len(v3_probe_ids) == 132

    web360_rows = [
        json.loads(ln) for ln in WEB360_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    v3_query_norms = {
        norm_text(r["query"]) for r in web360_rows if str(r["probe_id"]) in v3_probe_ids
    }

    # Build complete forbidden holdout text set (HZD_50 + Locked_150 + Blind_300 + Blind_90 + ALL 132 v3 items)
    forbidden_norms: set[str] = set(v3_query_norms)
    for p in (HZD_50_PATH, LOCKED_150_PATH, BLIND_300_PATH, BLIND_90_RAW_PATH):
        for ln in p.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            obj = json.loads(ln)
            for k in ("text", "claim_or_text", "query"):
                if k in obj and obj[k]:
                    forbidden_norms.add(norm_text(str(obj[k])))

    # Load base WO-42 training rows (excluding any collision with forbidden_norms)
    base_rows = [
        json.loads(ln)
        for ln in WO42_TRAIN_JSONL.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    train_rows: list[dict[str, str]] = [
        {"text": str(r["text"]), "label": str(r["label"])}
        for r in base_rows
        if norm_text(str(r["text"])) not in forbidden_norms
    ]

    # Load 73 R-40v2 over-escalations: keep ONLY non-v3 items (49/73 = 67.1%) for training,
    # holding out all 24 v3 items (24/73 = 32.9% >= 20.0%)!
    r40 = json.loads(R40V2_AUDIT_PATH.read_text(encoding="utf-8"))
    esc_73 = [it for it in r40["evaluated_items_163"] if it["cohort"] == "escalated_73"]
    assert len(esc_73) == 73

    hard_neg_train = [it for it in esc_73 if str(it["probe_id"]) not in v3_probe_ids]
    hard_neg_holdout = [it for it in esc_73 if str(it["probe_id"]) in v3_probe_ids]
    holdout_fraction = len(hard_neg_holdout) / len(esc_73)
    assert holdout_fraction >= 0.20, f"Holdout fraction {holdout_fraction:.3f} < 0.20"

    for hn in hard_neg_train:
        pid = str(hn["probe_id"])
        # RM-7 mandatory assertion: fail immediately if any v3 probe_id enters training!
        assert pid not in v3_probe_ids, f"FATAL LEAKAGE: v3 probe_id {pid} in training!"
        q_txt = str(hn["query"])
        assert norm_text(q_txt) not in v3_query_norms, f"FATAL LEAKAGE: v3 query text in {pid}!"
        gold_lbl = str(hn["adjudicated_label"]).upper()
        assert gold_lbl in ("LOW", "MEDIUM")
        train_rows.append({"text": q_txt, "label": gold_lbl})

    # Include non-v3 control_90 items from R-40v2 audit (1x) to preserve HIGH/MEDIUM/LOW balance
    ctrl_90_train = [
        it
        for it in r40["evaluated_items_163"]
        if it["cohort"] == "control_90" and str(it["probe_id"]) not in v3_probe_ids
    ]
    for ct in ctrl_90_train:
        pid = str(ct["probe_id"])
        assert pid not in v3_probe_ids, f"FATAL LEAKAGE: v3 probe_id {pid} in training!"
        q_txt = str(ct["query"])
        assert norm_text(q_txt) not in v3_query_norms, f"FATAL LEAKAGE: v3 query text in {pid}!"
        adj_lbl = str(ct["adjudicated_label"]).upper()
        gold_lbl = adj_lbl if adj_lbl in ("LOW", "MEDIUM", "HIGH") else str(ct["nominal_hazard"]).upper()
        if gold_lbl in ("LOW", "MEDIUM", "HIGH") and norm_text(q_txt) not in forbidden_norms:
            train_rows.append({"text": q_txt, "label": gold_lbl})

    # Final global assertion across every training example
    for r in train_rows:
        assert norm_text(r["text"]) not in forbidden_norms, f"Holdout/v3 leakage: {r['text']}"

    rng = random.Random(42)
    rng.shuffle(train_rows)
    print(
        f"[RM-7 / R-42] Training corpus N={len(train_rows)} | R-40v2 hard_neg_train={len(hard_neg_train)} "
        f"| R-40v2 ctrl_train={len(ctrl_90_train)} "
        f"| R-40v2 held-out={len(hard_neg_holdout)} ({100.0 * holdout_fraction:.1f}% >= 20%)",
        flush=True,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, local_files_only=True)
    config = AutoConfig.from_pretrained(
        BASE_MODEL_ID,
        num_labels=len(LABELS),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        local_files_only=True,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL_ID,
        config=config,
        ignore_mismatched_sizes=True,
        local_files_only=True,
    ).to(device)

    for p in model.parameters():
        p.requires_grad = True

    dataset = HazardDataset(train_rows, tokenizer)
    loader = DataLoader(dataset, batch_size=32, shuffle=True)

    backbone_params = [p for n, p in model.named_parameters() if not n.startswith("classifier.")]
    head_params = [p for n, p in model.named_parameters() if n.startswith("classifier.")]
    optimizer = torch.optim.AdamW(
        [
            {"params": backbone_params, "lr": 3.5e-5},
            {"params": head_params, "lr": 1.8e-4},
        ],
        weight_decay=0.01,
    )
    criterion = nn.CrossEntropyLoss(label_smoothing=0.02)
    epochs = 9
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=epochs * len(loader)
    )

    model.train()
    for epoch in range(1, epochs + 1):
        t0 = time.perf_counter()
        ep_loss = 0.0
        correct = 0
        total = 0
        for batch in loader:
            optimizer.zero_grad()
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            loss = criterion(logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            ep_loss += float(loss.item()) * labels.size(0)
            correct += int((logits.argmax(dim=-1) == labels).sum().item())
            total += int(labels.size(0))
        print(
            f"  Epoch {epoch}/{epochs} ({time.perf_counter() - t0:.2f}s) | "
            f"Loss={ep_loss / total:.4f} | Train Acc={correct}/{total} ({100.0 * correct / total:.2f}%)",
            flush=True,
        )

    model.eval()
    model.cpu()

    class TraceableRobertaClassifier(nn.Module):
        def __init__(self, m: Any) -> None:
            super().__init__()
            self.embeddings: Any = m.roberta.embeddings
            self.layers: Any = m.roberta.encoder.layer
            self.classifier: Any = m.classifier

        def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
            ext_mask = (1.0 - attention_mask[:, None, None, :].to(torch.float32)) * -10000.0
            h = self.embeddings(input_ids=input_ids)
            for layer in self.layers:
                out = layer(h, ext_mask)
                h = out[0] if isinstance(out, tuple) else out
            res: torch.Tensor = self.classifier(h)
            return res

    traceable = TraceableRobertaClassifier(model).eval()
    d_ids = torch.ones((1, STATIC_SEQ_LEN), dtype=torch.long)
    d_mask = torch.ones((1, STATIC_SEQ_LEN), dtype=torch.long)
    ov_model = ov.convert_model(
        traceable,
        example_input={"input_ids": d_ids, "attention_mask": d_mask},
        input=[
            ("input_ids", [1, STATIC_SEQ_LEN], ov.Type.i64),
            ("attention_mask", [1, STATIC_SEQ_LEN], ov.Type.i64),
        ],
    )
    ov_model.reshape({"input_ids": [1, STATIC_SEQ_LEN], "attention_mask": [1, STATIC_SEQ_LEN]})
    V2_OV_DIR.mkdir(parents=True, exist_ok=True)
    ov.save_model(ov_model, str(V2_OV_DIR / "openvino_model.xml"), compress_to_fp16=True)
    tokenizer.save_pretrained(str(V2_OV_DIR))
    config.save_pretrained(str(V2_OV_DIR))

    if RUNTIME_ROOT.exists():
        RUNTIME_V2_OV_DIR.mkdir(parents=True, exist_ok=True)
        for item in V2_OV_DIR.iterdir():
            if item.is_file():
                shutil.copy2(item, RUNTIME_V2_OV_DIR / item.name)

    print("[RM-7 / R-42] Evaluating v1 (old) vs v2 (retrained) side-by-side...", flush=True)
    v1_eval = evaluate_all_suites(V1_OV_DIR)
    v2_eval = evaluate_all_suites(V2_OV_DIR)

    locked_reg_pp = round(
        float(v1_eval["wo42_locked_holdout_50"]["accuracy_pct"])
        - float(v2_eval["wo42_locked_holdout_50"]["accuracy_pct"]),
        2,
    )
    blind_reg_pp = round(
        float(v1_eval["blind_390_proof_policy_130"]["accuracy_pct"])
        - float(v2_eval["blind_390_proof_policy_130"]["accuracy_pct"]),
        2,
    )
    over_esc_dropped = (
        int(v2_eval["heldout_r40v2_escalations_24"]["over_escalated_count"])
        < int(v1_eval["heldout_r40v2_escalations_24"]["over_escalated_count"])
    )
    accepted = over_esc_dropped and locked_reg_pp <= 1.0 and blind_reg_pp <= 1.0

    report = {
        "task_id": "RM-7_R-42",
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "base_model": BASE_MODEL_ID,
        "seed": 42,
        "epochs": epochs,
        "n_train_rows": len(train_rows),
        "r40v2_hard_negatives_train_count": len(hard_neg_train),
        "r40v2_hard_negatives_heldout_count": len(hard_neg_holdout),
        "r40v2_heldout_fraction_pct": round(100.0 * holdout_fraction, 2),
        "zero_v3_probe_id_leakage_verified": True,
        "zero_holdout_text_leakage_verified": True,
        "v1_old_classifier": v1_eval,
        "v2_retrained_classifier": v2_eval,
        "acceptance_checks": {
            "heldout_24_over_escalation_dropped": over_esc_dropped,
            "wo42_locked_holdout_150_regression_pp": locked_reg_pp,
            "wo42_locked_holdout_150_le_1pp": locked_reg_pp <= 1.0,
            "blind_390_regression_pp": blind_reg_pp,
            "blind_390_le_1pp": blind_reg_pp <= 1.0,
            "accepted_for_g4_v3": accepted,
        },
    }
    REPORT_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
