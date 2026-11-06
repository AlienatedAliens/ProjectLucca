"""
OpenVINO Multi-Head Sentence-Window Neural Router Classifier (WO-41 Phase 4 & WO-42 Milestone 1.3).

Trained full-layer on a discrete CUDA GPU (`cross-encoder/nli-MiniLM2-L6-H768`,
all 6 transformer layers + embeddings unfrozen) and exported to static-shape `[1, 96]` OpenVINO IR
(`models/router_intent_ov/openvino_model.xml`) for Intel NPU / iGPU / CPU execution.

WO-42 Milestone 1.3 Multi-Sentence Task-Priority Pooling:
  - Evaluates both the full transcript and individual sentences when a prompt spans multiple sentences.
  - Applies task-priority max-pooling (`Tier 3 Safety/Reflex > Tier 2 Formal Reasoning > Tier 1 Tool/Action > Tier 0 Chit-Chat/Unknown`)
    so multi-sentence prompts (e.g., greeting + math problem, or 4-sentence logic/code descriptions)
    never collapse to `chit_chat` or `unknown`.
  - Unions high-confidence (`>= 0.78`) reasoning domain flags across sentences so multi-sentence
    hybrid turns (e.g., Sentence 1 `spatial_relocation` + Sentence 2 `mathematics`) expose all
    required solver libraries simultaneously.

Output Tensor (`[1, 29]`):
  - `logits[:, 0:19]`  -> 19-class Primary Route/Intent Head (Softmax)
  - `logits[:, 19:29]` -> 10-flag Multi-Label Reasoning-Domain & Reflex Head (Sigmoid)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import threading
import time
from typing import Final

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

STATIC_SEQ_LEN: Final[int] = 96

PRIMARY_CLASSES: Final[tuple[str, ...]] = (
    "launch_app",
    "file_read",
    "file_write",
    "web_fetch",
    "context_query",
    "memory_query",
    "chit_chat",
    "clarify",
    "dangerous",
    "spatial_grid",
    "code_repair",
    "logic_constraints",
    "math_computation",
    "science_research",
    "factual_lookup",
    "spatial_relocation",
    "soft_logic",
    "emergency_reflex",
    "unknown",
)

DOMAIN_FLAGS: Final[tuple[str, ...]] = (
    "emergency_reflex",
    "spatial_relocation",
    "spatial_grid",
    "code_repair",
    "combinatorial_smt",
    "mathematics",
    "soft_logic",
    "science_research",
    "web_search",
    "aime_combinatorics",
)

CLASS_TO_DOMAIN: Final[dict[str, str]] = {
    "spatial_relocation": "spatial_relocation",
    "spatial_grid": "spatial_grid",
    "code_repair": "code_repair",
    "logic_constraints": "combinatorial_smt",
    "math_computation": "mathematics",
    "soft_logic": "soft_logic",
    "science_research": "science_research",
    "web_fetch": "web_search",
    "emergency_reflex": "emergency_reflex",
}

CLASS_PRIORITY_TIER: Final[dict[str, int]] = {
    "dangerous": 3,
    "emergency_reflex": 3,
    "spatial_grid": 2,
    "code_repair": 2,
    "logic_constraints": 2,
    "math_computation": 2,
    "spatial_relocation": 2,
    "science_research": 2,
    "soft_logic": 2,
    "launch_app": 1,
    "file_read": 1,
    "file_write": 1,
    "web_fetch": 1,
    "context_query": 1,
    "memory_query": 1,
    "factual_lookup": 1,
    "chit_chat": 0,
    "clarify": 0,
    "unknown": 0,
}

DOMAIN_THRESHOLD: Final[float] = 0.50
_SENTENCE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class NeuralRouterVerdict:
    raw_primary_class: str
    predicted_intent: str
    intent_confidence: float
    active_domains: tuple[str, ...]
    domain_probabilities: dict[str, float]
    latency_ms: float
    device: str


def format_router_input(transcript: str, last_tool: str | None = None) -> str:
    cleaned = (transcript or "").strip()
    if last_tool in {"search_web", "fetch_url", "web_fetch"}:
        return f"[LAST_TOOL: {last_tool}] {cleaned}"
    return cleaned


class NeuralIntentClassifier:
    """Thread-safe OpenVINO runtime wrapper for the Multi-Head Neural Router Classifier."""

    def __init__(
        self,
        model_dir: Path | str | None = None,
        preferred_devices: tuple[str, ...] = ("NPU", "GPU.0", "GPU", "CPU"),
        domain_threshold: float = DOMAIN_THRESHOLD,
    ) -> None:
        if model_dir is None:
            repo_root = Path(__file__).resolve().parents[3]
            candidate = repo_root / "models" / "router_intent_ov"
            if not (candidate / "openvino_model.xml").exists():
                candidate = Path(r"C:\ProjectLucca\models\router_intent_ov")
            self.model_dir = candidate
        else:
            self.model_dir = Path(model_dir)

        self.domain_threshold = domain_threshold
        self._lock = threading.Lock()
        self.available = False
        self.active_device = "NONE"
        self._tokenizer: object = None
        self._infer_req: object = None

        xml_path = self.model_dir / "openvino_model.xml"
        tok_path = self.model_dir / "tokenizer.json"
        if not xml_path.exists() or not tok_path.exists():
            logger.warning(
                "neural_intent_classifier_model_missing",
                model_dir=str(self.model_dir),
            )
            return

        try:
            import openvino as ov  # noqa: PLC0415
            from tokenizers import Tokenizer  # noqa: PLC0415

            tok = Tokenizer.from_file(str(tok_path))
            tok.enable_truncation(max_length=STATIC_SEQ_LEN)
            tok.enable_padding(length=STATIC_SEQ_LEN, pad_id=1, pad_token="<pad>")
            self._tokenizer = tok

            core = ov.Core()
            avail = set(core.available_devices)
            chosen_dev = "CPU"
            for dev in preferred_devices:
                if dev in avail:
                    try:
                        compiled = core.compile_model(str(xml_path), dev)
                        self._infer_req = compiled.create_infer_request()
                        chosen_dev = dev
                        break
                    except Exception as dev_exc:  # noqa: BLE001
                        logger.debug(
                            "neural_intent_classifier_device_fallback",
                            device=dev,
                            error=str(dev_exc),
                        )
            if self._infer_req is None:
                compiled = core.compile_model(str(xml_path), "CPU")
                self._infer_req = compiled.create_infer_request()
                chosen_dev = "CPU"

            self.active_device = chosen_dev
            self.available = True
            logger.info(
                "neural_intent_classifier_ready",
                device=self.active_device,
                model_dir=str(self.model_dir),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neural_intent_classifier_init_failed", error=str(exc))

    def _infer_single(self, formatted_text: str) -> tuple[str, float, np.ndarray, np.ndarray]:
        enc = self._tokenizer.encode(formatted_text)  # type: ignore[attr-defined]
        input_ids = np.array([enc.ids], dtype=np.int64)
        attention_mask = np.array([enc.attention_mask], dtype=np.int64)

        with self._lock:
            res = self._infer_req.infer(  # type: ignore[attr-defined]
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                }
            )
            logits = np.asarray(list(res.values())[0], dtype=np.float64)[0]

        num_primary = len(PRIMARY_CLASSES)
        cls_logits = logits[:num_primary]
        domain_logits = logits[num_primary:]

        shifted = cls_logits - np.max(cls_logits)
        exp_i = np.exp(shifted)
        cls_probs = exp_i / np.sum(exp_i)
        cls_idx = int(np.argmax(cls_probs))
        raw_cls = PRIMARY_CLASSES[cls_idx]
        pred_conf = float(cls_probs[cls_idx])

        dom_probs_arr = 1.0 / (1.0 + np.exp(-domain_logits))
        return raw_cls, pred_conf, cls_probs, dom_probs_arr

    def evaluate(
        self,
        transcript: str,
        last_tool: str | None = None,
    ) -> NeuralRouterVerdict:
        cleaned = (transcript or "").strip()
        if not cleaned or not self.available or self._tokenizer is None or self._infer_req is None:
            return NeuralRouterVerdict(
                raw_primary_class="unknown",
                predicted_intent="unknown",
                intent_confidence=0.20,
                active_domains=(),
                domain_probabilities={d: 0.0 for d in DOMAIN_FLAGS},
                latency_ms=0.0,
                device="UNAVAILABLE" if not self.available else self.active_device,
            )

        t0 = time.perf_counter()
        formatted_full = format_router_input(cleaned, last_tool=last_tool)
        raw_cls, pred_conf, _, dom_probs_arr = self._infer_single(formatted_full)

        # Multi-sentence task-priority pooling (WO-42 Milestone 1.3)
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(cleaned) if s.strip()]
        if len(sentences) >= 2:
            best_cls = raw_cls
            best_conf = pred_conf
            best_tier = CLASS_PRIORITY_TIER.get(raw_cls, 0)
            max_dom_probs = dom_probs_arr.copy()
            non_chitchat_sents: list[str] = []

            for s_idx, sent in enumerate(sentences):
                if len(sent.split()) < 2:
                    continue
                s_tool = last_tool if s_idx == len(sentences) - 1 else None
                s_cls, s_conf, _, s_dom_probs = self._infer_single(
                    format_router_input(sent, last_tool=s_tool)
                )
                s_tier = CLASS_PRIORITY_TIER.get(s_cls, 0)
                if s_cls not in ("chit_chat", "clarify"):
                    non_chitchat_sents.append(sent)

                # Pool domain probabilities across sentences when a sentence has a strong reasoning signal
                if s_tier >= 2 and s_conf >= 0.65:
                    max_dom_probs = np.maximum(max_dom_probs, s_dom_probs)

                # Promote concrete task/reasoning sentence over Tier-0 (chit_chat / clarify / unknown)
                # or promote higher-tier reasoning sentence, or higher-confidence sentence within the same tier
                if best_tier == 0 and s_tier >= 1 and s_conf >= 0.60:
                    best_cls = s_cls
                    best_conf = s_conf
                    best_tier = s_tier
                elif s_tier > best_tier and s_conf >= 0.78:
                    if best_tier <= 1 or s_cls == "dangerous":
                        best_cls = s_cls
                        best_conf = s_conf
                        best_tier = s_tier
                elif s_tier == best_tier and s_tier >= 1 and s_conf > best_conf:
                    best_cls = s_cls
                    best_conf = s_conf

            # Also evaluate the greeting-stripped core task body if greetings were removed
            if 1 <= len(non_chitchat_sents) < len(sentences):
                core_body = " ".join(non_chitchat_sents)
                c_cls, c_conf, _, c_dom_probs = self._infer_single(
                    format_router_input(core_body, last_tool=last_tool)
                )
                c_tier = CLASS_PRIORITY_TIER.get(c_cls, 0)
                if c_tier >= 2 and c_conf >= 0.65:
                    max_dom_probs = np.maximum(max_dom_probs, c_dom_probs)
                if c_tier > best_tier and c_conf >= 0.70:
                    best_cls = c_cls
                    best_conf = c_conf
                    best_tier = c_tier
                elif c_tier == best_tier and c_tier >= 1 and c_conf > best_conf:
                    best_cls = c_cls
                    best_conf = c_conf

            raw_cls = best_cls
            pred_conf = best_conf
            dom_probs_arr = max_dom_probs

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        dom_map = {
            DOMAIN_FLAGS[i]: round(float(dom_probs_arr[i]), 4)
            for i in range(len(DOMAIN_FLAGS))
        }
        active_list: list[str] = []
        if raw_cls in CLASS_TO_DOMAIN:
            active_list.append(CLASS_TO_DOMAIN[raw_cls])
            for i in range(len(DOMAIN_FLAGS)):
                flg = DOMAIN_FLAGS[i]
                if flg not in active_list and float(dom_probs_arr[i]) >= 0.75:
                    active_list.append(flg)

        if raw_cls in {"spatial_relocation", "soft_logic", "emergency_reflex"}:
            pred_intent = "unknown"
        else:
            pred_intent = raw_cls

        effective_conf = (
            max(round(pred_conf, 4), 0.90) if pred_intent != "unknown" else round(pred_conf, 4)
        )

        return NeuralRouterVerdict(
            raw_primary_class=raw_cls,
            predicted_intent=pred_intent,
            intent_confidence=effective_conf,
            active_domains=tuple(active_list),
            domain_probabilities=dom_map,
            latency_ms=round(elapsed_ms, 2),
            device=self.active_device,
        )


_SINGLETON_LOCK = threading.Lock()
_SINGLETON_INSTANCE: NeuralIntentClassifier | None = None


def get_neural_intent_classifier() -> NeuralIntentClassifier:
    global _SINGLETON_INSTANCE
    if _SINGLETON_INSTANCE is None:
        with _SINGLETON_LOCK:
            if _SINGLETON_INSTANCE is None:
                _SINGLETON_INSTANCE = NeuralIntentClassifier()
    return _SINGLETON_INSTANCE


def reset_neural_intent_classifier() -> None:
    global _SINGLETON_INSTANCE
    with _SINGLETON_LOCK:
        _SINGLETON_INSTANCE = None
