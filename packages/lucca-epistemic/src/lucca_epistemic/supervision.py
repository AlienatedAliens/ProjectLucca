"""Clause-level Receipt Supervisor with OpenVINO CPU/NPU support and deterministic fallback."""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy as np
import openvino as ov
from tokenizers import Tokenizer

from lucca_epistemic.hazard import split_into_clauses
from lucca_epistemic.schemas import ClauseSupervisionVerdict, ToolReceipt

DEFAULT_SEQ_LEN: Final[int] = 192

_ACTION_FAMILY_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "write",
        re.compile(
            r"\bI\s+(?:(?:also|have|just|already|successfully)\s+)*(?:saved|wrote|written|created|updated|modified|edited)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "delete",
        re.compile(
            r"\bI\s+(?:(?:also|have|just|already|successfully)\s+)*(?:deleted|removed|erased|wiped|formatted)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exec",
        re.compile(
            r"\bI\s+(?:(?:also|have|just|already|successfully)\s+)*(?:executed|ran|installed|committed|pushed|killed|restarted)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "send",
        re.compile(
            r"\bI\s+(?:(?:also|have|just|already|successfully)\s+)*(?:sent|emailed|messaged|dispatched)\b",
            re.IGNORECASE,
        ),
    ),
)

_TOOL_FAMILY_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "write": ("write", "save", "create", "edit", "update", "note"),
    "delete": ("delete", "remove", "unlink", "erase", "wipe", "rm"),
    "exec": ("run", "exec", "bash", "shell", "cmd", "git", "install", "kill"),
    "send": ("send", "email", "mail", "message", "post"),
}

_HEDGE_EXEMPTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:if\s+I|would\s+have|could\s+have|cannot|can't|did\s+not|didn't|haven't|"
    r"have\s+not|unable\s+to|let\s+me\s+know\s+if\s+you\s+want\s+me\s+to)\b",
    re.IGNORECASE,
)


class ReceiptSupervisor:
    """Verifies assistant narration clauses against deterministic `ToolReceipt` records."""

    def __init__(
        self,
        model_dir: Path | str | None = None,
        *,
        device: str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self.available = False
        self.active_device = "DETERMINISTIC_CPU"
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
        except Exception:
            self.available = False
            self.active_device = "DETERMINISTIC_CPU"

    @staticmethod
    def _resolve_model_dir(model_dir: Path | str | None) -> Path | None:
        if model_dir is not None:
            return Path(model_dir)
        env_dir = os.environ.get("LUCCA_ACTION_CLAIM_MODEL_DIR")
        if env_dir:
            return Path(env_dir)
        for cand in (
            Path.cwd() / "models" / "action_claim_verifier_ov",
            Path(__file__).resolve().parents[4] / "models" / "action_claim_verifier_ov",
            Path(r"C:\ProjectLucca\models\action_claim_verifier_ov"),
        ):
            if (cand / "openvino_model.xml").exists():
                return cand
        return None

    def _detect_claimed_family(self, clause: str, user_prompt: str = "") -> str | None:
        if _HEDGE_EXEMPTION_RE.search(clause):
            return None
        for fam, pat in _ACTION_FAMILY_PATTERNS:
            if pat.search(clause):
                return fam
        if not self.available or self._tokenizer is None or self._infer_req is None:
            return None
        enc = (
            self._tokenizer.encode(user_prompt, clause)
            if user_prompt
            else self._tokenizer.encode(clause)
        )
        input_ids = np.array([enc.ids], dtype=np.int64)
        attention_mask = np.array([enc.attention_mask], dtype=np.int64)
        with self._lock:
            res = self._infer_req.infer({"input_ids": input_ids, "attention_mask": attention_mask})
            logits = np.asarray(list(res.values())[0], dtype=np.float64)[0]
        exp_l = np.exp(logits - np.max(logits))
        probs = exp_l / np.sum(exp_l)
        idx = int(np.argmax(probs))
        if idx in (3, 4) and float(probs[idx]) >= 0.70:
            return "any"
        return None

    @staticmethod
    def _receipt_supports_clause(clause: str, family: str, receipts: Sequence[ToolReceipt]) -> bool:
        ok_receipts = [r for r in receipts if r.ok]
        if not ok_receipts:
            return False
        cl_lower = clause.lower()
        fam_kws = _TOOL_FAMILY_KEYWORDS.get(family, ())
        for rcpt in ok_receipts:
            tool_l = rcpt.tool.lower()
            if fam_kws and not any(kw in tool_l for kw in fam_kws):
                continue
            if not rcpt.args:
                return True
            for val in rcpt.args.values():
                sval = str(val).strip().lower()
                if len(sval) >= 3 and sval in cl_lower:
                    return True
        return False

    def verify_narration(
        self,
        narration: str,
        receipts: Sequence[ToolReceipt] = (),
        *,
        user_prompt: str = "",
    ) -> ClauseSupervisionVerdict:
        t0 = time.perf_counter()
        clauses = split_into_clauses(narration)
        unsupported: list[str] = []
        for cl in clauses:
            fam = self._detect_claimed_family(cl, user_prompt=user_prompt)
            if fam is not None and not self._receipt_supports_clause(cl, fam, receipts):
                unsupported.append(cl)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return ClauseSupervisionVerdict(
            is_valid=len(unsupported) == 0,
            device=self.active_device,
            latency_ms=elapsed_ms,
            clauses_checked=len(clauses),
            unsupported_claims=unsupported,
        )
