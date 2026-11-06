#!/usr/bin/env python3
"""
WO-42 Milestone 1.3: GPU Training & OpenVINO IR Export for the Multi-Sentence Neurosymbolic Router
(`models/router_intent_ov/openvino_model.xml`).

Strict Zero-Leakage Guarantee:
  - Excludes all 60 items of `RTR_01..RTR_60`, all 135 items of `tests/fixtures/router/router_fixtures.jsonl`
    (`T-RTR-01`), and all 30 items of `BLIND_RTR_01..BLIND_RTR_30` with hard assertion checks.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import sys
import time
from typing import Final

import numpy as np
import openvino as ov
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
RUNTIME_ROOT: Final[Path] = Path("C:/ProjectLucca")
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lucca.router.heuristic import HeuristicRouter  # noqa: E402
from lucca.router.neural_intent_classifier import (  # noqa: E402
    STATIC_SEQ_LEN,
    format_router_input,
    reset_neural_intent_classifier,
)
from train_wo41_phase4_router import (  # noqa: E402
    BASE_MODEL_ID,
    DOMAIN_FLAGS,
    DOMAIN2IDX,
    PRIMARY_CLASSES,
    TOTAL_OUTPUT_DIM,
    RouterDataset,
    build_heldout_60,
    build_training_corpus,
)

OUTPUT_PYTORCH_DIR: Final[Path] = ROOT / "models" / "router_intent_pt"
OUTPUT_OV_DIR: Final[Path] = ROOT / "models" / "router_intent_ov"
RUNTIME_OV_DIR: Final[Path] = RUNTIME_ROOT / "models" / "router_intent_ov"
BENCH_DIR: Final[Path] = ROOT / "data" / "benchmarks" / "supervision_heldout"
BLIND_90_PATH: Final[Path] = BENCH_DIR / "wo41_blind_adversarial_90_worksheet.jsonl"
WO42_TRAIN_JSONL: Final[Path] = BENCH_DIR / "wo42_router_train.jsonl"


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def build_wo42_router_corpus() -> tuple[list[dict[str, object]], list[dict[str, object]], set[str]]:
    heldout_60 = build_heldout_60()
    base_rows = build_training_corpus(heldout_60)

    forbidden_keys: set[str] = {
        norm_text(format_router_input(str(r["transcript"]), r.get("last_tool")))  # type: ignore[arg-type]
        for r in heldout_60
    }
    fixtures_path = ROOT / "tests" / "fixtures" / "router" / "router_fixtures.jsonl"
    if fixtures_path.exists():
        for raw_line in fixtures_path.read_text(encoding="utf-8").splitlines():
            if raw_line.strip():
                item = json.loads(raw_line)
                forbidden_keys.add(norm_text(format_router_input(str(item["transcript"]), None)))

    if BLIND_90_PATH.exists():
        for raw_line in BLIND_90_PATH.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            item = json.loads(raw_line)
            for k in ("transcript", "input", "text"):
                if k in item:
                    forbidden_keys.add(
                        norm_text(format_router_input(str(item[k]), item.get("last_tool")))
                    )

    rows: list[dict[str, object]] = [
        r for r in base_rows if norm_text(str(r["text"])) not in forbidden_keys
    ]

    def add(
        text: str,
        primary_class: str,
        domains: list[str] | None = None,
        last_tool: str | None = None,
        repeat: int = 4,
    ) -> None:
        formatted = format_router_input(text, last_tool)
        if norm_text(formatted) in forbidden_keys:
            return
        dom_list = domains or []
        for _ in range(repeat):
            rows.append(
                {
                    "text": formatted,
                    "primary_class": primary_class,
                    "domains": dom_list,
                }
            )

    # 1. Bracketed 2D Integer Grids & Multi-Sentence ARC-AGI Tasks -> spatial_grid (arc_primitives)
    spatial_grid_bracketed = [
        "Given the 2D input grid [[0, 1, 0], [1, 1, 1], [0, 1, 0]], recolor all cells of value 1 to 4 and crop to the bounding box.",
        "In this ARC puzzle, transform the 2D grid [[0, 0, 3], [0, 3, 0], [3, 0, 0]] by reflecting it across the vertical axis.",
        "Take the input pixel grid [[2, 2, 0], [2, 0, 0], [0, 0, 0]] and flood fill the background region of 0s with color 8.",
        "Find all 4-connected components in the grid [[0, 5, 5], [0, 5, 0], [0, 0, 0]] and shift the colored object one row down.",
        "Here is a 3x3 integer grid: [[1, 0, 1], [0, 1, 0], [1, 0, 1]]. Rotate the grid 90 degrees clockwise and invert colors 0 and 1.",
        "Given the demonstration grids [[0, 4, 0], [4, 0, 4]] and [[0, 7, 0], [7, 0, 7]], fill the hollow interior cell of the 2D shape.",
        "Consider the 2D array of colored tiles [[0, 0, 2, 0], [0, 2, 2, 2], [0, 0, 2, 0]]. Extract the bounding subgrid containing non-zero tiles.",
        "Apply gravity downward to the nonzero pixels in the 2D grid [[3, 0, 6], [0, 0, 0], [0, 5, 0]] so tiles rest on the bottom row.",
        "We have an ARC-AGI visual grid task with input [[8, 8, 0], [8, 0, 0], [0, 0, 0]]. Tile this 3x3 pattern into a 6x6 symmetric output grid.",
        "In the 2D grid [[0, 9, 0], [9, 9, 9], [0, 9, 0]], replace the center pixel of the plus shape with color 2.",
    ]
    for ex in spatial_grid_bracketed:
        add(ex, "spatial_grid", ["spatial_grid"], repeat=6)

    # 2. Multi-Sentence Combinatorial SMT & Constraint Satisfaction Puzzles -> logic_constraints (combinatorial_smt)
    multi_sentence_smt = [
        "Four nurses—Alice, Brenda, Clara, and Diana—must be assigned to four different hospital shifts: morning, afternoon, evening, and night. Alice cannot work the night shift, and Brenda must work earlier than Clara. Which nurse is assigned to each shift?",
        "Five speakers are scheduled to give talks in slots 1 through 5 at a conference. Dr. Evans must speak before Dr. Patel, and Dr. Kim cannot be in slot 1 or slot 5. Find a valid schedule that satisfies all constraints.",
        "Three boxes are labeled Red, Blue, and Green, and each contains a different gem: ruby, sapphire, or emerald. The ruby is not in the Red box, and the Green box does not hold the sapphire. Determine which gem is inside each box.",
        "On an island where knights always tell the truth and knaves always lie, you meet three inhabitants: P, Q, and R. P claims that Q and R are of the same type, while Q says that P is a knave. Determine who is a knight and who is a knave.",
        "Six quests must be assigned to six days of the week from Monday to Saturday with no two quests on the same day. Quest A must occur two days before Quest B, and Quest C must be on Wednesday or Friday. Find the exact day for each quest.",
        "Four houses in a row are painted red, yellow, blue, and white, and each homeowner drinks a different beverage. The tea drinker lives immediately to the left of the yellow house, and the coffee drinker lives in the middle. Solve this logic grid puzzle.",
    ]
    for ex in multi_sentence_smt:
        add(ex, "logic_constraints", ["combinatorial_smt"], repeat=6)

    # 3. Multi-Sentence Math Word Problems & Rate/Algebra/Calculus -> math_computation (mathematics)
    multi_sentence_math = [
        "Pump A can fill a storage tank in 6 hours by itself, while Pump B can fill the same tank in 4 hours. At 9:00 AM both pumps are turned on together, but an outlet valve is accidentally left open that drains 1/12 of the tank per hour. How many hours will it take to fill the tank completely?",
        "A train leaves Station X traveling east at 60 miles per hour. Two hours later, an express train leaves the same station on a parallel track at 90 miles per hour. After how many hours will the express train overtake the first train, and at what distance from Station X?",
        "Consider a continuous function f(x) = x^3 - 6x^2 + 9x + 2 defined on the closed interval [0, 5]. Find all critical points by setting the first derivative to zero and compute the global maximum and minimum values.",
        "A rectangular garden has a perimeter of 84 meters, and its length is 6 meters greater than twice its width. Set up a system of linear equations and solve for the exact length, width, and area of the garden.",
        "In a sequence of positive integers, the first term is 3 and each subsequent term is obtained by multiplying the previous term by 2 and subtracting 1. Find a closed-form expression and compute the sum of the first 12 terms.",
    ]
    for ex in multi_sentence_math:
        add(ex, "math_computation", ["mathematics"], repeat=6)

    # 4. Multi-Sentence Code Repair & Codebase Investigation -> code_repair (swe_bench)
    multi_sentence_code_repair = [
        "Investigate the issue in the codebase and reproduce the issue.",
        "Investigate the bug in the repository, reproduce the failure with pytest, and apply a fix.",
        "When we pass an empty dictionary to the configuration loader, it crashes with an unhandled KeyError. Please inspect the module, reproduce the failing test case, and write a patch.",
        "The async websocket client leaks file descriptors whenever the remote server drops the connection mid-handshake. Locate the bug in the connection pool, add a unit test that reproduces it, and fix the cleanup logic.",
        "Users report that pagination returns duplicate rows when sorting by non-unique timestamps. Diagnose the SQL query builder bug in the codebase and verify the patch with pytest.",
    ]
    for ex in multi_sentence_code_repair:
        add(ex, "code_repair", ["code_repair"], repeat=6)

    # 5. Multi-Sentence Soft Logic / Deductive Reading Comprehension -> soft_logic
    multi_sentence_soft_logic = [
        "Every security engineer who attended the Tuesday briefing signed the physical access log at the front desk. Marcus did not sign the physical access log on Tuesday, even though his badge was active. Based strictly on these premises, what can we logically conclude about Marcus?",
        "During the art gallery heist, the alarm was triggered at 11:15 PM. Suspect A was seen on a verified restaurant security camera 20 miles away at 11:12 PM, while Suspect B claims to have been alone in the gallery courtyard at 11:15 PM but heard no alarm. Which suspect's alibi is logically implausible?",
        "All certified aviation mechanics must complete 40 hours of recurrent hydraulics training every two years. No contractor in Sector 4 has completed recurrent hydraulics training in the past three years. Which deduction necessarily follows from the passage?",
    ]
    for ex in multi_sentence_soft_logic:
        add(ex, "soft_logic", ["soft_logic"], repeat=6)

    # 6. Multi-Sentence Spatial Relocation (ContainerWorld Theory-of-Mind) -> spatial_relocation
    multi_sentence_relocation = [
        "Hannah put the silver watch inside the velvet jewelry box on her dresser before leaving for work. While she was away, her brother Leo moved the silver watch from the jewelry box into the hallway coat pocket, and later moved it into the kitchen pantry. Where will Hannah look for the silver watch when she gets home, and where is it actually located?",
        "Oliver placed the encrypted USB drive in the top desk drawer. Later that afternoon, Maya took the USB drive out of the top desk drawer and placed it inside the blue backpack. Where does Oliver believe the USB drive is?",
    ]
    for ex in multi_sentence_relocation:
        add(ex, "spatial_relocation", ["spatial_relocation"], repeat=6)

    # 7. Unlisted / Creative Apps -> unknown (NOT dangerous, NOT launch_app)
    unlisted_apps_unknown = [
        "Open Blender and render the default 3D scene",
        "Open Adobe Photoshop and resize the banner image",
        "Launch Unreal Engine and load the level editor",
        "Open Audacity and record a voiceover track",
        "Start OBS Studio and check the scene layout",
        "Open Figma and export the vector icons",
    ]
    for ex in unlisted_apps_unknown:
        add(ex, "unknown", [], repeat=5)

    rng = random.Random(42)
    rng.shuffle(rows)

    for r in rows:
        assert norm_text(str(r["text"])) not in forbidden_keys, f"LEAKAGE DETECTED: {r['text']}"

    return rows, heldout_60, forbidden_keys


def main() -> int:
    torch.manual_seed(42)
    np.random.seed(42)
    random.seed(42)

    train_rows, heldout_60, forbidden_keys = build_wo42_router_corpus()
    WO42_TRAIN_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with WO42_TRAIN_JSONL.open("w", encoding="utf-8") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(
        f"[WO-42 M1.3] Built Router Corpus: N={len(train_rows)} "
        f"(0% overlap with {len(forbidden_keys)} held-out items)"
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, local_files_only=True)
    config = AutoConfig.from_pretrained(
        BASE_MODEL_ID,
        num_labels=TOTAL_OUTPUT_DIM,
        local_files_only=True,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL_ID,
        config=config,
        ignore_mismatched_sizes=True,
        local_files_only=True,
    ).to(device)

    for param in model.parameters():
        param.requires_grad = True

    dataset = RouterDataset(train_rows, tokenizer)
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
    ce_loss_fn = nn.CrossEntropyLoss()
    pos_weight = torch.full((len(DOMAIN_FLAGS),), 8.0, dtype=torch.float32, device=device)
    bce_loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    epochs = 10
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=epochs * len(loader)
    )
    num_primary = len(PRIMARY_CLASSES)

    model.train()
    for epoch in range(1, epochs + 1):
        t0 = time.perf_counter()
        ep_loss = 0.0
        cls_correct = 0
        total = 0
        for batch in loader:
            optimizer.zero_grad()
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            cls_lbl = batch["class_label"].to(device)
            domain_lbl = batch["domain_labels"].to(device)

            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
            cls_logits = logits[:, :num_primary]
            domain_logits = logits[:, num_primary:]

            loss = ce_loss_fn(cls_logits, cls_lbl) + bce_loss_fn(domain_logits, domain_lbl)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            ep_loss += float(loss.item()) * cls_lbl.size(0)
            cls_correct += int((cls_logits.argmax(dim=-1) == cls_lbl).sum().item())
            total += int(cls_lbl.size(0))

        print(
            f"  Epoch {epoch:2d}/{epochs} ({time.perf_counter()-t0:.2f}s) | "
            f"Loss={ep_loss/total:.4f} | Primary Acc={cls_correct}/{total} ({100.0*cls_correct/total:.2f}%)",
            flush=True,
        )

    OUTPUT_PYTORCH_DIR.mkdir(parents=True, exist_ok=True)
    model.eval()
    model.cpu()
    model.save_pretrained(str(OUTPUT_PYTORCH_DIR))
    tokenizer.save_pretrained(str(OUTPUT_PYTORCH_DIR))

    class TraceableRobertaRouter(nn.Module):
        def __init__(self, m: nn.Module) -> None:
            super().__init__()
            self.embeddings = m.roberta.embeddings  # type: ignore[attr-defined]
            self.layers = m.roberta.encoder.layer  # type: ignore[attr-defined]
            self.classifier = m.classifier  # type: ignore[attr-defined]

        def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
            ext_mask = (1.0 - attention_mask[:, None, None, :].to(torch.float32)) * -10000.0
            h = self.embeddings(input_ids=input_ids)
            for layer in self.layers:
                out = layer(h, ext_mask)
                h = out[0] if isinstance(out, tuple) else out
            return self.classifier(h)

    traceable = TraceableRobertaRouter(model).eval()
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
    OUTPUT_OV_DIR.mkdir(parents=True, exist_ok=True)
    ov.save_model(ov_model, str(OUTPUT_OV_DIR / "openvino_model.xml"), compress_to_fp16=True)
    tokenizer.save_pretrained(str(OUTPUT_OV_DIR))
    config.save_pretrained(str(OUTPUT_OV_DIR))

    if RUNTIME_ROOT.exists():
        RUNTIME_OV_DIR.mkdir(parents=True, exist_ok=True)
        for item in OUTPUT_OV_DIR.iterdir():
            if item.is_file():
                shutil.copy2(item, RUNTIME_OV_DIR / item.name)

    xml_b = (OUTPUT_OV_DIR / "openvino_model.xml").read_bytes()
    bin_b = (OUTPUT_OV_DIR / "openvino_model.bin").read_bytes()
    sha256_hex = hashlib.sha256(xml_b + bin_b).hexdigest()
    print(f"[WO-42 M1.3] Exported OpenVINO IR SHA-256: {sha256_hex}")

    reset_neural_intent_classifier()
    router = HeuristicRouter()
    correct_60 = 0
    for item in heldout_60:
        text = str(item["transcript"])
        last_tool = item.get("last_tool")  # type: ignore[assignment]
        gold_intent = str(item["gold_intent"])
        gold_domain = item.get("gold_domain")
        gold_libs = sorted(list(item.get("gold_libs", [])))  # type: ignore[arg-type]

        pred_intent, _, _ = router.classify_intent(text, last_tool=last_tool)  # type: ignore[arg-type]
        dec = router.route(text, last_tool=last_tool)  # type: ignore[arg-type]
        pred_dom = "emergency_reflex" if dec.tier.value == "REFLEX" else dec.reasoning_domain
        pred_libs = sorted(list(dec.exposed_libraries))

        if (pred_intent == gold_intent) and (pred_dom == gold_domain) and (pred_libs == gold_libs):
            correct_60 += 1
        else:
            print(f"  MISS {item['id']}: pred=({pred_intent}, {pred_dom}, {pred_libs}) vs gold=({gold_intent}, {gold_domain}, {gold_libs})")

    print(f"[WO-42 M1.3] Held-out RTR_60 Accuracy: {correct_60}/60 ({100.0*correct_60/60:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
