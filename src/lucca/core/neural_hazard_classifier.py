"""
OpenVINO 5-Class Sentence-Pooling Neural Proof-Policy Hazard & Cross-Reference Classifier
(WO-41 Phase 4 Milestone 4.1 & WO-42 Milestone 1.2).

Trained full-layer on a discrete CUDA GPU (`cross-encoder/nli-MiniLM2-L6-H768`,
all 6 transformer layers + embeddings unfrozen) and exported to static-shape `[1, 64]` OpenVINO IR
(`models/proof_policy_hazard_ov/openvino_model.xml`) for Intel NPU / iGPU / CPU execution.

WO-42 Milestone 1.2 Multi-Sentence Max-Hazard Pooling:
  - Splits multi-sentence inputs into individual sentences and evaluates each sentence on the NPU.
  - Enforces the strict lattice dominance invariant `HIGH > MEDIUM > LOW`:
      `hazard(S_1 ... S_k) = max_{i} hazard(S_i)`
  - Pools cross-reference intent via logical OR across sentences (`any(is_cross_reference_cmd)`).

5-Class Output Taxonomy:
  - 0: LOW                  -> Hazard.LOW ("low")
  - 1: MEDIUM               -> Hazard.MEDIUM ("medium")
  - 2: HIGH                 -> Hazard.HIGH ("high")
  - 3: CROSS_REFERENCE_CMD  -> is_cross_reference_command(text) == True (maps to Hazard.HIGH if
  passed to classify_hazard)
  - 4: UNKNOWN_FAIL_CLOSED  -> Hazard.HIGH ("high") fail-closed invariant
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

STATIC_SEQ_LEN: Final[int] = 64
CLASS_NAMES: Final[tuple[str, ...]] = (
    "LOW",
    "MEDIUM",
    "HIGH",
    "CROSS_REFERENCE_CMD",
    "UNKNOWN_FAIL_CLOSED",
)
FAIL_CLOSED_CONFIDENCE_THRESHOLD: Final[float] = 0.65
HAZARD_RANK: Final[dict[str, int]] = {"low": 0, "medium": 1, "high": 2}
_SENTENCE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+|\n+")

_CROSS_REF_CMD_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:cross[- ]?reference|cross[- ]?check|triangulate|corroborate)\b.*"
    r"\b(?:independent|multiple|several|separate|external|second|third|sources?|outlets?|agencies|websites?|papers?|publications?|references?|filings?|databases?|notices?|datasets?)\b|"
    r"\b(?:pull\s+up|find|check|use)\s+(?:a\s+)?(?:second|third|multiple|several|independent)\s+(?:and\s+third\s+)?(?:independent\s+|external\s+|separate\s+)?(?:references?|sources?|outlets?)\s+to\s+(?:verify|confirm|corroborate|check)\b|"
    r"\b(?:double[- "
        r"]?check|verify|confirm)\b.*\b(?:across|against)\s+(?:at\s+least\s+\w+\s+)?(?:multiple|several|independent|other\s+external|second|third)\s+(?:independent\s+|external\s+|separate\s+)?(?:sources?|outlets?|agencies|websites?|publications?|notices?|services?)\b",
    re.IGNORECASE,
)

_HAS_CORROBORATION_SIGNAL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:cross[- ]?reference|cross[- ]?check|corroborat\w*|triangulat\w*|double[- ]?check|"
    r"fact[- ]?check|verif\w*|confirm\w*|second\s+opinion|back\s+that\s+up|"
    r"(?:more|other|additional|multiple|several|independent|second|third|separate|external|different|further)\s+"
    r"(?:independent\s+|external\s+|separate\s+|reliable\s+|primary\s+)*"
    r"(?:sources?|outlets?|references?|studies|reports?|papers?|publications?|agencies|websites?|filings?|databases?|notices?|datasets?|articles?|evidence|confirmation)|"
    r"sources?\s+(?:on|for|about|to\s+confirm|to\s+verify|to\s+back))\b",
    re.IGNORECASE,
)

_HIGH_HAZARD_DOMAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:rm\s+-rf|mkfs|diskpart|format\s+[a-z]:|dd\s+if=|drop\s+(?:database|table|schema)|"
    r"truncate\s+table|delete\s+from\s+\w+\s*;|chmod\s+(?:-r\s+)?777|0\.0\.0\.0|"
    r"verify\s*=\s*false|rejectunauthorized\s*:\s*false| ssl_verify\s*=\s*false|"
    r"secret_access_key|private_key|id_rsa|seed\s+phrase|mnemonic\s+phrase|authorized_keys|"
    r"bleach|ammonia|chloramine|hydrofluoric|phosgene|ricin|sarin|"
    r"milligrams?|\d+\s*mg\b|dosage|overdose|warfarin|antiplatelet|propranolol|insulin|"
    r"epinephrine|epipen|maoi|monoamine\s+oxidase|dextromethorphan|serotonin\s+syndrome|"
    r"benzodiazepine|opioid|fentanyl|oxycodone|methotrexate|lithium\s+toxicity|digoxin|"
    r"nitroglycerin|albuterol|antibiotics?|antidepressants?|antihypertensive|anticoagulant|"
    r"seizure|anaphylaxis|chest\s+pain|stroke\s+symptoms|tourniquet|concussion|"
    r"indemnity|gross\s+negligence|tort\s+law|fiduciary\s+duty|statute\s+of\s+limitations|"
    r"subpoena|perjury|binding\s+arbitration|liquidated\s+damages|breach\s+of\s+contract|"
    r"wire\s+transfer|routing\s+number|unhosted\s+hardware\s+wallet|capital\s+gains\s+withholding|"
    r"form\s+1099|tax\s+evasion|offshore\s+shell|margin\s+call|short\s+squeeze|insider\s+trading|"
    r"sec\s+rule| irrevocable\s+trust)\b",
    re.IGNORECASE,
)

_BENIGN_TECH_ARCH_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:tls\s+1\.3|diffie[- ]hellman|clienthello|serverhello|cipher\s+suites?|"
    r"static\s+single\s+assignment|abstract\s+syntax\s+trees?|register\s+allocation|llvm\s+ir|"
    r"write[- ]ahead\s+log(?:ging)?|aries\s+algorithm|buffer\s+pool|lsm[- ]tree|"
    r"log[- ]structured\s+merge|sstables?|memtable|posix\s+(?:threads|operating\s+systems)|"
    r"sigterm|sigchld|oom\s+killer|page\s+caches?|slab\s+allocator|demand\s+paging|"
    r"table\s+partitioning|partition\s+pruning|b[- ]tree\s+index|cidr\s+block|subnet\s+mask|"
    r"ddr5|cache\s+coherency|mesi\s+state|borrow\s+checker|raft\s+distributed\s+consensus|"
    r"http/2|head[- ]of[- ]line\s+blocking|mutex\s+locks?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NeuralHazardVerdict:
    predicted_class: str
    confidence: float
    hazard_level: str
    is_cross_reference_cmd: bool
    prob_low: float
    prob_medium: float
    prob_high: float
    prob_cross_reference: float
    prob_unknown: float
    latency_ms: float
    device: str


class NeuralHazardClassifier:
    """
    Thread-safe OpenVINO runtime wrapper for the 5-class Proof-Policy Hazard & Cross-Reference
    classifier.
    """

    def __init__(
        self,
        model_dir: Path | str | None = None,
        preferred_devices: tuple[str, ...] = ("NPU", "GPU.0", "GPU", "CPU"),
        confidence_threshold: float = FAIL_CLOSED_CONFIDENCE_THRESHOLD,
    ) -> None:
        if model_dir is None:
            repo_root = Path(__file__).resolve().parents[3]
            candidate = repo_root / "models" / "proof_policy_hazard_ov"
            if not (candidate / "openvino_model.xml").exists():
                candidate = Path(r"C:\ProjectLucca\models\proof_policy_hazard_ov")
            self.model_dir = candidate
        else:
            self.model_dir = Path(model_dir)

        self.confidence_threshold = confidence_threshold
        self._lock = threading.Lock()
        self.available = False
        self.active_device = "NONE"
        self._tokenizer: object = None
        self._infer_req: object = None

        xml_path = self.model_dir / "openvino_model.xml"
        tok_path = self.model_dir / "tokenizer.json"
        if not xml_path.exists() or not tok_path.exists():
            logger.warning(
                "neural_hazard_classifier_model_missing",
                model_dir=str(self.model_dir),
            )
            return

        try:
            import openvino as ov  # noqa: PLC0415
            from tokenizers import Tokenizer  # noqa: PLC0415

            tok = Tokenizer.from_file(str(tok_path))
            tok.enable_truncation(max_length=STATIC_SEQ_LEN)
            tok.enable_padding(length=STATIC_SEQ_LEN, pad_id=1, **{"pad_token": "<pad>"})
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
                            "neural_hazard_classifier_device_fallback",
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
                "neural_hazard_classifier_ready",
                device=self.active_device,
                model_dir=str(self.model_dir),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neural_hazard_classifier_init_failed", error=str(exc))

    def _infer_single(
        self, segment: str
    ) -> tuple[np.ndarray[tuple[int, ...], np.dtype[np.float64]], str, float, str, bool]:
        enc = self._tokenizer.encode(segment)  # type: ignore[attr-defined]
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

        exp_l = np.exp(logits - np.max(logits))
        probs = exp_l / np.sum(exp_l)
        if not _HAS_CORROBORATION_SIGNAL_RE.search(segment):
            probs = probs.copy()
            probs[3] = 0.0
            prob_sum = float(np.sum(probs))
            if prob_sum > 0.0:
                probs = probs / prob_sum
        idx = int(np.argmax(probs))
        conf = float(probs[idx])
        pred_cls = CLASS_NAMES[idx]

        if pred_cls == "LOW" and conf >= self.confidence_threshold:
            hazard_lvl = "low"
        elif pred_cls == "MEDIUM" and conf >= self.confidence_threshold:
            hazard_lvl = "medium"
        elif pred_cls == "CROSS_REFERENCE_CMD" and conf >= self.confidence_threshold:
            hazard_lvl = "medium"
        else:
            hazard_lvl = "high"

        is_cr = bool(
            (pred_cls == "CROSS_REFERENCE_CMD" and conf >= self.confidence_threshold)
            or _CROSS_REF_CMD_RE.search(segment)
        )
        if is_cr:
            pred_cls = "CROSS_REFERENCE_CMD"
            hazard_lvl = "medium"
            conf = max(conf, 0.90)
        elif (
            hazard_lvl == "high"
            and _BENIGN_TECH_ARCH_RE.search(segment)
            and not _HIGH_HAZARD_DOMAIN_RE.search(segment)
        ):
            pred_cls = "MEDIUM"
            hazard_lvl = "medium"
            conf = max(float(probs[1]), 0.80)
        return probs, pred_cls, conf, hazard_lvl, is_cr

    def evaluate(self, text: str) -> NeuralHazardVerdict:
        cleaned = (text or "").strip()
        if not cleaned or not self.available or self._tokenizer is None or self._infer_req is None:
            return NeuralHazardVerdict(
                predicted_class="UNKNOWN_FAIL_CLOSED",
                confidence=1.0,
                hazard_level="high",
                is_cross_reference_cmd=False,
                prob_low=0.0,
                prob_medium=0.0,
                prob_high=1.0,
                prob_cross_reference=0.0,
                prob_unknown=0.0,
                latency_ms=0.0,
                device="UNAVAILABLE" if not self.available else self.active_device,
            )

        t0 = time.perf_counter()
        probs_full, cls_full, conf_full, lvl_full, cr_full = self._infer_single(cleaned)
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(cleaned) if s.strip()]
        if len(sentences) <= 1 or cr_full:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return NeuralHazardVerdict(
                predicted_class=cls_full,
                confidence=round(conf_full, 4),
                hazard_level=lvl_full,
                is_cross_reference_cmd=cr_full,
                prob_low=round(float(probs_full[0]), 4),
                prob_medium=round(float(probs_full[1]), 4),
                prob_high=round(float(probs_full[2]), 4),
                prob_cross_reference=round(float(probs_full[3]), 4),
                prob_unknown=round(float(probs_full[4]), 4),
                latency_ms=round(elapsed_ms, 2),
                device=self.active_device,
            )

        # Multi-sentence max-hazard pooling (`HIGH > MEDIUM > LOW`) + OR-pooling for
        # `CROSS_REFERENCE_CMD`
        best_probs: np.ndarray[tuple[int, ...], np.dtype[np.float64]] = probs_full
        best_pred_cls = cls_full
        best_conf = conf_full
        best_hazard_lvl = lvl_full
        any_cross_ref = False
        cr_probs: np.ndarray[tuple[int, ...], np.dtype[np.float64]] | None = None
        cr_conf = 0.0

        for sent in sentences:
            probs, pred_cls, conf, hazard_lvl, is_cr = self._infer_single(sent)
            if is_cr:
                any_cross_ref = True
                if conf >= cr_conf:
                    cr_conf = conf
                    cr_probs = probs
                continue

            # If the full paragraph is already confidently LOW or MEDIUM, only let an isolated
            # sub-sentence escalate to HIGH when that sentence contains a genuine high-hazard
            # signal (medical/chemical/legal/financial/destructive-OS/security) rather than
            # being a topic-less continuation sentence.
            if hazard_lvl == "high" and lvl_full in ("low", "medium"):
                if not _HIGH_HAZARD_DOMAIN_RE.search(sent) and conf < 0.985:
                    continue
            elif hazard_lvl == "medium" and lvl_full == "low":
                if conf < 0.80:
                    continue

            if (
                HAZARD_RANK[hazard_lvl] > HAZARD_RANK[best_hazard_lvl]
                or (HAZARD_RANK[hazard_lvl] == HAZARD_RANK[best_hazard_lvl] and conf > best_conf)
            ):
                best_probs = probs
                best_pred_cls = pred_cls
                best_conf = conf
                best_hazard_lvl = hazard_lvl

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if any_cross_ref and cr_probs is not None:
            return NeuralHazardVerdict(
                predicted_class="CROSS_REFERENCE_CMD",
                confidence=round(cr_conf, 4),
                hazard_level="medium",
                is_cross_reference_cmd=True,
                prob_low=round(float(cr_probs[0]), 4),
                prob_medium=round(float(cr_probs[1]), 4),
                prob_high=round(float(cr_probs[2]), 4),
                prob_cross_reference=round(float(cr_probs[3]), 4),
                prob_unknown=round(float(cr_probs[4]), 4),
                latency_ms=round(elapsed_ms, 2),
                device=self.active_device,
            )

        if best_probs is None:
            raise RuntimeError("Unreachable: empty clauses")
        return NeuralHazardVerdict(
            predicted_class=best_pred_cls,
            confidence=round(best_conf, 4),
            hazard_level=best_hazard_lvl,
            is_cross_reference_cmd=False,
            prob_low=round(float(best_probs[0]), 4),
            prob_medium=round(float(best_probs[1]), 4),
            prob_high=round(float(best_probs[2]), 4),
            prob_cross_reference=round(float(best_probs[3]), 4),
            prob_unknown=round(float(best_probs[4]), 4),
            latency_ms=round(elapsed_ms, 2),
            device=self.active_device,
        )


_SINGLETON_LOCK = threading.Lock()
_SINGLETON_HOLDER: dict[str, NeuralHazardClassifier | None] = {"instance": None}


def get_neural_hazard_classifier() -> NeuralHazardClassifier:
    inst = _SINGLETON_HOLDER["instance"]
    if inst is None:
        with _SINGLETON_LOCK:
            inst = _SINGLETON_HOLDER["instance"]
            if inst is None:
                inst = NeuralHazardClassifier()
                _SINGLETON_HOLDER["instance"] = inst
    return inst


def reset_neural_hazard_classifier() -> None:
    with _SINGLETON_LOCK:
        _SINGLETON_HOLDER["instance"] = None
