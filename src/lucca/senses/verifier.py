"""
Project Lucca — Semantic Verifier Subsystem (MiniLM-L6 NLI on Intel CPU/NPU)
Spec 04 §3, Spec 11 §4, Release v1.35.7 (Phase 2), WO-37 Phase 2
"""

import json
import threading
import time
import unicodedata
from collections import OrderedDict
from pathlib import Path

import numpy as np
import openvino as ov
import structlog

try:
    from tokenizers import Tokenizer
except ImportError:
    Tokenizer = None  # type: ignore[assignment, misc]

from lucca.core.schemas import VerificationResult, VerifierLabel

logger = structlog.get_logger(__name__)

import os

REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_verifier_model_dir() -> Path:
    """Resolve verifier model directory from environment or repo root, or raise FileNotFoundError."""
    env_dir = os.environ.get("LUCCA_VERIFIER_MODEL_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.exists():
            return p
        raise FileNotFoundError(
            f"LUCCA_VERIFIER_MODEL_DIR specified directory does not exist: '{p}'. "
            "Please download cross-encoder/nli-MiniLM2-L6-H768 or set a valid path."
        )

    default_path = REPO_ROOT / "models" / "verifier_minilm"
    if default_path.exists():
        return default_path

    export_script = REPO_ROOT / "scripts" / "export_nli_minilm.py"
    msg = (
        f"Verifier model directory not found at '{default_path}'. "
        "Please download cross-encoder/nli-MiniLM2-L6-H768 or set LUCCA_VERIFIER_MODEL_DIR."
    )
    if export_script.exists():
        msg += f" Alternatively, generate it locally by running: python {export_script.relative_to(REPO_ROOT)}"
    raise FileNotFoundError(msg)


try:
    DEFAULT_VERIFIER_DIR = _resolve_verifier_model_dir()
except FileNotFoundError:
    DEFAULT_VERIFIER_DIR = REPO_ROOT / "models" / "verifier_minilm"

VERIFIER_MINILM_DIR = DEFAULT_VERIFIER_DIR


class BoundedLRUPairCache:
    """Thread-safe bounded LRU cache for (premise, hypothesis) verification pairs."""

    def __init__(self, capacity: int = 1024) -> None:
        self.capacity = capacity
        self._cache: OrderedDict[tuple[str, str], VerificationResult] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, str]) -> VerificationResult | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def set(self, key: tuple[str, str], val: VerificationResult) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = val
            if len(self._cache) > self.capacity:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


class VerifierWorker:
    """
    Sub-25ms in-process OpenVINO NLI inference worker.
    Runs on Intel Core Ultra CPU/NPU with 0 MB VRAM overhead.
    """

    def __init__(
        self,
        device: str | None = None,
        model_dir: Path | None = None,
        timeout_ms: float = 50.0,
        cache_capacity: int = 1024,
    ) -> None:
        if model_dir is not None:
            self.model_dir = Path(model_dir)
            if not self.model_dir.exists():
                export_script = REPO_ROOT / "scripts" / "export_nli_minilm.py"
                msg = (
                    f"Verifier model directory not found at '{self.model_dir}'. "
                    "Please download cross-encoder/nli-MiniLM2-L6-H768 or set LUCCA_VERIFIER_MODEL_DIR."
                )
                if export_script.exists():
                    msg += f" Alternatively, generate it locally by running: python {export_script.relative_to(REPO_ROOT)}"
                raise FileNotFoundError(msg)
        else:
            self.model_dir = _resolve_verifier_model_dir()
        self.timeout_ms = timeout_ms
        self._requested_device = device
        self.device = "CPU"
        self._infer_lock = threading.Lock()
        self.compiled: object | None = None
        self.infer_request: object | None = None
        self.tokenizer: object | None = None
        self._input_names: list[str] = []
        self._cache = BoundedLRUPairCache(capacity=cache_capacity)
        self._init_model()

    def _init_model(self) -> None:
        xml_path = self.model_dir / "openvino_model.xml"
        tok_path = self.model_dir / "tokenizer.json"

        self.label_map: dict[str, int] = {"contradiction": 0, "entailment": 1, "neutral": 2}
        config_path = self.model_dir / "config.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                id2label = cfg.get("id2label", {})
                if id2label:
                    self.label_map = {str(v).lower(): int(k) for k, v in id2label.items()}
            except Exception as exc:
                logger.debug("verifier_config_read_failed", error=str(exc))

        # Load fast Rust tokenizer
        if Tokenizer is not None and tok_path.exists():
            try:
                tok = Tokenizer.from_file(str(tok_path))
                tok.enable_truncation(max_length=128)
                tok.enable_padding(length=128)
                self.tokenizer = tok
            except Exception as exc:
                logger.warning("verifier_tokenizer_init_failed", error=str(exc))
                self.tokenizer = None

        if not xml_path.exists():
            return

        try:
            core = ov.Core()
            available = core.available_devices

            if self._requested_device is not None:
                target_dev = self._requested_device
            else:
                # Default to CPU; NPU compile fallback if requested/available
                target_dev = "CPU"

            model = core.read_model(str(xml_path))

            # Compile with automatic fallback to CPU if NPU fails (Trap 1 guard)
            try:
                self.compiled = core.compile_model(model, target_dev)
                self.device = target_dev
            except Exception as compile_exc:
                if target_dev != "CPU":
                    logger.warning(
                        "verifier_npu_compile_fallback_to_cpu",
                        error=str(compile_exc),
                    )
                    self.compiled = core.compile_model(model, "CPU")
                    self.device = "CPU"
                else:
                    raise compile_exc

            if self.compiled is not None:
                compiled_model: ov.CompiledModel = self.compiled  # type: ignore[assignment]
                self.infer_request = compiled_model.create_infer_request()
                self._input_names = [inp.get_any_name() for inp in compiled_model.inputs]
        except Exception as init_exc:
            logger.warning("verifier_model_init_failed", error=str(init_exc))
            self.compiled = None
            self.infer_request = None

    def check_consistency(
        self,
        *,
        premise: str,
        hypothesis: str,
    ) -> VerificationResult:
        """
        Evaluate NLI relationship between premise and hypothesis.
        Keyword-only arguments prevent hypothesis directionality inversion (Trap 3).
        """
        t0 = time.perf_counter()

        # NFC normalize inputs for determinism and cache keys
        norm_premise = unicodedata.normalize("NFC", premise.strip())
        norm_hypothesis = unicodedata.normalize("NFC", hypothesis.strip())
        cache_key = (norm_premise, norm_hypothesis)

        cached_hit = self._cache.get(cache_key)
        if cached_hit is not None:
            hit_latency = round((time.perf_counter() - t0) * 1000.0, 2)
            return cached_hit.model_copy(
                update={
                    "cached": True,
                    "latency_ms": hit_latency,
                }
            )

        # Fail-open if model or tokenizer is unavailable
        if self.compiled is None or self.tokenizer is None:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            logger.warning(
                "verifier_degraded",
                reason="model_or_tokenizer_unavailable",
                latency_ms=elapsed_ms,
            )
            return VerificationResult(
                label=VerifierLabel.UNCERTAIN,
                confidence=0.0,
                latency_ms=elapsed_ms,
                degraded=True,
                premise=premise,
                hypothesis=hypothesis,
            )

        try:
            tok: Tokenizer = self.tokenizer  # type: ignore[assignment]
            # Encode premise and hypothesis pair
            encoding = tok.encode(norm_premise, norm_hypothesis)

            input_ids = np.array([encoding.ids], dtype=np.int64)
            attention_mask = np.array([encoding.attention_mask], dtype=np.int64)

            feed_dict: dict[str, np.ndarray] = {}
            if "input_ids" in self._input_names:
                feed_dict["input_ids"] = input_ids
            if "attention_mask" in self._input_names:
                feed_dict["attention_mask"] = attention_mask
            if "token_type_ids" in self._input_names:
                token_type_ids = np.array([encoding.type_ids], dtype=np.int64)
                feed_dict["token_type_ids"] = token_type_ids

            with self._infer_lock:
                infer_req: ov.InferRequest = self.infer_request or self.compiled.create_infer_request()  # type: ignore[assignment]
                outputs = infer_req.infer(feed_dict)

            # Extract 3-class logits
            out_tensor = list(outputs.values())[0]
            logits = np.squeeze(out_tensor)

            # Softmax calculation
            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / np.sum(exp_logits)

            # MiniLM NLI label mapping: 0: contradiction, 1: entailment, 2: neutral
            ent_idx = self.label_map.get("entailment", 1)
            neu_idx = self.label_map.get("neutral", 2)
            con_idx = self.label_map.get("contradiction", 0)

            entailment_prob = float(probs[ent_idx])
            neutral_prob = float(probs[neu_idx])
            contradiction_prob = float(probs[con_idx])

            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # Guard against timeout (>50ms)
            if elapsed_ms > self.timeout_ms:
                logger.warning(
                    "verifier_degraded",
                    reason="timeout",
                    latency_ms=round(elapsed_ms, 2),
                    timeout_ms=self.timeout_ms,
                )
                return VerificationResult(
                    label=VerifierLabel.UNCERTAIN,
                    entailment_prob=entailment_prob,
                    contradiction_prob=contradiction_prob,
                    neutral_prob=neutral_prob,
                    confidence=0.0,
                    latency_ms=round(elapsed_ms, 2),
                    degraded=True,
                    premise=premise,
                    hypothesis=hypothesis,
                )

            # Decision policy:
            # - Pre-registered threshold tau = 0.50
            # - Uncertainty band [0.40, 0.60] -> UNCERTAIN (never force binary on ambiguous pairs)
            dominant_prob = float(max(entailment_prob, neutral_prob, contradiction_prob))

            if entailment_prob > contradiction_prob and entailment_prob > neutral_prob:
                if 0.40 <= entailment_prob <= 0.60:
                    label = VerifierLabel.UNCERTAIN
                elif entailment_prob > 0.60:
                    label = VerifierLabel.ENTAILMENT
                else:
                    label = VerifierLabel.UNCERTAIN
                confidence = entailment_prob
            elif contradiction_prob > entailment_prob and contradiction_prob > neutral_prob:
                if 0.40 <= contradiction_prob <= 0.60:
                    label = VerifierLabel.UNCERTAIN
                elif contradiction_prob > 0.60:
                    label = VerifierLabel.CONTRADICTION
                else:
                    label = VerifierLabel.UNCERTAIN
                confidence = contradiction_prob
            elif neutral_prob >= entailment_prob and neutral_prob >= contradiction_prob:
                if 0.40 <= neutral_prob <= 0.60:
                    label = VerifierLabel.UNCERTAIN
                elif neutral_prob > 0.60:
                    label = VerifierLabel.NEUTRAL
                else:
                    label = VerifierLabel.UNCERTAIN
                confidence = neutral_prob
            else:
                label = VerifierLabel.UNCERTAIN
                confidence = dominant_prob

            result = VerificationResult(
                label=label,
                entailment_prob=round(entailment_prob, 4),
                contradiction_prob=round(contradiction_prob, 4),
                neutral_prob=round(neutral_prob, 4),
                confidence=round(confidence, 4),
                latency_ms=round(elapsed_ms, 2),
                cached=False,
                degraded=False,
                premise=premise,
                hypothesis=hypothesis,
            )

            self._cache.set(cache_key, result)
            return result

        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            logger.warning(
                "verifier_degraded",
                reason="inference_exception",
                error=str(exc),
                latency_ms=elapsed_ms,
            )
            return VerificationResult(
                label=VerifierLabel.UNCERTAIN,
                confidence=0.0,
                latency_ms=elapsed_ms,
                degraded=True,
                premise=premise,
                hypothesis=hypothesis,
            )


class LocalSemanticVerifierPort:
    """Local in-process implementation of SemanticVerifierPort using VerifierWorker."""

    def __init__(self, worker: VerifierWorker | None = None) -> None:
        self.worker = worker or VerifierWorker()

    def check_consistency(
        self,
        *,
        premise: str,
        hypothesis: str,
    ) -> VerificationResult:
        return self.worker.check_consistency(premise=premise, hypothesis=hypothesis)
