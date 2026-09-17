"""
Project Lucca — Embedding Subsystem (MiniLM on Intel NPU)
Spec 04 §3, Spec 11 §4
"""

import time
from pathlib import Path

import numpy as np
import openvino as ov
import structlog

try:
    from transformers import AutoTokenizer
except ImportError:
    AutoTokenizer = None

logger = structlog.get_logger(__name__)

MODEL_DIR = Path(r"C:\ProjectLucca\models\embed\all-MiniLM-L6-v2")


class EmbedWorker:
    def __init__(self) -> None:
        self.device = "CPU"
        self.compiled = None
        self.tokenizer = None
        self._init_model()

    def _init_model(self) -> None:
        xml_path = MODEL_DIR / "openvino_model.xml"
        if not xml_path.exists():
            return

        core = ov.Core()
        devices = core.available_devices

        # Primary: NPU static 128; Fallback: CPU
        target_dev = "NPU" if "NPU" in devices else "CPU"
        model = core.read_model(xml_path)

        if target_dev == "NPU":
            model.reshape({
                "input_ids": [1, 128],
                "attention_mask": [1, 128],
                "token_type_ids": [1, 128]
            })
            self.device = "NPU"
        else:
            self.device = "CPU"

        self.compiled = core.compile_model(model, target_dev)

        # Load tokenizer
        if AutoTokenizer is not None and MODEL_DIR.exists():
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
            except (OSError, RuntimeError) as exc:
                logger.warning("embed_tokenizer_init_failed", error=str(exc))
                self.tokenizer = None
        else:
            self.tokenizer = None

    def embed_text(self, texts: list[str]) -> tuple[list[list[float]], int, float]:
        t0 = time.perf_counter()
        if not texts or self.compiled is None:
            return [[0.0] * 384 for _ in texts], 384, 0.0

        vectors: list[list[float]] = []
        infer_req = self.compiled.create_infer_request()

        for t in texts:
            if self.tokenizer:
                enc = self.tokenizer(
                    t,
                    max_length=128,
                    padding="max_length",
                    truncation=True,
                    return_tensors="np",
                )
                default_type_ids = np.zeros((1, 128), dtype=np.int64)
                token_type_ids = enc.get("token_type_ids", default_type_ids).astype(np.int64)
                inp = {
                    "input_ids": enc["input_ids"].astype(np.int64),
                    "attention_mask": enc["attention_mask"].astype(np.int64),
                    "token_type_ids": token_type_ids,
                }
            else:
                # Basic token length dummy for testing without transformers
                inp = {
                    "input_ids": np.ones((1, 128), dtype=np.int64),
                    "attention_mask": np.ones((1, 128), dtype=np.int64),
                    "token_type_ids": np.zeros((1, 128), dtype=np.int64)
                }

            out = infer_req.infer(inp)
            # Output is usually last_hidden_state [1, 128, 384]
            out_tensor = list(out.values())[0]
            if len(out_tensor.shape) == 3:
                # Mean pooling
                vec = np.mean(out_tensor[0], axis=0)
            else:
                vec = out_tensor[0]

            # L2 normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec.tolist())

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return vectors, 384, elapsed_ms
