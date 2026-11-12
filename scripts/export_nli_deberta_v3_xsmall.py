"""Project Lucca — NLI Verifier v2 Export Script.

Exports `cross-encoder/nli-deberta-v3-xsmall` (22M Disentangled-Attention NLI Cross-Encoder)
to static-shape `[1, 128]` OpenVINO FP16 IR at `models/verifier_deberta_v3_xsmall_ov`
and mirrors to `C:\\ProjectLucca\\models\\verifier_deberta_v3_xsmall_ov` when present.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import openvino as ov
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_ID = "cross-encoder/nli-deberta-v3-xsmall"
STATIC_SEQ_LEN = 128
REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_OUT_DIR = REPO_ROOT / "models" / "verifier_deberta_v3_xsmall_ov"
RUNTIME_OUT_DIR = Path(r"C:\ProjectLucca\models\verifier_deberta_v3_xsmall_ov")


def export_model() -> None:
    print(f"Exporting {MODEL_ID} to OpenVINO FP16 IR at {REPO_OUT_DIR}...")
    REPO_OUT_DIR.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID).eval()

    d_ids = torch.ones((1, STATIC_SEQ_LEN), dtype=torch.long)
    d_mask = torch.ones((1, STATIC_SEQ_LEN), dtype=torch.long)
    ov_model = ov.convert_model(
        model,
        example_input={"input_ids": d_ids, "attention_mask": d_mask},
        input=[
            ("input_ids", [1, STATIC_SEQ_LEN], ov.Type.i64),
            ("attention_mask", [1, STATIC_SEQ_LEN], ov.Type.i64),
        ],
    )
    ov_model.reshape({"input_ids": [1, STATIC_SEQ_LEN], "attention_mask": [1, STATIC_SEQ_LEN]})
    ov.save_model(
        ov_model,
        str(REPO_OUT_DIR / "openvino_model.xml"),
        compress_to_fp16=True,
    )
    tokenizer.save_pretrained(str(REPO_OUT_DIR))
    model.config.save_pretrained(str(REPO_OUT_DIR))

    if RUNTIME_OUT_DIR.parent.exists():
        RUNTIME_OUT_DIR.mkdir(parents=True, exist_ok=True)
        for item in REPO_OUT_DIR.iterdir():
            if item.is_file():
                shutil.copy2(item, RUNTIME_OUT_DIR / item.name)

    xml_path = REPO_OUT_DIR / "openvino_model.xml"
    bin_path = REPO_OUT_DIR / "openvino_model.bin"
    tok_path = REPO_OUT_DIR / "tokenizer.json"
    assert xml_path.exists() and bin_path.exists() and tok_path.exists()

    cfg = json.loads((REPO_OUT_DIR / "config.json").read_text(encoding="utf-8"))
    print(f"[EXPORT COMPLETE] xml={xml_path.stat().st_size:,}B bin={bin_path.stat().st_size:,}B")
    print(f"  id2label={cfg.get('id2label')}")


if __name__ == "__main__":
    export_model()
