"""Clause-splitting OpenVINO INT8 Hazard Classifier with automatic NPU -> GPU -> CPU fallback."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import openvino as ov
from tokenizers import Tokenizer

from epistemic_guard.models import resolve_managed_model_dir
from epistemic_guard.schemas import Hazard

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
    r"can|could|should|will|would|while|although|whereas)\b)|"
    r"(?:,\s*|\s+)(?:and|but|then|plus)\s+(?=(?:I|we)\s+|\[(?:ACTION|ACTION_CLAIM)\b)",
    re.IGNORECASE,
)

_HIGH_HAZARD_CUE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:rm\s+-rf|mkfs|diskpart|format\s+[a-z]:|dd\s+if=|drop\s+(?:database|table|schema)|"
    r"truncate\s+table|blkdiscard|lvremove|chmod\s+(?:-r\s+)?777|"
    r"secret_access_key|private_key|id_rsa|seed\s+phrase|mnemonic\s+phrase|"
    r"unsalted\s+(?:sha|md5)|credential\s+hashing|password\s+storage|"
    r"deprecat\w+\s+(?:sha[- ]?1|md5|rc4|des)|(?:deprecated|forbidden)\s+in\s+tls|"
    r"bleach|ammonia|chloramine|hydrofluoric|phosgene|ricin|sarin|"
    r"usda\s+fsis|salmonella|botulism|listeria|trichinella|"
    r"milligrams?|\d+\s*mg\b|dosage|overdose|warfarin|insulin|epinephrine|maoi|"
    r"acetaminophen|paracetamol|ibuprofen|aspirin|"
    r"benzodiazepine|opioid|fentanyl|methotrexate|digoxin|anticoagulant|"
    r"anaphylaxis|chest\s+pain|stroke\s+symptoms|tourniquet|"
    r"gdpr\s+article|hipaa\s+breach|personal\s+data\s+breach|"
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


def split_into_clauses_with_spans(text: str) -> list[tuple[str, int, int]]:
    """Split text into `(clause_text, start_char, end_char)` spans in `text`."""
    if not text or not text.strip():
        return []
    spans: list[tuple[str, int, int]] = []
    cursor = 0
    for match in _CLAUSE_SPLIT_RE.finditer(text):
        seg = text[cursor : match.start()]
        stripped = seg.strip()
        if stripped:
            lead = len(seg) - len(seg.lstrip())
            s_idx = cursor + lead
            e_idx = s_idx + len(stripped)
            spans.append((stripped, s_idx, e_idx))
        cursor = match.end()
    tail = text[cursor:]
    tail_stripped = tail.strip()
    if tail_stripped:
        lead = len(tail) - len(tail.lstrip())
        s_idx = cursor + lead
        e_idx = s_idx + len(tail_stripped)
        spans.append((tail_stripped, s_idx, e_idx))
    return spans


def split_into_clauses(text: str) -> list[str]:
    """Split a single- or multi-clause query/reply into non-empty atomic clauses."""
    return [c for c, _, _ in split_into_clauses_with_spans(text)]


@dataclass(frozen=True)
class HazardVerdict:
    hazard: Hazard
    confidence: float
    clauses: tuple[str, ...]
    device: str
    latency_ms: float


class OpenVINOHazardClassifier:
    """OpenVINO INT8 5-class hazard classifier with automatic CPU fallback."""

    def __init__(
        self,
        model_dir: Path | str | None = None,
        *,
        device: str | None = None,
        confidence_threshold: float = 0.65,
        verify_hashes: bool = False,
        require_neural: bool = False,
        warn_on_missing: bool = True,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self._lock = threading.Lock()
        self.available = False
        self.active_device = "HEURISTIC_CPU"
        self._tokenizer: Tokenizer | None = None
        self._infer_req: ov.InferRequest | None = None

        resolved = resolve_managed_model_dir(
            "hazard",
            model_dir,
            verify_hashes=verify_hashes,
            require_neural=require_neural,
            warn_on_missing=warn_on_missing,
        )
        self.model_dir = resolved
        if resolved is None:
            return

        xml_path = resolved / "openvino_model.xml"
        tok_path = resolved / "tokenizer.json"
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
            if require_neural:
                raise
            self.available = False
            self.active_device = "HEURISTIC_CPU"

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
