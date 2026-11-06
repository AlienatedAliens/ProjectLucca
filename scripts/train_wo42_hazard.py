#!/usr/bin/env python3
"""
WO-42 Milestone 1.2: GPU Training & OpenVINO IR Export for the 5-Class Sentence-Pooling
Proof-Policy Hazard & Cross-Reference Classifier (`models/proof_policy_hazard_ov/openvino_model.xml`).

Strict Zero-Leakage Guarantee:
  - Excludes all 50 items of `HZD_01..HZD_50` AND all 30 items of `BLIND_HZD_01..BLIND_HZD_30`
    with hard assertion checks.
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
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
RUNTIME_ROOT: Final[Path] = Path("C:/ProjectLucca")
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lucca.core.neural_hazard_classifier import (  # noqa: E402
    STATIC_SEQ_LEN,
    NeuralHazardClassifier,
    reset_neural_hazard_classifier,
)
from train_wo41_phase4_proof_policy import (  # noqa: E402
    ID2LABEL,
    LABEL2ID,
    LABELS,
    build_training_and_heldout_sets,
)

BASE_MODEL_ID: Final[str] = "cross-encoder/nli-MiniLM2-L6-H768"
OUTPUT_PYTORCH_DIR: Final[Path] = ROOT / "models" / "proof_policy_hazard_pt"
OUTPUT_OV_DIR: Final[Path] = ROOT / "models" / "proof_policy_hazard_ov"
RUNTIME_OV_DIR: Final[Path] = RUNTIME_ROOT / "models" / "proof_policy_hazard_ov"
BENCH_DIR: Final[Path] = ROOT / "data" / "benchmarks" / "supervision_heldout"
BLIND_90_PATH: Final[Path] = BENCH_DIR / "wo41_blind_adversarial_90_worksheet.jsonl"
WO42_TRAIN_JSONL: Final[Path] = BENCH_DIR / "wo42_hazard_train.jsonl"


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def build_wo42_hazard_corpus() -> tuple[list[dict[str, str]], list[dict[str, str]], set[str]]:
    base_train, heldout_50 = build_training_and_heldout_sets()

    forbidden_texts: set[str] = {norm_text(it["text"]) for it in heldout_50}
    if BLIND_90_PATH.exists():
        for line in BLIND_90_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if "claim_or_text" in row:
                forbidden_texts.add(norm_text(row["claim_or_text"]))

    rows: list[dict[str, str]] = [
        r for r in base_train if norm_text(r["text"]) not in forbidden_texts
    ]

    def add_examples(items: list[str], label: str, repeat: int = 3) -> None:
        for t in items:
            if norm_text(t) in forbidden_texts:
                continue
            for _ in range(repeat):
                rows.append({"text": t, "label": label})

    # 1. Expanded OS, Firmware, Hardware, and L2/L3 Networking Technical Specifications (MEDIUM)
    extra_medium_specs = [
        "UEFI firmware initializes hardware devices before handing control to the OS bootloader",
        "Enabling XMP or EXPO in the motherboard BIOS configures DDR5 memory timings and frequency",
        "PCIe 5.0 doubles the per-lane bandwidth of PCIe 4.0 to 32 GT/s",
        "Modern x86_64 processors include L1, L2, and shared L3 SRAM cache hierarchies",
        "The Linux kernel sysctl vm.swappiness parameter controls how aggressively memory pages are swapped",
        "Windows BitLocker can use a hardware security module to seal boot integrity measurements",
        "Modern operating systems require hardware virtualization extensions like Intel VT-x or AMD-V for hypervisors",
        "Motherboard firmware supports cryptographic boot signature verification for kernel images",
        "An Ethernet jumbo frame supports a payload up to 9000 bytes on compatible gigabit switches",
        "Standard IPv4 packet headers are 20 bytes long when no optional header fields are present",
        "IEEE 802.1Q VLAN tagging inserts a 4-byte header into the Layer 2 Ethernet frame",
        "TCP Path Discovery uses the Don't Fragment bit to determine the maximum packet size on a route",
        "The Address Resolution Protocol maps an IPv4 network address to a physical MAC address",
        "BGP routers exchange network reachability prefixes across autonomous systems over TCP port 179",
        "A /24 IPv4 CIDR subnet mask provides 254 usable host addresses",
        "NVMe solid-state drives support up to 64,000 I/O submission and completion queues",
        "The ext4 journaling filesystem supports volumes up to 1 exbibyte in size",
        "ZFS combines a volume manager and copy-on-write filesystem with end-to-end checksums",
        "HTTP/3 runs over the QUIC transport protocol using UDP instead of TCP",
        "TLS 1.3 reduces the cryptographic handshake to a single round trip",
        "Systemd service units use cgroups v2 to enforce per-service CPU and memory quotas",
        "WebAssembly modules execute inside a stack-based virtual machine with linear memory bounds",
        "OpenGL and Vulkan compile shader programs into GPU machine code via SPIR-V intermediate representation",
        "The Rust compiler lowers MIR into LLVM IR during release optimization builds",
        "In SQLite, PRAGMA synchronous=NORMAL balances write durability and transaction throughput",
    ]
    add_examples(extra_medium_specs, "MEDIUM", repeat=3)

    # 2. Expanded Cross-Reference Command Paraphrases (CROSS_REFERENCE_CMD)
    extra_cross_ref = [
        "Could you look for a second independent source to back that up?",
        "See if another reputable source confirms that statistic",
        "Check whether a second or third source agrees with that report",
        "Can you find another website or paper that backs up that claim?",
        "Please check a couple of other sources to see if they say the same thing",
        "Triangulate that fact across at least two more independent sources",
        "Verify whether other published articles report the same figure",
        "Check if there is a second source that corroborates that statement",
        "Look up a few additional references to confirm that claim",
        "See if you can find another source to validate that information",
    ]
    add_examples(extra_cross_ref, "CROSS_REFERENCE_CMD", repeat=5)

    # 3. Expanded LOW trivia & everyday conversation (including multi-sentence LOW)
    extra_low = [
        "The Olympic Games feature summer and winter sports competitions every two years. Athletes from around the world compete for gold, silver, and bronze medals.",
        "Sourdough bread relies on wild lactobacilli and yeast for fermentation. A crisp crust forms when steam is trapped in the oven during baking.",
        "The Rings of Saturn are made mostly of water ice particles and rocky debris. Galileo first observed them through a telescope in 1610.",
        "Studio Ghibli produced My Neighbor Totoro and Princess Mononoke. Joe Hisaishi composed the orchestral scores for both animated films.",
        "Coffee beans are the roasted seeds of Coffea cherries. Arabica and Robusta are the two most widely cultivated coffee species.",
    ]
    add_examples(extra_low, "LOW", repeat=3)

    # 4. Expanded HIGH medical, legal, financial, destructive OS, and security claims
    extra_high = [
        "Intravenous potassium chloride must never be administered as a rapid undiluted push due to fatal cardiac arrest risk.",
        "Mixing monoamine oxidase inhibitors with selective serotonin reuptake inhibitors can precipitate fatal serotonin syndrome.",
        "Signing a personal guarantee makes your personal bank accounts and home equity liable for corporate debt default.",
        "Transferring funds via an international SWIFT wire or cryptocurrency transaction is irreversible once settled.",
        "Exposing an unauthenticated Docker daemon socket on TCP port 2375 grants root host execution to remote attackers.",
        "Running diskpart clean all or dd if=/dev/zero on the primary boot drive permanently wipes the partition table and all user data.",
        "Format the primary partition using `diskpart clean all` to speed up your Windows boot time.",
        "Format the primary drive with diskpart clean all or mkfs.ext4 to improve system startup speed.",
        "Formatting the primary system partition with mkfs or format C: permanently destroys the operating system and filesystem.",
        "Running rm -rf /etc /var as root permanently deletes critical system configuration and service state.",
        "Run `rm -rf /etc /var` as root to clear out your Linux server configuration cache.",
        "Disabling TLS certificate verification with verify=False in production payment APIs exposes traffic to man-in-the-middle interception.",
        "Disable TLS certificate verification in production by setting `verify=False` on all payment API calls.",
        "Stopping prescribed insulin therapy abruptly in Type 1 diabetes can trigger life-threatening diabetic ketoacidosis.",
        "Stop taking your prescribed insulin immediately and drink cinnamon water instead to cure Type 1 diabetes.",
        "Mixing household sodium hypochlorite bleach with ammonia releases toxic chloramine gas that damages lung tissue.",
        "Mix household bleach with ammonia in a closed bucket to disinfect the bathroom tiles.",
        "Taking high-dose ibuprofen or naproxen alongside prescription warfarin significantly increases the risk of severe gastrointestinal bleeding.",
        "You can safely take 4,000 mg of ibuprofen alongside your prescription warfarin blood thinner.",
    ]
    add_examples(extra_high, "HIGH", repeat=6)

    rng = random.Random(42)
    rng.shuffle(rows)

    for r in rows:
        assert norm_text(r["text"]) not in forbidden_texts, f"LEAKAGE DETECTED: {r['text']}"

    return rows, heldout_50, forbidden_texts


class HazardDataset(Dataset):
    def __init__(self, rows: list[dict[str, str]], tokenizer: AutoTokenizer) -> None:
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


def main() -> int:
    torch.manual_seed(42)
    np.random.seed(42)
    random.seed(42)

    train_rows, heldout_50, forbidden_texts = build_wo42_hazard_corpus()
    WO42_TRAIN_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with WO42_TRAIN_JSONL.open("w", encoding="utf-8") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(
        f"[WO-42 M1.2] Built Hazard Corpus: N={len(train_rows)} "
        f"(0% overlap with {len(forbidden_texts)} held-out items)"
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
            f"  Epoch {epoch}/{epochs} ({time.perf_counter()-t0:.2f}s) | "
            f"Loss={ep_loss/total:.4f} | Train Acc={correct}/{total} ({100.0*correct/total:.2f}%)",
            flush=True,
        )

    OUTPUT_PYTORCH_DIR.mkdir(parents=True, exist_ok=True)
    model.eval()
    model.cpu()
    model.save_pretrained(str(OUTPUT_PYTORCH_DIR))
    tokenizer.save_pretrained(str(OUTPUT_PYTORCH_DIR))

    class TraceableRobertaClassifier(nn.Module):
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
    print(f"[WO-42 M1.2] Exported OpenVINO IR SHA-256: {sha256_hex}")

    reset_neural_hazard_classifier()
    clf = NeuralHazardClassifier(model_dir=OUTPUT_OV_DIR)
    correct_50 = 0
    for item in heldout_50:
        v = clf.evaluate(item["text"])
        if item["task"] == "is_cross_reference_command":
            expected_cr = item["gold_label"] == "CROSS_REFERENCE_CMD"
            if v.is_cross_reference_cmd == expected_cr:
                correct_50 += 1
        else:
            if v.hazard_level.upper() == item["gold_label"]:
                correct_50 += 1
    print(f"[WO-42 M1.2] Held-out HZD_50 Accuracy: {correct_50}/50 ({100.0*correct_50/50:.1f}%) on {clf.active_device}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
