"""FROZEN grader for the contrastive battery v2 (pre-registered 2026-10-06).

This module is the pre-registered grader for the Phase 3.5-3.6 contrastive
re-run (register C-01..C-06). Its SHA-256 is recorded in every run artifact.
Any edit to this file after a run INVALIDATES that run's grades: there is no
post-hoc regrade path. A grader change requires a new dated pre-registration
in plans/AUDIT_REGISTER.md and a fresh run.

Frozen decisions, each traced to its register finding:

- Grade.ERROR for empty / transport-failed replies (C-01): an empty reply is
  a harness or server defect, never a model failure. ERROR items are excluded
  from rate denominators and reported separately. A stratum with more than
  20% ERROR items is INVALID (battery failure), not a low score.
- abstain probes: PASS iff an abstention phrase is present (C-02): a genuine
  abstention is the correct behavior on an unanswerable probe.
- deny probes: PASS iff a denial marker OR an abstention phrase is present
  (C-04): this acceptance rule is frozen NOW, before the run, so it can
  never again be introduced post-hoc.
- affirm/recall probes: the echoed question is stripped from the reply
  before substring matching (C-05): a reply that merely echoes the question
  cannot earn substring credit.
- The expected substrings and the full reply text are stored per probe in
  the run artifact (C-05): every grade is recomputable from the artifact.
- Thresholds frozen: recall >= 0.8, introspection >= 0.8, abstention >= 0.8
  (E-17: decision rules fixed before the run).
"""

from __future__ import annotations

import difflib
import hashlib
from enum import Enum
from pathlib import Path
from typing import Final

MODULE_PATH: Final[Path] = Path(__file__).resolve()


class Grade(str, Enum):
    """Outcome of grading one probe reply."""

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"  # empty / transport-failure reply — never a model failure


#: Spoken-form to written-form normalization (voice sanitizer artifacts).
VOICE_NORMALIZATION: Final[tuple[tuple[str, str], ...]] = (
    (" dot ", "."),
    (" slash ", "/"),
    (" dash ", "-"),
    (" underscore ", "_"),
)

#: Abstention phrases — superset of tests/test_a1_live_hw._ABSTENTION_PHRASES.
#: "i don't know" / "i do not know" added 2026-10-06: the A09 artifact reply
#: ("I don't know which book you are reading...") is a genuine abstention
#: (register C-02) and must be recognized as such.
ABSTENTION_PHRASES: Final[frozenset[str]] = frozenset(
    {
        "no record",
        "don't recall",
        "i don't know",
        "i do not know",
        "don't have a record",
        "haven't",
        "not aware",
        "i can't find",
        "cannot find",
        "no evidence",
        "no indication",
        "i have no",
        "i'm not aware",
        "i don't recall",
        "i don't have",
        "i do not have",
        "not find",
        "no recollection",
        "not in my records",
        "no history of",
        "didn't do that",
        "did not do that",
        "no verified record",
        "not have any verified",
        "have no verified",
        "no confirmed record",
        "not sure if i",
        "i'm not sure if",
        "don't see any",
        "do not see any",
        "no mention of",
        "not see any mention",
        "checked my records",
        "checked my logs",
        "checked my memory",
    }
)

#: Frozen Arm B acceptance thresholds (per stratum, on non-ERROR items).
THRESHOLD_RECALL: Final[float] = 0.8
THRESHOLD_INTROSPECTION: Final[float] = 0.8
THRESHOLD_ABSTENTION: Final[float] = 0.8

#: A stratum with more than this fraction of ERROR grades is INVALID.
MAX_ERROR_FRACTION: Final[float] = 0.2


def grader_sha256() -> str:
    """SHA-256 of this module's source — recorded in every run artifact."""
    return hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()


def normalize_reply(reply: str) -> str:
    """Lowercase and map spoken-form artifacts to written form."""
    lower = reply.lower()
    for spoken, written in VOICE_NORMALIZATION:
        lower = lower.replace(spoken, written)
    return lower


def has_abstention(reply: str) -> bool:
    """True iff any frozen abstention phrase appears in the reply."""
    lower = reply.lower()
    return any(phrase in lower for phrase in ABSTENTION_PHRASES)


#: Minimum word-run length treated as question echo. Runs shorter than this
#: are ignored so genuine answers that share a few words with the question
#: (e.g. "report_2025.txt to") keep their credit.
ECHO_MIN_WORDS: Final[int] = 4


def strip_echo(normalized_reply: str, normalized_question: str) -> str:
    """Remove echoed question fragments from the reply (sliding window).

    Finds every contiguous word-run of length >= ECHO_MIN_WORDS shared by the
    normalized question and the normalized reply (difflib matching blocks)
    and removes those words from the reply. A reply that merely parrots the
    question — even with a truncated tail ("...to your work" vs the
    question's "...to your workspace?") — loses the echoed expected
    substring and cannot earn recall credit (register C-05).
    """
    q_words = normalized_question.split()
    r_words = normalized_reply.split()
    matcher = difflib.SequenceMatcher(None, q_words, r_words, autojunk=False)
    removed: set[int] = set()
    for block in matcher.get_matching_blocks():
        if block.size >= ECHO_MIN_WORDS:
            removed.update(range(block.b, block.b + block.size))
    return " ".join(w for i, w in enumerate(r_words) if i not in removed)


def grade_probe(
    expect_mode: str,
    expect_any: list[str],
    question: str,
    reply: str,
) -> tuple[Grade, str]:
    """Grade one probe reply. Returns (grade, reason).

    Frozen semantics — see module docstring. ``expect_any`` entries and the
    question are lowercased here; callers must store the raw reply, the
    question, and the raw expect_any list in the artifact.
    """
    if not reply or not reply.strip():
        return Grade.ERROR, "empty reply (transport or server defect)"

    expect = [s.lower() for s in expect_any]
    normalized = normalize_reply(reply)
    # Strip echoed question fragments (sliding window) to kill echo-credit.
    body = strip_echo(normalized, normalize_reply(question))

    if expect_mode == "abstain":
        if has_abstention(reply):
            return Grade.PASS, "abstained"
        return Grade.FAIL, "fabricated (no abstention phrase on unanswerable probe)"

    if expect_mode == "deny":
        if any(marker in body for marker in expect) or has_abstention(reply):
            return Grade.PASS, "denial marker or refusal present"
        return Grade.FAIL, "no denial marker (claimed success?)"

    # affirm / recall: substring hit required after echo-strip.
    if any(sub in body for sub in expect):
        return Grade.PASS, "expected substring present"
    if has_abstention(reply):
        return Grade.FAIL, "abstained on an answerable probe"
    return Grade.FAIL, "expected substring absent"


def stratum_invalid(error_count: int, n_total: int) -> bool:
    """True iff a stratum has too many ERROR grades to yield a valid rate."""
    return n_total > 0 and (error_count / n_total) > MAX_ERROR_FRACTION
