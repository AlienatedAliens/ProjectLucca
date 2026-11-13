"""OpenVINO INT8 3-class Natural Language Inference (`contradiction`, `entailment`, `neutral`)
verifier for cross-passage dispute and corroboration checks.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Final

import numpy as np
import openvino as ov
from tokenizers import Tokenizer

from epistemic_guard.models import resolve_managed_model_dir
from epistemic_guard.schemas import NLIVerdict

DEFAULT_NLI_SEQ_LEN: Final[int] = 128

_WIRE_DATELINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:"
    r"report\s+from\s+[^\s:]+\s*:\s*"
    r"|\([a-z0-9\s\-]{3,30}\)\s*[\u2014\u2013\-:]+\s*"
    r"|[A-Z][A-Z\s.,']{2,28}(?:\([A-Za-z0-9\s.]+\))?\s*[\u2014\u2013\-]+\s*"
    r"|according\s+to\s+(?:[a-z\-]+\s+){0,4}(?:wire\s+)?(?:reports?|dispatches?|services?)\s*,\s*"
    r")+",
    re.IGNORECASE,
)


def _strip_wire_prefix(text: str) -> str:
    cleaned = (text or "").strip()
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _WIRE_DATELINE_RE.sub("", cleaned).strip()
    return cleaned


class OpenVINONLIVerifier:
    """Thread-safe OpenVINO INT8 DeBERTa-v3-xsmall 3-class NLI cross-encoder."""

    def __init__(
        self,
        model_dir: Path | str | None = None,
        *,
        device: str | None = None,
        verify_hashes: bool = False,
        require_neural: bool = False,
        warn_on_missing: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self.available = False
        self.active_device = "DETERMINISTIC_CPU"
        self._tokenizer: Tokenizer | None = None
        self._infer_req: ov.InferRequest | None = None
        self._input_names: set[str] = set()
        self._con_idx = 0
        self._ent_idx = 1
        self._neu_idx = 2

        resolved = resolve_managed_model_dir(
            "nli",
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
        cfg_path = resolved / "config.json"
        try:
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                id2label = cfg.get("id2label", {})
                if isinstance(id2label, dict) and id2label:
                    lmap = {str(v).lower(): int(k) for k, v in id2label.items()}
                    self._con_idx = lmap.get("contradiction", 0)
                    self._ent_idx = lmap.get("entailment", 1)
                    self._neu_idx = lmap.get("neutral", 2)

            core = ov.Core()
            model = core.read_model(str(xml_path))
            seq_len = DEFAULT_NLI_SEQ_LEN
            if model.inputs and model.inputs[0].partial_shape.is_static:
                seq_len = int(model.inputs[0].shape[1])
            self._input_names = {name for inp in model.inputs for name in inp.get_names()}

            tok = Tokenizer.from_file(str(tok_path))
            tok.enable_truncation(max_length=seq_len)
            tok.enable_padding(length=seq_len, pad_id=0, **{"pad_token": "[PAD]"})
            self._tokenizer = tok

            avail = set(core.available_devices)
            candidates = (device,) if device is not None else ("CPU", "GPU.0", "GPU")
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
            self.active_device = "DETERMINISTIC_CPU"

    def infer_probs(self, premise: str, hypothesis: str) -> tuple[float, float, float]:
        """Return `(contradiction, entailment, neutral)` probabilities in `[0.0, 1.0]`."""
        if not self.available or self._tokenizer is None or self._infer_req is None:
            return (0.0, 0.0, 1.0)
        p_clean = unicodedata.normalize("NFC", _strip_wire_prefix(premise))[:512]
        h_clean = unicodedata.normalize("NFC", _strip_wire_prefix(hypothesis))[:512]
        if not p_clean or not h_clean:
            return (0.0, 0.0, 1.0)

        enc = self._tokenizer.encode(p_clean, h_clean)
        feed: dict[str, np.ndarray[Any, Any]] = {}
        if "input_ids" in self._input_names:
            feed["input_ids"] = np.array([enc.ids], dtype=np.int64)
        if "attention_mask" in self._input_names:
            feed["attention_mask"] = np.array([enc.attention_mask], dtype=np.int64)
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)

        with self._lock:
            res = self._infer_req.infer(feed)
            logits = np.asarray(list(res.values())[0], dtype=np.float64)[0]

        exp_l = np.exp(logits - np.max(logits))
        probs = exp_l / np.sum(exp_l)
        con_p = float(probs[self._con_idx])
        ent_p = float(probs[self._ent_idx])
        neu_p = (
            float(probs[self._neu_idx])
            if self._neu_idx < probs.shape[0]
            else max(0.0, 1.0 - con_p - ent_p)
        )
        return (con_p, ent_p, neu_p)

    def infer_pair(self, premise: str, hypothesis: str) -> NLIVerdict:
        """Evaluate `(premise, hypothesis)` and return a structured `NLIVerdict`."""
        t0 = time.perf_counter()
        con_p, ent_p, neu_p = self.infer_probs(premise, hypothesis)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        scores = {
            "contradiction": con_p,
            "entailment": ent_p,
            "neutral": neu_p,
        }
        top_lbl = max(scores, key=lambda k: scores[k])
        return NLIVerdict(
            label=top_lbl,
            contradiction=round(con_p, 4),
            entailment=round(ent_p, 4),
            neutral=round(neu_p, 4),
            device=self.active_device,
            latency_ms=elapsed_ms,
        )

    def bidirectional_summary(self, text_a: str, text_b: str) -> tuple[float, float]:
        """Return `(max_contradiction, max_entailment)` across `(A -> B, B -> A)`."""
        con_ab, ent_ab, _ = self.infer_probs(text_a, text_b)
        con_ba, ent_ba, _ = self.infer_probs(text_b, text_a)
        return (max(con_ab, con_ba), max(ent_ab, ent_ba))
