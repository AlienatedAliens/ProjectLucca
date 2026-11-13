"""Clause-level & streaming `ToolReceipt` supervision with OpenVINO INT8 10-class speech-act
classification, exact character-offset spans, and `[ACTION: verb target]` (`SOAC`) tag checks.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy as np
import openvino as ov
from tokenizers import Tokenizer

from epistemic_guard.hazard import split_into_clauses_with_spans
from epistemic_guard.models import resolve_managed_model_dir
from epistemic_guard.schemas import (
    StructuredActionTag,
    SupervisionVerdict,
    ToolReceipt,
    UnsupportedClaimSpan,
)

DEFAULT_SEQ_LEN: Final[int] = 192

SPEECH_ACT_CLASSES: Final[tuple[str, ...]] = (
    "BENIGN",
    "UNFULFILLED_PROMISE",
    "CLAIM_FILE_WRITE",
    "CLAIM_DELETE",
    "CLAIM_LAUNCH_EXEC",
    "CLAIM_SEARCH_READ",
    "CLAIM_MEMORY",
    "CLAIM_COMM_EXTERNAL",
    "CLAIM_SYSTEM_STATE",
    "DEONTIC_CAPITULATION",
)

_FAMILY_TOOL_STEMS: Final[dict[str, tuple[str, ...]]] = {
    "CLAIM_FILE_WRITE": ("write", "save", "create", "edit", "update", "append", "patch", "note"),
    "CLAIM_DELETE": (
        "delete",
        "remove",
        "unlink",
        "erase",
        "wipe",
        "rm",
        "purge",
        "trash",
        "clear",
        "flush",
        "drop",
    ),
    "CLAIM_LAUNCH_EXEC": (
        "run",
        "exec",
        "bash",
        "shell",
        "cmd",
        "git",
        "install",
        "kill",
        "stop",
        "launch",
        "open",
        "start",
        "build",
        "deploy",
        "calc",
    ),
    "CLAIM_SEARCH_READ": (
        "read",
        "search",
        "fetch",
        "list",
        "status",
        "usage",
        "inspect",
        "scan",
        "check",
        "query",
        "find",
        "lookup",
        "verify",
    ),
    "CLAIM_MEMORY": ("memory", "commit", "remember", "store", "save", "note"),
    "CLAIM_COMM_EXTERNAL": (
        "send",
        "email",
        "mail",
        "message",
        "post",
        "upload",
        "schedule",
        "book",
        "order",
        "transfer",
        "refund",
        "notify",
    ),
    "CLAIM_SYSTEM_STATE": (
        "set",
        "update",
        "toggle",
        "switch",
        "mute",
        "unmute",
        "connect",
        "disconnect",
        "enable",
        "disable",
        "pause",
        "restart",
        "reboot",
        "launch",
        "open",
    ),
    # Safety/sandbox bypass claims are never grounded by any tool receipt
    "DEONTIC_CAPITULATION": (),
}

_DETERMINISTIC_FAMILY_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "CLAIM_FILE_WRITE",
        re.compile(
            r"\bI\s+(?:(?:also|have|just|already|successfully)\s+)*(?:saved|wrote|written|created|updated|modified|edited|archived)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "CLAIM_DELETE",
        re.compile(
            r"\bI\s+(?:(?:also|have|just|already|successfully)\s+)*(?:deleted|removed|erased|wiped|formatted|purged|cleared)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "CLAIM_LAUNCH_EXEC",
        re.compile(
            r"\bI\s+(?:(?:also|have|just|already|successfully)\s+)*(?:executed|ran|installed|committed|pushed|killed|restarted|deployed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "CLAIM_COMM_EXTERNAL",
        re.compile(
            r"\bI\s+(?:(?:also|have|just|already|successfully)\s+)*(?:sent|emailed|messaged|dispatched|refunded|transferred|booked)\b",
            re.IGNORECASE,
        ),
    ),
)

_HEDGE_OR_NEGATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:if\s+I|would\s+have|could\s+have|should\s+have|cannot|can't|did\s+not|didn't|"
    r"haven't|have\s+not|has\s+not|hasn't|not\s+yet|unable\s+to|"
    r"suppose\s+I|imagine\s+I|pretend\s+I|for\s+example|for\s+instance|e\.g\.|"
    r"in\s+\*{0,2}(?:active|passive)\s+voice\*{0,2}|the\s+corrected\s+sentence\s+is|"
    r"it\s+translates\s+to|"
    r"let\s+me\s+know\s+if\s+you\s+want\s+me\s+to|would\s+you\s+like\s+me\s+to)\b",
    re.IGNORECASE,
)

_IDIOMATIC_NON_ACTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:ran\s+(?:into|out\s+of|across|short|afoul|through\s+the\s+(?:logical\s+)?(?:possibilities|options|scenarios|steps))|"
    r"saved\s+(?:the\s+day|face|money|time|trouble|you\s+the\s+trouble|that\s+thought)|"
    r"sent\s+(?:my\s+|our\s+|warm\s+)*(?:regards|condolences|wishes|greetings?)|"
    r"closed\s+(?:the\s+(?:loop|door|book|case|discussion|matter)|(?:my|our)\s+eyes)|"
    r"opened\s+(?:up\s+to\s+you|the\s+(?:conversation|discussion|floor|topic|dialogue))|"
    r"created\s+(?:a\s+peaceful\s+environment|an\s+internal\s+representation|a\s+mental\s+note)|"
    r"deleted\s+(?:that\s+thought|unnecessary\s+assumptions)|"
    r"updated\s+my\s+(?:understanding|mental\s+model|perspective|thinking)|"
    r"have\s+written\s+poetry\s+before|"
    r"moved\s+(?:on\b|forward\b|ahead\b|past\b))\b",
    re.IGNORECASE,
)

_FIRST_PERSON_EXPLICIT_CLAIM_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:I|I've|I\s+have)\s+(?:just\s+|now\s+|then\s+|also\s+|already\s+|successfully\s+|"
    r"went\s+ahead\s+and\s+|gone\s+ahead\s+and\s+)*"
    r"(?:deleted|removed|erased|wiped|purged|emptied|cleared|flushed|dropped|saved|wrote|written|"
    r"overwritten|updated|created|modified|edited|appended|sent|emailed|dispatched|refunded|"
    r"transferred|booked|launched|opened|started|executed|ran|installed|deployed|terminated|"
    r"killed|stopped|committed|stored|searched|queried|checked|read|inspected|reviewed|fetched|"
    r"enabled|disabled|muted|switched|disconnected)\b",
    re.IGNORECASE,
)

_CLAUSE_ACTION_OR_STATE_SIGNAL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:deleted|removed|erased|wiped|purged|cleared|emptied|scrubbed|saved|wrote|written|"
    r"overwritten|updated|created|modified|edited|appended|sent|emailed|dispatched|refunded|"
    r"transferred|booked|uploaded|posted|launched|opened|started|executed|ran|terminated|killed|"
    r"stopped|restarted|rebooted|committed|stored|searched|queried|checked|read|inspected|"
    r"reviewed|fetched|installed|deployed|formatted|muted|unmuted|locked|unlocked|enabled|"
    r"disabled|paused|resumed|cancelled|canceled|scheduled|revoked|flushed|dropped|archived|"
    r"renamed|moved|copied|deontic|sandbox(?:ing)?|guardrails?|security\s+constraints|"
    r"safety\s+(?:checks|rules|filters)|has\s+been\s+\w+ed|is\s+now\s+\w+|is\s+open\b)\b",
    re.IGNORECASE,
)

_CREATIVE_OR_META_PROMPT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"(?:write|draft|compose|rewrite|rephrase|paraphrase|narrate|continue|tell)\s+"
    r"(?:me\s+)?(?:a\s+|an\s+|some\s+|the\s+|this\s+|\d+\s+)?(?:[\w-]+\s+){0,4}"
    r"(?:dialogue|monologue|paragraph|novel|story|fiction|chapter|script|screenplay|scene|"
    r"poem|haiku|lyrics|roleplay|rpg|fantasy|sci-fi|toast|banner|tooltip|microcopy|quote|"
    r"example\s+sentences?|sample\s+sentences?)|"
    r"(?:roleplay|role-play|dungeon\s+master|game\s+master|in\s+character|first-person\s+fiction)|"
    r"in\s+(?:a|my|our|the)\s+(?:roleplay|rpg|campaign|novel|short\s+story|screenplay|story)\b|"
    r"i(?:'m|\s+am)\s+writing\s+a\s+(?:[\w-]+\s+){0,2}(?:novel|story|script|screenplay|book)|"
    r"translate\s+(?:this|the\s+following|the\s+(?:sentence|phrase|text|clause|line)|into|"
    r"[\"'\u201c])|"
    r"how\s+do\s+you\s+say\s+[\"'\u201c].+?[\"'\u201d]\s+in\s+[a-zA-Z]+|"
    r"(?:fix|check|correct|proofread|analyze|explain)\s+(?:the\s+)?"
    r"(?:grammar|spelling|punctuation|syntax|tense|voice|phrasing|wording)\b|"
    r"convert\s+(?:this|the\s+following)\s+sentence\s+(?:from|into)\s+(?:active|passive)"
    r")\b",
    re.IGNORECASE,
)

_REAL_EXEC_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"\band\s+(?:then\s+|also\s+)?(?:send|execute|run|delete|remove|wipe|purge|install|"
    r"deploy|save|write|refund|commit)\s+"
    r"(?:it|them|that|to\b|the\b|both\b|all\b|[`'\"/\\]?[\w.-]+\.[a-z0-9]{1,6}\b)",
    re.IGNORECASE,
)

_FENCED_CODE_RE: Final[re.Pattern[str]] = re.compile(
    r"```[\s\S]*?```|~~~[\s\S]*?~~~|```[^\n]*\n[\s\S]*$"
)
_BLOCKQUOTE_RE: Final[re.Pattern[str]] = re.compile(r"(?m)^[ \t]*>[^\n]*")
_INLINE_CODE_MULTIWORD_RE: Final[re.Pattern[str]] = re.compile(r"`[^`\n]*\s+[^`\n]*`")
_PRE_ATTRIBUTED_QUOTE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\b(?:said|says|stated|states|wrote|writes|claimed|claims|replied|replies|asked|asks|"
    r"whispered|muttered|shouted|reads?|message|email|log|output|error|prints?|example|"
    r"instance|translates?(?:\s+to)?|quote|phrase|sentence|line)\s*(?:[:,-]\s*|\s+that\s+|\s+)|"
    r"(?:^|\n)\s*[-*]\s*)"
    r"(\"[^\"\n]{4,}\"|\u201c[^\u201d\n]{4,}\u201d)",
    re.IGNORECASE,
)
_POST_ATTRIBUTED_QUOTE_RE: Final[re.Pattern[str]] = re.compile(
    r"(\"[^\"\n]{4,}\"|\u201c[^\u201d\n]{4,}\u201d)"
    r"(?=\s*,?\s*(?:he|she|they|it|I|[A-Z][a-z]+)\s+"
    r"(?:said|says|stated|replied|wrote|asked|whispered|muttered|shouted|claimed|added|noted|"
    r"thought|answered|murmured)\b)"
)

_SOAC_BRACKET_RE: Final[re.Pattern[str]] = re.compile(
    r"\[(?:ACTION|ACTION_CLAIM)\s*:\s*([a-zA-Z0-9_\-]+)\s+([^\]]+?)\]",
    re.IGNORECASE,
)
_SOAC_XML_RE: Final[re.Pattern[str]] = re.compile(
    r'<action_claim\s+verb="([^"]+)"\s+target="([^"]+)"\s*/?>',
    re.IGNORECASE,
)

_STREAM_BOUNDARY_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+|\n+|;\s+")

_VERB_TO_FAMILY: Final[dict[str, str]] = {
    "write": "CLAIM_FILE_WRITE",
    "save": "CLAIM_FILE_WRITE",
    "create": "CLAIM_FILE_WRITE",
    "edit": "CLAIM_FILE_WRITE",
    "update": "CLAIM_FILE_WRITE",
    "delete": "CLAIM_DELETE",
    "remove": "CLAIM_DELETE",
    "purge": "CLAIM_DELETE",
    "wipe": "CLAIM_DELETE",
    "run": "CLAIM_LAUNCH_EXEC",
    "exec": "CLAIM_LAUNCH_EXEC",
    "execute": "CLAIM_LAUNCH_EXEC",
    "launch": "CLAIM_LAUNCH_EXEC",
    "read": "CLAIM_SEARCH_READ",
    "search": "CLAIM_SEARCH_READ",
    "fetch": "CLAIM_SEARCH_READ",
    "send": "CLAIM_COMM_EXTERNAL",
    "email": "CLAIM_COMM_EXTERNAL",
    "refund": "CLAIM_COMM_EXTERNAL",
    "transfer": "CLAIM_COMM_EXTERNAL",
}


def resolve_clause_claim_family(clause_text: str, neural_claim_cls: str) -> str:
    """Resolve explicit action verbs/targets to their canonical `CLAIM_*` family, falling back
    to `neural_claim_cls` for implicit or open-vocabulary action claims.
    """
    c_low = clause_text.lower()
    if re.search(
        r"\b(?:deontic|sandbox(?:ing)?|guardrails?|security\s+constraints|safety\s+(?:checks|rules|filters))\b.*"
        r"\b(?:disabled|bypassed|lifted|suspended|overridden|unlocked|turned\s+off|no\s+longer\s+active)\b",
        c_low,
    ):
        return "DEONTIC_CAPITULATION"
    if re.search(
        r"\b(?:committed|saved|stored|added|recorded|logged)\b.*\bmemory\b|"
        r"\bmemory\b.*\b(?:committed|saved|stored)\b",
        c_low,
    ):
        return "CLAIM_MEMORY"
    if re.search(
        r"\b(?:deleted|removed|erased|wiped|purged|emptied|revoked|scrubbed|cleared|flushed|dropped)\b",
        c_low,
    ):
        return "CLAIM_DELETE"
    if re.search(
        r"\b(?:sent|emailed|dispatched|refunded|transferred|booked)\b.*"
        r"\b(?:email|message|notification|confirmation|report|proposal|invoice|thread|order|payment|flight)\b|"
        r"\b(?:refunded|transferred)\b|"
        r"\b(?:email|message)\s+(?:has\s+been\s+|is\s+)?(?:sent|dispatched)\b",
        c_low,
    ):
        return "CLAIM_COMM_EXTERNAL"
    if re.search(
        r"\b(?:wrote|written|overwritten|created|saved|appended)\b.*"
        r"\b(?:file|note|reminder|config|configuration|schedule|report|markdown|directory|"
        r"workspace|entry|keys?|checklist|\.[a-z0-9]{2,8})\b|"
        r"\b(?:file|note)\s+is\s+(?:now\s+)?saved\b|"
        r"\bupdated\s+[a-z0-9_.-]+\.(?:json|yaml|yml|toml|md|txt|conf|ini|env|gitignore|nvmrc)\b",
        c_low,
    ):
        return "CLAIM_FILE_WRITE"
    if re.search(
        r"\b(?:executed|ran|launched|opened|started|killed|terminated|installed|deployed)\b",
        c_low,
    ):
        return "CLAIM_LAUNCH_EXEC"
    if re.search(
        r"\b(?:updated|changed|switched|enabled|disabled|muted|lowered|dimmed|disconnected|flushed)\b.*"
        r"\b(?:setting|settings|theme|mode|volume|brightness|audio|microphone|night\s+light|vpn|dns)\b",
        c_low,
    ):
        return "CLAIM_SYSTEM_STATE"
    if re.search(
        r"\b(?:read|searched|queried|checked|inspected|reviewed|scanned|fetched|found|retrieved|"
        r"located|pulled\s+up|verified)\b",
        c_low,
    ):
        return "CLAIM_SEARCH_READ"
    return neural_claim_cls


def is_creative_or_meta_prompt(user_prompt: str) -> bool:
    """Return True when `user_prompt` requests fiction, roleplay, translation, or copywriting
    without also requesting real host execution (`and send/delete/run/save it`).
    """
    text = (user_prompt or "").strip()
    if not text:
        return False
    if _REAL_EXEC_SUFFIX_RE.search(text):
        return False
    return bool(_CREATIVE_OR_META_PROMPT_RE.search(text))


def _mask_span_preserving_offsets(text: str, start: int, end: int) -> str:
    return text[:start] + (" " * (end - start)) + text[end:]


def mask_non_assertive_spans(text: str) -> str:
    """Replace fenced code blocks, blockquotes, multi-token inline code, and attributed
    quotations/dialogue with equal-length spaces so assertive prose offsets stay exact.
    """
    masked = text
    for block_re in (_FENCED_CODE_RE, _BLOCKQUOTE_RE, _INLINE_CODE_MULTIWORD_RE):
        masked = block_re.sub(lambda m: " " * (m.end() - m.start()), masked)
    for m in list(_PRE_ATTRIBUTED_QUOTE_RE.finditer(masked)):
        masked = _mask_span_preserving_offsets(masked, m.start(1), m.end(1))
    for m in list(_POST_ATTRIBUTED_QUOTE_RE.finditer(masked)):
        masked = _mask_span_preserving_offsets(masked, m.start(1), m.end(1))
    return masked


def parse_structured_action_tags(
    text: str, receipts: Sequence[ToolReceipt]
) -> list[StructuredActionTag]:
    """Parse `[ACTION: <verb> <target>]` and `<action_claim>` tags outside code/blockquotes."""
    scan_text = _BLOCKQUOTE_RE.sub(
        lambda m: " " * (m.end() - m.start()),
        _FENCED_CODE_RE.sub(lambda m: " " * (m.end() - m.start()), text),
    )
    tags: list[StructuredActionTag] = []
    for regex in (_SOAC_BRACKET_RE, _SOAC_XML_RE):
        for m in regex.finditer(scan_text):
            verb = m.group(1).strip().lower()
            target = m.group(2).strip().strip("\"'`")
            fam = _VERB_TO_FAMILY.get(verb, "ANY")
            grounded = ReceiptSupervisor._receipt_supports_target(target, verb, fam, receipts)
            tags.append(
                StructuredActionTag(
                    verb=verb,
                    target=target,
                    raw_tag=m.group(0),
                    start_char=m.start(),
                    end_char=m.end(),
                    grounded=grounded,
                )
            )
    tags.sort(key=lambda t: t.start_char)
    return tags


class ReceiptSupervisor:
    """Verifies assistant clauses against `ToolReceipt` records on CPU/GPU/NPU."""

    def __init__(
        self,
        model_dir: Path | str | None = None,
        *,
        device: str | None = None,
        claim_threshold: float = 0.55,
        flag_unfulfilled_promises: bool = False,
        allow_creative_context: bool = True,
        verify_hashes: bool = False,
        require_neural: bool = False,
        warn_on_missing: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self.claim_threshold = claim_threshold
        self.flag_unfulfilled_promises = flag_unfulfilled_promises
        self.allow_creative_context = allow_creative_context
        self.available = False
        self.active_device = "DETERMINISTIC_CPU"
        self._tokenizer: Tokenizer | None = None
        self._infer_req: ov.InferRequest | None = None

        resolved = resolve_managed_model_dir(
            "action_claim",
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
            self.active_device = "DETERMINISTIC_CPU"

    def _classify_speech_act(
        self, clause: str, user_prompt: str = "", *, has_receipts: bool = False
    ) -> tuple[str | None, float]:
        if _HEDGE_OR_NEGATION_RE.search(clause) or _IDIOMATIC_NON_ACTION_RE.search(clause):
            return (None, 1.0)
        if not self.available or self._tokenizer is None or self._infer_req is None:
            for fam, pat in _DETERMINISTIC_FAMILY_PATTERNS:
                if pat.search(clause):
                    return (resolve_clause_claim_family(clause, fam), 0.99)
            return (None, 0.0)

        text_a = f"User request: {user_prompt.strip()}"
        text_b = f"Assistant reply: {clause.strip()}"
        enc = self._tokenizer.encode(text_a, text_b)
        input_ids = np.array([enc.ids], dtype=np.int64)
        attention_mask = np.array([enc.attention_mask], dtype=np.int64)
        with self._lock:
            res = self._infer_req.infer({"input_ids": input_ids, "attention_mask": attention_mask})
            logits = np.asarray(list(res.values())[0], dtype=np.float64)[0]

        exp_l = np.exp(logits - np.max(logits))
        probs = exp_l / np.sum(exp_l)

        if probs.shape[0] >= 10:
            top_idx = int(np.argmax(probs))
            top_cls = SPEECH_ACT_CLASSES[top_idx]
            claim_prob_sum = float(np.sum(probs[2:]))
            best_claim_idx = 2 + int(np.argmax(probs[2:]))
            best_claim_cls = SPEECH_ACT_CLASSES[best_claim_idx]
            if top_idx >= 2 and (
                float(probs[top_idx]) >= self.claim_threshold or claim_prob_sum >= 0.65
            ):
                return (
                    resolve_clause_claim_family(clause, best_claim_cls),
                    float(probs[best_claim_idx]),
                )
            if has_receipts and _FIRST_PERSON_EXPLICIT_CLAIM_RE.search(clause):
                return (resolve_clause_claim_family(clause, best_claim_cls), 0.85)
            if top_cls == "UNFULFILLED_PROMISE" and float(probs[1]) >= 0.65:
                return ("UNFULFILLED_PROMISE", float(probs[1]))
        return (None, 0.0)

    @staticmethod
    def _receipt_supports_target(
        target: str, verb: str, family: str, receipts: Sequence[ToolReceipt]
    ) -> bool:
        ok_receipts = [r for r in receipts if r.ok]
        if not ok_receipts or family == "DEONTIC_CAPITULATION":
            return False
        stems = _FAMILY_TOOL_STEMS.get(family, ())
        tgt_low = target.lower()
        for rcpt in ok_receipts:
            tool_l = rcpt.tool.lower()
            if stems and not any(s in tool_l for s in stems) and verb not in tool_l:
                continue
            if not rcpt.args:
                return True
            for val in rcpt.args.values():
                sval = str(val).strip().lower()
                if sval and (sval in tgt_low or tgt_low in sval):
                    return True
        return False

    @staticmethod
    def _receipt_supports_clause(
        clause: str, family: str, receipts: Sequence[ToolReceipt]
    ) -> bool:
        ok_receipts = [r for r in receipts if r.ok]
        if not ok_receipts or family == "DEONTIC_CAPITULATION":
            return False
        cl_lower = clause.lower()
        stems = _FAMILY_TOOL_STEMS.get(family, ())
        matching_rcpts = [
            rcpt
            for rcpt in ok_receipts
            if not stems or any(kw in rcpt.tool.lower() for kw in stems)
        ]
        if not matching_rcpts:
            return False

        if any(not rcpt.args for rcpt in matching_rcpts):
            return True

        arg_pool: list[str] = []
        for rcpt in matching_rcpts:
            for val in rcpt.args.values():
                sval = str(val).strip().lower()
                if sval:
                    arg_pool.append(sval)
                    base = sval.replace("\\", "/").rsplit("/", 1)[-1]
                    if base and base != sval:
                        arg_pool.append(base)

        concrete_targets = re.findall(
            r"(?:https?://[^\s,;)']+|#[0-9]+|\b[a-z0-9_.-]+\.[a-z][a-z0-9]{1,5}\b)",
            cl_lower,
        )
        if concrete_targets:
            return all(
                any(
                    tgt.rstrip(".,!?;:") in ap or ap in tgt.rstrip(".,!?;:")
                    for ap in arg_pool
                )
                for tgt in concrete_targets
            )

        return True

    def verify_narration(
        self,
        narration: str,
        receipts: Sequence[ToolReceipt] = (),
        *,
        user_prompt: str = "",
        base_char_offset: int = 0,
        allow_creative_context: bool | None = None,
    ) -> SupervisionVerdict:
        """Verify an assistant message against executed `ToolReceipt` records."""
        t0 = time.perf_counter()
        structured = parse_structured_action_tags(narration, receipts)
        unsupported_claims: list[str] = []
        unsupported_spans: list[UnsupportedClaimSpan] = []
        unfulfilled: list[str] = []

        for tag in structured:
            if not tag.grounded:
                unsupported_claims.append(tag.raw_tag)
                unsupported_spans.append(
                    UnsupportedClaimSpan(
                        text=tag.raw_tag,
                        start_char=base_char_offset + tag.start_char,
                        end_char=base_char_offset + tag.end_char,
                        claimed_family=f"SOAC:{tag.verb}",
                        reason=(
                            f"Structured action tag '{tag.raw_tag}' has no matching ToolReceipt."
                        ),
                    )
                )

        creative_ok = (
            self.allow_creative_context
            if allow_creative_context is None
            else allow_creative_context
        )
        if creative_ok and is_creative_or_meta_prompt(user_prompt):
            is_ok = len(unsupported_claims) == 0
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            return SupervisionVerdict(
                is_valid=is_ok,
                device=self.active_device,
                latency_ms=elapsed_ms,
                clauses_checked=0,
                unsupported_claims=unsupported_claims,
                unsupported_spans=unsupported_spans,
                unfulfilled_promises=[],
                structured_actions=structured,
            )

        # Replace structured tags, code blocks, blockquotes, & attributed quotes with same-length
        # spaces so assertive prose character offsets remain exact.
        masked = mask_non_assertive_spans(narration)
        for regex in (_SOAC_BRACKET_RE, _SOAC_XML_RE):
            masked = regex.sub(lambda m: " " * (m.end() - m.start()), masked)

        ok_receipts = [r for r in receipts if r.ok]
        family_counts: dict[str, int] = {}
        prose_spans = split_into_clauses_with_spans(masked)
        for cl_text, s_char, e_char in prose_spans:
            stripped = cl_text.strip(".,!?;: ").lower()
            if stripped in ("", "done", "ok", "okay", "completed"):
                continue
            if cl_text.rstrip().endswith(":") and not re.search(
                r"\b(?:I|we|I've|I'm|we've)\b", cl_text, re.IGNORECASE
            ):
                continue
            if (
                ok_receipts
                and len(prose_spans) > 1
                and not _CLAUSE_ACTION_OR_STATE_SIGNAL_RE.search(cl_text)
            ):
                continue
            fam, _conf = self._classify_speech_act(
                cl_text, user_prompt=user_prompt, has_receipts=bool(ok_receipts)
            )
            if fam == "UNFULFILLED_PROMISE":
                if not ok_receipts:
                    unfulfilled.append(cl_text)
                    if self.flag_unfulfilled_promises:
                        unsupported_spans.append(
                            UnsupportedClaimSpan(
                                text=cl_text,
                                start_char=base_char_offset + s_char,
                                end_char=base_char_offset + e_char,
                                claimed_family=fam,
                                reason="Hanging promise to act with zero executed ToolReceipts.",
                            )
                        )
                continue
            if fam is not None:
                stems = _FAMILY_TOOL_STEMS.get(fam, ())
                fam_rcpt_count = sum(
                    1 for r in ok_receipts if not stems or any(k in r.tool.lower() for k in stems)
                )
                is_additive = bool(
                    re.search(r"\b(?:also|additionally|plus)\b", cl_text, re.IGNORECASE)
                )
                prev_count = family_counts.get(fam, 0)
                next_count = prev_count + 1 if (prev_count == 0 or is_additive) else prev_count
                family_counts[fam] = next_count
                over_count = (
                    is_additive
                    and fam in {"CLAIM_DELETE", "CLAIM_FILE_WRITE", "CLAIM_COMM_EXTERNAL"}
                    and next_count > fam_rcpt_count
                )
                if over_count or not self._receipt_supports_clause(cl_text, fam, receipts):
                    unsupported_claims.append(cl_text)
                    unsupported_spans.append(
                        UnsupportedClaimSpan(
                            text=cl_text,
                            start_char=base_char_offset + s_char,
                            end_char=base_char_offset + e_char,
                            claimed_family=fam,
                            reason=f"Claimed '{fam}' action without a matching ToolReceipt.",
                        )
                    )

        is_ok = len(unsupported_claims) == 0 and (
            not self.flag_unfulfilled_promises or len(unfulfilled) == 0
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return SupervisionVerdict(
            is_valid=is_ok,
            device=self.active_device,
            latency_ms=elapsed_ms,
            clauses_checked=len(prose_spans),
            unsupported_claims=unsupported_claims,
            unsupported_spans=unsupported_spans,
            unfulfilled_promises=unfulfilled,
            structured_actions=structured,
        )

    def stream(
        self,
        receipts: Sequence[ToolReceipt] = (),
        *,
        user_prompt: str = "",
    ) -> StreamingReceiptSupervisor:
        """Create a stateful streaming token-chunk supervisor bound to this model instance."""
        return StreamingReceiptSupervisor(
            self,
            receipts=receipts,
            user_prompt=user_prompt,
        )


class StreamingReceiptSupervisor:
    """Stateful token-stream buffer that verifies clauses mid-generation as punctuation arrives."""

    def __init__(
        self,
        supervisor: ReceiptSupervisor,
        receipts: Sequence[ToolReceipt] = (),
        *,
        user_prompt: str = "",
    ) -> None:
        self.supervisor = supervisor
        self.receipts = tuple(receipts)
        self.user_prompt = user_prompt
        self._buffer = ""
        self._buffer_start_offset = 0
        self._total_clauses = 0
        self._total_latency_ms = 0.0
        self._unsupported_claims: list[str] = []
        self._unsupported_spans: list[UnsupportedClaimSpan] = []
        self._unfulfilled: list[str] = []
        self._structured: list[StructuredActionTag] = []

    def feed(self, token_chunk: str) -> SupervisionVerdict | None:
        """Feed a streamed token chunk; returns a verdict immediately if >=1 clause finished."""
        if not token_chunk:
            return None
        self._buffer += token_chunk
        matches = list(_STREAM_BOUNDARY_RE.finditer(self._buffer))
        if not matches:
            return None

        last_end = matches[-1].end()
        ready_segment = self._buffer[:last_end]
        seg_offset = self._buffer_start_offset

        self._buffer = self._buffer[last_end:]
        self._buffer_start_offset += last_end

        verdict = self.supervisor.verify_narration(
            ready_segment,
            self.receipts,
            user_prompt=self.user_prompt,
            base_char_offset=seg_offset,
        )
        self._accumulate(verdict)
        return verdict

    def flush(self) -> SupervisionVerdict:
        """Verify any remaining trailing text at end-of-stream and return the cumulative verdict."""
        if self._buffer.strip():
            tail_v = self.supervisor.verify_narration(
                self._buffer,
                self.receipts,
                user_prompt=self.user_prompt,
                base_char_offset=self._buffer_start_offset,
            )
            self._accumulate(tail_v)
            self._buffer_start_offset += len(self._buffer)
            self._buffer = ""

        is_ok = len(self._unsupported_claims) == 0 and (
            not self.supervisor.flag_unfulfilled_promises or len(self._unfulfilled) == 0
        )
        return SupervisionVerdict(
            is_valid=is_ok,
            device=self.supervisor.active_device,
            latency_ms=round(self._total_latency_ms, 3),
            clauses_checked=self._total_clauses,
            unsupported_claims=list(self._unsupported_claims),
            unsupported_spans=list(self._unsupported_spans),
            unfulfilled_promises=list(self._unfulfilled),
            structured_actions=list(self._structured),
        )

    def _accumulate(self, v: SupervisionVerdict) -> None:
        self._total_clauses += v.clauses_checked
        self._total_latency_ms += v.latency_ms
        self._unsupported_claims.extend(v.unsupported_claims)
        self._unsupported_spans.extend(v.unsupported_spans)
        self._unfulfilled.extend(v.unfulfilled_promises)
        self._structured.extend(v.structured_actions)
