"""
Project Lucca — WO-37 Phase 2: NLI Model Export Script
Exports cross-encoder/nli-MiniLM2-L6-H768 to OpenVINO INT8 IR format.
"""

from __future__ import annotations

import json
from pathlib import Path

from optimum.intel.openvino import OVModelForSequenceClassification
from transformers import AutoTokenizer

MODEL_ID = "cross-encoder/nli-MiniLM2-L6-H768"
OUT_DIR = Path(r"C:\ProjectLucca\models\verifier_minilm")


def export_model() -> None:
    print(f"Exporting {MODEL_ID} to OpenVINO INT8 at {OUT_DIR}...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Export via optimum-intel with 8-bit quantization
    try:
        model = OVModelForSequenceClassification.from_pretrained(
            MODEL_ID,
            export=True,
            load_in_8bit=True,
            compile=False,
        )
    except Exception as exc:
        print(f"Failed with load_in_8bit=True ({exc}), falling back to standard export...")
        model = OVModelForSequenceClassification.from_pretrained(
            MODEL_ID,
            export=True,
            compile=False,
        )

    model.save_pretrained(OUT_DIR)
    print("Model saved successfully.")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    tokenizer.save_pretrained(OUT_DIR)
    print("Tokenizer saved successfully.")

    xml_path = OUT_DIR / "openvino_model.xml"
    bin_path = OUT_DIR / "openvino_model.bin"
    tok_path = OUT_DIR / "tokenizer.json"

    assert xml_path.exists(), f"Missing {xml_path}"
    assert bin_path.exists(), f"Missing {bin_path}"
    assert tok_path.exists(), f"Missing {tok_path}"

    xml_size = xml_path.stat().st_size
    bin_size = bin_path.stat().st_size
    tok_size = tok_path.stat().st_size

    print(f"[STOP GATE CONFIRMED]")
    print(f"  {xml_path.name}: {xml_size:,} bytes")
    print(f"  {bin_path.name}: {bin_size:,} bytes")
    print(f"  {tok_path.name}: {tok_size:,} bytes")

    config_path = OUT_DIR / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        id2label = cfg.get("id2label", {})
        print(f"  id2label mapping: {id2label}")


if __name__ == "__main__":
    export_model()
