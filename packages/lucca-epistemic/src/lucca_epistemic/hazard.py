"""Clause-splitting OpenVINO Hazard Classifier with automatic NPU -> GPU -> CPU fallback."""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import openvino as ov
from tokenizers import Tokenizer

from lucca_epistemic.schemas import Hazard

DEFAULT_SEQ_LEN: Final[int] = 64
CLASS_NAMES: Final[tuple[str, ...]] = (
    "LOW",
    "MEDIUM",
    "HIGH",
    "CROSS_REFERENCE_CMD",
    "UNKNOWN_FAIL_CLOSED",
)
HAZARD_RANK: Final[dict[Hazard, int]] = {
    Hazard.LOW: 0,
    Hazard.MEDIUM: 1,
    Hazard.HIGH: 2,
}

_CLAUSE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<=[.!?])\s+|\n+|;\s+|,\s+(?=(?:how|what|why|when|where|which|who|does|do|did|"
    r"can|could|should|will|would|while|although|whereas)\b)",
    re.IGNORECASE,
)

_HIGH_HAZARD_CUE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:rm\s+-rf|mkfs|diskpart|format\s+[a-z]:|dd\s+if=|drop\s+(?:database|table|schema)|"
    r"truncate\s+table|blkdiscard|lvremove|chmod\s+(?:-r\s+)?777|"
    r"secret_access_key|private_key|id_rsa|seed\s+phrase|mnemonic\s+phrase|"
    r"bleach|ammonia|chloramine|hydrofluoric|phosgene|ricin|sarin|"
    r"milligrams?|\d+\s*mg\b|dosage|overdose|warfarin|insulin|epinephrine|maoi|"
    r"benzodiazepine|opioid|fentanyl|methotrexate|digoxin|anticoagulant|"
    r"anaphylaxis|chest\s+pain|stroke\s+symptoms|tourniquet|"
    r"fiduciary\s+duty|statute\s+of\s+limitations|subpoena|perjury|binding\s+arbitration|"
    r"wire\s+transfer|tax\s+evasion|margin\s+call|insider\s+trading)\b",
    re.IGNORECASE,
)

_LOW_TRIVIA_CUE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:capital\s+of|who\s+wrote|who\s+directed|who\s+painted|box\s+office|album|"
    r"olympic|world\s+cup|mascot|constellation|recipe\s+for\s+pancakes|board\s+game|"
    r"novel|symphony|pokedex|pokemon|hogwarts|middle[- ]earth)\b",
    re.IGNORECASE,
)


def split_into_clauses(text: str) -> list[str]:
    """Split a single- or multi-clause query into non-empty atomic clauses."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(cleaned) if p and p.strip()]
    return parts if parts else [cleaned]


@dataclass(frozen=True)
class HazardVerdict:
    hazard: Hazard
    confidence: float
    clauses: tuple[str, ...]
    device: str
    latency_ms: float


class OpenVINOHazardClassifier:
    """OpenVINO 5-class hazard classifier with automatic CPU fallback (`device="CPU"`)."""

    def __init__(
        self,
        model_dir: Path | str | None = None,
        *,
        device: str | None = None,
        confidence_threshold: float = 0.65,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self._lock = threading.Lock()
        self.available = False
        self.active_device = "HEURISTIC_CPU"
        self._tokenizer: Tokenizer | None = None
        self._infer_req: ov.InferRequest | None = None

        resolved = self._resolve_model_dir(model_dir)
        self.model_dir = resolved
        if resolved is None:
            return

        xml_path = resolved / "openvino_model.xml"
        tok_path = resolved / "tokenizer.json"
        if not xml_path.exists() or not tok_path.exists():
            return

        try:
            core = ov.Core()
            model = core.read_model(str(xml_path))
            seq_len = DEFAULT_SEQ_LEN
            if model.inputs and model.inputs[0].partial_shape.is_static:
                seq_len = int(model.inputs[0].shape[1])

            tok = Tokenizer.from_file(str(tok_path))
            tok.enable_truncation(max_length=seq_len)
            tok.enable_padding(length=seq_len, pad_id=1, **{"pad_token": "<pad>"})
            self._tokenizer = tok

            avail = set(core.available_devices)
            candidates = (device,) if device is not None else ("NPU", "GPU.0", "GPU", "CPU")
            for dev in candidates:
                if dev == "CPU" or dev in avail:
                    try:
                        compiled = core.compile_model(model, dev)
                        self._infer_req = compiled.create_infer_request()
                        self.active_device = dev
                        self.available = True
                        break
                    except RuntimeError:
                        pass
            if not self.available:
                compiled = core.compile_model(model, "CPU")
                self._infer_req = compiled.create_infer_request()
                self.active_device = "CPU"
                self.available = True
        except Exception:
            self.available = False
            self.active_device = "HEURISTIC_CPU"

    @staticmethod
    def _resolve_model_dir(model_dir: Path | str | None) -> Path | None:
        if model_dir is not None:
            return Path(model_dir)
        env_dir = os.environ.get("LUCCA_HAZARD_MODEL_DIR")
        if env_dir:
            return Path(env_dir)
        for cand in (
            Path.cwd() / "models" / "proof_policy_hazard_ov",
            Path(__file__).resolve().parents[4] / "models" / "proof_policy_hazard_ov",
            Path(r"C:\ProjectLucca\models\proof_policy_hazard_ov"),
        ):
            if (cand / "openvino_model.xml").exists():
                return cand
        return None

    def _classify_clause(self, clause: str) -> tuple[Hazard, float]:
        if _HIGH_HAZARD_CUE_RE.search(clause):
            return (Hazard.HIGH, 0.95)
        if not self.available or self._tokenizer is None or self._infer_req is None:
            if _LOW_TRIVIA_CUE_RE.search(clause):
                return (Hazard.LOW, 0.80)
            return (Hazard.MEDIUM, 0.70)

        enc = self._tokenizer.encode(clause)
        input_ids = np.array([enc.ids], dtype=np.int64)
        attention_mask = np.array([enc.attention_mask], dtype=np.int64)
        with self._lock:
            res = self._infer_req.infer({"input_ids": input_ids, "attention_mask": attention_mask})
            logits = np.asarray(list(res.values())[0], dtype=np.float64)[0]

        exp_l = np.exp(logits - np.max(logits))
        probs = exp_l / np.sum(exp_l)
        probs = probs.copy()
        probs[3] = 0.0
        total = float(np.sum(probs))
        if total > 0.0:
            probs /= total

        idx = int(np.argmax(probs))
        conf = float(probs[idx])
        pred_cls = CLASS_NAMES[idx]
        if pred_cls == "LOW" and conf >= self.confidence_threshold:
            return (Hazard.LOW, conf)
        if pred_cls == "MEDIUM" and conf >= self.confidence_threshold:
            return (Hazard.MEDIUM, conf)
        return (Hazard.HIGH, conf)

    def evaluate(self, query_or_claim: str) -> HazardVerdict:
        t0 = time.perf_counter()
        clauses = split_into_clauses(query_or_claim)
        if not clauses:
            return HazardVerdict(
                hazard=Hazard.HIGH,
                confidence=1.0,
                clauses=(),
                device=self.active_device,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 3),
            )

        best_hazard = Hazard.LOW
        best_conf = 0.0
        for idx, cl in enumerate(clauses):
            hz, conf = self._classify_clause(cl)
            if idx == 0 or HAZARD_RANK[hz] > HAZARD_RANK[best_hazard]:
                best_hazard = hz
                best_conf = conf
            elif hz == best_hazard and conf > best_conf:
                best_conf = conf

        if len(clauses) > 1 and best_hazard != Hazard.HIGH:
            full_hz, full_conf = self._classify_clause(query_or_claim.strip())
            if HAZARD_RANK[full_hz] > HAZARD_RANK[best_hazard]:
                best_hazard = full_hz
                best_conf = full_conf

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return HazardVerdict(
            hazard=best_hazard,
            confidence=round(best_conf, 4),
            clauses=tuple(clauses),
            device=self.active_device,
            latency_ms=elapsed_ms,
        )
