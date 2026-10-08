"""
Project Lucca — Autobiographical Memory Commit Service
Spec D-MEM-04, WO-9, WO-17, WO-18b (F-ARCH-103)

Extracted from Orchestrator: handles all autobiographical and capability provenance
memory commits, passive fact extraction, and assistant belief formation.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Final

import structlog
import ulid

from lucca.core.clock import SystemClock
from lucca.core.schemas import Provenance, SignedPayload, UnsignedPayload, VerifierLabel
from lucca.core.signer_factory import SignerFactory
from lucca.core.trace import TurnTrace
from lucca.memory.extraction import FactExtractor
from lucca.ports import ClockPort, MemoryStorePort, SemanticVerifierPort

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)

STANCE_MARKERS: tuple[str, ...] = (
    "i think",
    "i believe",
    "in my view",
    "i prefer",
    "my opinion",
)


def _extract_stance_topic(text: str) -> str:
    """Extracts candidate topic string from a first-person stance utterance (Spec §7, WP-2)."""
    lower = text.lower()
    for marker in STANCE_MARKERS:
        if marker in lower:
            idx = lower.find(marker)
            sub = text[idx + len(marker) :].strip(" ,:.-")
            if sub:
                clause = re.split(r"[.!?;\n]+", sub)[0].strip()
                if clause:
                    return clause[:40].strip()
    return text[:40].strip()


_DEMONYMS: Final[frozenset[str]] = frozenset(
    {
        "afghan",
        "albanian",
        "algerian",
        "american",
        "andorran",
        "angolan",
        "argentine",
        "argentinian",
        "armenian",
        "australian",
        "austrian",
        "azerbaijani",
        "bahamian",
        "bahraini",
        "bangladeshi",
        "barbadian",
        "belarusian",
        "belgian",
        "belizean",
        "beninese",
        "bhutanese",
        "bolivian",
        "bosnian",
        "botswanan",
        "brazilian",
        "british",
        "bruneian",
        "bulgarian",
        "burkinabe",
        "burmese",
        "burundian",
        "cambodian",
        "cameroonian",
        "canadian",
        "cape verdean",
        "central african",
        "chadian",
        "chilean",
        "chinese",
        "colombian",
        "comoran",
        "congolese",
        "costa rican",
        "croatian",
        "cuban",
        "cypriot",
        "czech",
        "dane",
        "danish",
        "djiboutian",
        "dominican",
        "dutch",
        "east timorese",
        "ecuadorian",
        "egyptian",
        "emirati",
        "equatorial guinean",
        "eritrean",
        "estonian",
        "ethiopian",
        "fijian",
        "filipino",
        "finnish",
        "french",
        "gabonese",
        "gambian",
        "georgian",
        "german",
        "ghanaian",
        "greek",
        "grenadian",
        "guatemalan",
        "guinean",
        "guyanese",
        "haitian",
        "honduran",
        "hungarian",
        "icelandic",
        "indian",
        "indonesian",
        "iranian",
        "iraqi",
        "irish",
        "israeli",
        "italian",
        "ivorian",
        "jamaican",
        "japanese",
        "jordanian",
        "kazakhstani",
        "kenyan",
        "kuwaiti",
        "kyrgyz",
        "laotian",
        "latvian",
        "lebanese",
        "liberian",
        "libyan",
        "liechtensteiner",
        "lithuanian",
        "luxembourgish",
        "macedonian",
        "malagasy",
        "malawian",
        "malaysian",
        "maldivian",
        "malian",
        "maltese",
        "mauritanian",
        "mauritian",
        "mexican",
        "micronesian",
        "moldovan",
        "monacan",
        "mongolian",
        "montenegrin",
        "moroccan",
        "mozambican",
        "namibian",
        "nauruan",
        "nepalese",
        "new zealander",
        "kiwi",
        "nicaraguan",
        "nigerian",
        "nigerien",
        "north korean",
        "norwegian",
        "omani",
        "pakistani",
        "palauan",
        "palestinian",
        "panamanian",
        "papua new guinean",
        "paraguayan",
        "peruvian",
        "polish",
        "portuguese",
        "qatari",
        "romanian",
        "russian",
        "rwandan",
        "saint lucian",
        "salvadoran",
        "samoan",
        "saudi",
        "saudi arabian",
        "scottish",
        "senegalese",
        "serbian",
        "seychellois",
        "sierra leonean",
        "singaporean",
        "slovak",
        "slovene",
        "slovenian",
        "somali",
        "south african",
        "south korean",
        "spanish",
        "sri lankan",
        "sudanese",
        "surinamese",
        "swazi",
        "swedish",
        "swiss",
        "syrian",
        "taiwanese",
        "tajik",
        "tanzanian",
        "thai",
        "togolese",
        "tongan",
        "trinidadian",
        "tunisian",
        "turkish",
        "turkmen",
        "tuvaluan",
        "ugandan",
        "ukrainian",
        "uruguayan",
        "uzbek",
        "vanuatuan",
        "venezuelan",
        "vietnamese",
        "welsh",
        "yemeni",
        "zambian",
        "zimbabwean",
    }
)

_REPORTED_SPEECH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:he\s+said|she\s+told|they\s+said|my\s+friend\s+said|quote)\b",
    re.IGNORECASE,
)

_NEGATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:not|n't|never|no\s+longer)\b",
    re.IGNORECASE,
)

# WO-9 A3 & WO-17 Phase 2: passive fact extraction — deterministic, high-precision patterns.
# Candidates are re-validated by FactExtractor verbatim-quote grounding before
# signing, so a pattern can only ever produce facts the user literally said.
_PASSIVE_FACT_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "is_named",
        re.compile(
            r"\b(?:my name is|call me|name's)\s+([A-Za-z][A-Za-z\-']{1,30})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "lives_in",
        re.compile(
            r"\b(?:i live in|i moved to|i've moved to|i relocated to)\s+"
            r"([A-Za-z][A-Za-z\s\-']{1,40}?)"
            r"(?:\s+(?:last|this|next)\s+\w+|\s+recently|\s+now)?(?:[.,!?;]|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "works_at",
        re.compile(
            r"\bi work (?:at|for)\s+([A-Za-z][A-Za-z\s\-&']{1,40}?)(?:[.,!?;]|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "nationality_is",
        re.compile(
            r"\b(?:i am|i'm)\s+([a-z][a-z\-']{2,30})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "origin_is",
        re.compile(
            r"\b(?:i'm from|i am from|originally from)\s+([A-Za-z\s\-']{2,40}?)(?:[.,!?;]|$)",
            re.IGNORECASE,
        ),
    ),
)

# Hypothetical / counterfactual framing must never produce facts (the A1
# fixture "If I told you my name was Sean" is the canonical negative).
_HYPOTHETICAL_MARKERS: Final[tuple[str, ...]] = (
    "if i told you",
    "if i said",
    "if i say",
    "if my name",
    "suppose",
    "what if",
    "imagine",
    "let's say",
    "lets say",
    "hypothetically",
    "pretend",
)


def _sentence_containing(text: str, pos: int) -> str:
    """Returns the sentence of `text` containing character offset `pos`."""
    start = max(text.rfind(".", 0, pos), text.rfind("!", 0, pos), text.rfind("?", 0, pos)) + 1
    ends = [i for i in (text.find(".", pos), text.find("!", pos), text.find("?", pos)) if i != -1]
    end = min(ends) if ends else len(text) - 1
    sentence = text[start : end + 1].strip()
    return sentence if sentence else text[pos : pos + 200].strip()

_INTERROGATIVE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:who|what|when|where|why|how|which|whose|whom|can|could|should|"
    r"would|will|do|does|did|is|are|was|were|have|has|had|may|might|must|"
    r"tell\s+me|give\s+me|show\s+me|list|name)\b.*\?\s*$",
    re.IGNORECASE | re.DOTALL,
)

_INTERROGATIVE_OPENER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:who|what|when|where|why|how|which|whose|whom|can|could|should|"
    r"would|will|do|does|did|is|are|was|were|have|has|had|may|might|must|so)\b",
    re.IGNORECASE,
)

_LOCATION_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "though",
        "not",
        "no",
        "never",
        "nobody",
        "none",
        "really",
        "actually",
        "just",
    }
)

class MemoryCommitService:
    """Encapsulates memory commit operations for Orchestrator (F-ARCH-103, WO-18b)."""

    def __init__(
        self,
        memory_store: MemoryStorePort | None,
        signer_factory: SignerFactory,
        clock: ClockPort | None = None,
        orchestrator: Orchestrator | None = None,
        verifier: SemanticVerifierPort | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.signer_factory = signer_factory
        self.clock: ClockPort = clock or SystemClock()
        self._orchestrator = orchestrator
        self.verifier = verifier
        self._fact_extractor: FactExtractor | None = None
        self._last_transcript_signed: SignedPayload | None = None

    def commit_transcript(self, text: str, trace: TurnTrace) -> str | None:
        """Commits the user speech transcript to memory with a cryptographic signature."""
        if not self.memory_store or not text.strip():
            return None
        try:
            user_signer = (
                getattr(self._orchestrator, "user_signer", None)
                if self._orchestrator is not None
                else None
            )
            if user_signer is None:
                user_signer = self.signer_factory.user_speech()
                if self._orchestrator is not None:
                    self._orchestrator.user_signer = user_signer

            ts = self.clock.now_utc()
            unsigned = UnsignedPayload(
                content=text.strip(),
                provenance=Provenance.USER_EXPLICIT,
                kind="fact",
                nonce=os.urandom(16).hex(),
                created_at=ts,
                trace_id=trace.trace_id,
            )
            signed = user_signer.sign(unsigned)
            # WO-9 A2 (ADR-010): keep the signed transcript payload so a
            # grounded memory_commit in this turn can reference it as the
            # USER_EXPLICIT source for FactExtractor quote grounding.
            self._last_transcript_signed = signed
            if self._orchestrator is not None:
                self._orchestrator._last_transcript_signed = signed

            self.memory_store.commit(signed, now=ts)
            if self._orchestrator is not None and hasattr(self._orchestrator, "_publish_mem_event"):
                self._orchestrator._publish_mem_event("USER_EXPLICIT", text)
            return signed.entry_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("transcript_commit_failed", error=str(exc))
            return None

    _commit_transcript = commit_transcript

    def commit_action_receipts(self, trace: TurnTrace) -> None:
        """WO-9 A9 (F8): persist this turn's tool receipts as ASSISTANT_ACTION.

        Every LLM-initiated tool attempt — success, failure, user-cancelled
        confirmation, confirmation timeout, BDI rejection, provenance refusal —
        becomes a signed autobiographical record. This is the persistent
        receipt trail the honesty contract depends on: 'did you actually do X?'
        must be answerable from SELF_HISTORY, never confabulated.
        """
        receipts = (
            getattr(self._orchestrator, "current_turn_receipts", None)
            if self._orchestrator is not None
            else None
        )
        if not self.memory_store or not receipts:
            return

        action_signer = (
            getattr(self._orchestrator, "action_signer", None)
            if self._orchestrator is not None
            else None
        )
        if action_signer is None:
            action_signer = self.signer_factory.tool_result()
            if self._orchestrator is not None:
                self._orchestrator.action_signer = action_signer

        now = self.clock.now_utc()
        for receipt in receipts:
            try:
                args_summary = ", ".join(
                    f"{k}={str(v)[:60]}" for k, v in list(receipt.args.items())[:3]
                )
                status = "ok" if receipt.ok else "failed"
                if receipt.error and "cancelled" in str(receipt.error).lower():
                    status = "cancelled"
                elif receipt.error and "timeout" in str(receipt.error).lower():
                    status = "timeout"
                detail = str(receipt.error or receipt.output or "")[:200]
                content = f"{receipt.tool}({args_summary}) -> {status}"
                if detail:
                    content = f"{content}: {detail}"
                unsigned = UnsignedPayload(
                    content=content,
                    provenance=Provenance.ASSISTANT_ACTION,
                    kind="action_receipt",
                    nonce=os.urandom(16).hex(),
                    created_at=now,
                    trace_id=trace.trace_id,
                    confidence=1.0,
                    structured={
                        "importance": 0.2,
                        "call_id": receipt.call_id,
                        "tool": receipt.tool,
                        "ok": receipt.ok,
                        "error": str(receipt.error) if receipt.error else None,
                        "valid_from": now,
                    },
                )
                signed = action_signer.sign(unsigned)
                self.memory_store.commit(signed, now=now)
                if self._orchestrator is not None:
                    pending_rat = getattr(self._orchestrator, "_pending_ratification", None)
                    if (
                        pending_rat is not None
                        and getattr(pending_rat, "call_id", "") == receipt.call_id
                    ):
                        pending_rat.fetch_receipt_entry_id = signed.entry_id
            except Exception as exc:  # noqa: BLE001
                logger.warning("assistant_action_commit_failed", error=str(exc))
        receipts.clear()

    _commit_action_receipts = commit_action_receipts

    def maybe_extract_facts(self, trace: TurnTrace) -> None:
        """WO-9 A3: passive USER_DERIVED fact extraction from the user's words.

        Deterministic high-precision candidates (is_named / lives_in / works_at)
        are re-validated by FactExtractor verbatim-quote grounding and signed
        USER_DERIVED citing the turn transcript. Questions and hypothetical
        phrasing are skipped. Runs at finalize, off the speech path; bounded by
        FactExtractor's <=5 facts/turn cap. Functional predicates supersede
        prior values via store.commit (e.g. a name update).
        """
        if not self.memory_store:
            return
        transcript_payload = (
            getattr(self._orchestrator, "_last_transcript_signed", None)
            if self._orchestrator is not None
            else self._last_transcript_signed
        )
        if (
            transcript_payload is None
            or getattr(transcript_payload, "trace_id", None) != trace.trace_id
        ):
            return
        text = str(transcript_payload.content)
        stripped = text.strip()
        if _INTERROGATIVE_PATTERN.match(stripped) or _INTERROGATIVE_OPENER_PATTERN.match(stripped):
            return
        lower = text.lower()
        if any(marker in lower for marker in _HYPOTHETICAL_MARKERS):
            return

        candidates: list[dict[str, str]] = []
        for pred, pattern in _PASSIVE_FACT_PATTERNS:
            for m in pattern.finditer(text):
                value = m.group(1).strip().rstrip(".,!?;:")
                if not value:
                    continue

                sentence = _sentence_containing(text, m.start())

                # Reported-speech guard (row 11): attribution blindness prevention
                if _REPORTED_SPEECH_PATTERN.search(sentence):
                    continue

                # Negation window guard (row 11): voids candidates with negation before/at capture
                pre_window = text[max(0, m.start() - 15) : m.start(1)]
                if _NEGATION_PATTERN.search(pre_window) or value.lower() in (
                    "not",
                    "never",
                    "no",
                    "nobody",
                    "none",
                ):
                    continue

                # Location stopword guard (WO-20 Phase 0)
                if pred in ("origin_is", "lives_in") and value.lower() in _LOCATION_STOPWORDS:
                    continue

                # Demonym lexicon post-filter for nationality_is
                if pred == "nationality_is":
                    if value.lower() not in _DEMONYMS:
                        continue
                    value = value.capitalize()

                candidates.append(
                    {
                        "s": "user",
                        "p": pred,
                        "o": value,
                        "quote": sentence,
                    }
                )
        if not candidates:
            return

        extractor = (
            getattr(self._orchestrator, "_fact_extractor", None)
            if self._orchestrator is not None
            else self._fact_extractor
        )
        if extractor is None:
            extractor = FactExtractor(master_key=self.signer_factory.master_key)
            self._fact_extractor = extractor
            if self._orchestrator is not None:
                self._orchestrator._fact_extractor = extractor

        try:
            signed_facts = extractor.extract_and_sign(transcript_payload, candidates)
        except Exception as exc:  # noqa: BLE001
            logger.warning("passive_fact_extraction_failed", error=str(exc))
            return

        now = self.clock.now_utc()
        for signed_fact in signed_facts:
            # Semantic verification: verify fact candidate does not contradict transcript
            if self.verifier is not None:
                try:
                    v_res = self.verifier.check_consistency(
                        premise=transcript_payload.content,
                        hypothesis=str(signed_fact.content),
                    )
                    if not v_res.degraded and v_res.label == VerifierLabel.CONTRADICTION:
                        logger.info(
                            "passive_fact_rejected_contradiction",
                            fact=str(signed_fact.content),
                        )
                        continue
                except Exception as exc:  # noqa: BLE001
                    logger.debug("fact_verifier_eval_failed", error=str(exc))

            try:
                self.memory_store.commit(signed_fact, now=now)
                logger.info("passive_fact_extracted", content=str(signed_fact.content))
            except Exception as exc:  # noqa: BLE001
                logger.warning("passive_fact_commit_failed", error=str(exc))

    _maybe_extract_facts = maybe_extract_facts

    def commit_assistant_utterance(self, text: str, trace: TurnTrace) -> None:
        """Commits assistant's spoken utterance to memory (D-MEM-04, ASSISTANT_UTTERANCE)."""
        if not self.memory_store or not text.strip():
            return
        try:
            assistant_signer = (
                getattr(self._orchestrator, "assistant_signer", None)
                if self._orchestrator is not None
                else None
            )
            if assistant_signer is None:
                assistant_signer = self.signer_factory.assistant_utterance()
                if self._orchestrator is not None:
                    self._orchestrator.assistant_signer = assistant_signer

            ts = self.clock.now_utc()
            imp = (
                getattr(self._orchestrator, "_turn_importance", None)
                if self._orchestrator is not None
                else None
            )
            structured = {"importance": imp} if imp is not None else None
            unsigned = UnsignedPayload(
                content=text.strip(),
                provenance=Provenance.ASSISTANT_UTTERANCE,
                kind="assistant_utterance",
                nonce=os.urandom(16).hex(),
                created_at=ts,
                trace_id=trace.trace_id,
                structured=structured,
            )
            signed = assistant_signer.sign(unsigned)
            self.memory_store.commit(signed, now=ts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("assistant_utterance_commit_failed", error=str(exc))

    _commit_assistant_utterance = commit_assistant_utterance

    def commit_coherence_breach(self, claim: str, trace: TurnTrace | None = None) -> None:
        """Commits functional coherence breach to memory (D-MEM-04, COHERENCE_BREACH)."""
        if not self.memory_store or not claim.strip():
            return
        try:
            breach_signer = (
                getattr(self._orchestrator, "breach_signer", None)
                if self._orchestrator is not None
                else None
            )
            if breach_signer is None:
                breach_signer = self.signer_factory.coherence_breach()
                if self._orchestrator is not None:
                    self._orchestrator.breach_signer = breach_signer

            trace_id = trace.trace_id if trace is not None else f"breach-{ulid.ULID()}"
            ts = self.clock.now_utc()
            unsigned = UnsignedPayload(
                content=claim.strip(),
                provenance=Provenance.COHERENCE_BREACH,
                kind="coherence_breach",
                nonce=os.urandom(16).hex(),
                created_at=ts,
                trace_id=trace_id,
            )
            signed = breach_signer.sign(unsigned)
            self.memory_store.commit(signed, now=ts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("coherence_breach_commit_failed", error=str(exc))

    _commit_coherence_breach = commit_coherence_breach

    def maybe_form_belief(self, reply_text: str, trace: TurnTrace) -> None:
        """Extracts first-person stance claims and commits an ASSISTANT_BELIEF (Spec §7, WP-2)."""
        if not self.memory_store or not reply_text.strip():
            return
        if self._orchestrator is not None:
            config = getattr(self._orchestrator, "config", None)
            memory_config = getattr(config, "memory", None) if config is not None else None
            if memory_config is not None and not getattr(memory_config, "form_beliefs", True):
                return

        lower_reply = reply_text.lower()
        if not any(m in lower_reply for m in STANCE_MARKERS):
            return

        topic = _extract_stance_topic(reply_text)
        now = self.clock.now_utc()
        try:
            assistant_signer = (
                getattr(self._orchestrator, "assistant_signer", None)
                if self._orchestrator is not None
                else None
            )
            if assistant_signer is None:
                assistant_signer = self.signer_factory.assistant_utterance()
                if self._orchestrator is not None:
                    self._orchestrator.assistant_signer = assistant_signer

            unsigned = UnsignedPayload(
                content=reply_text.strip(),
                provenance=Provenance.ASSISTANT_BELIEF,
                kind="belief",
                nonce=os.urandom(16).hex(),
                created_at=now,
                trace_id=trace.trace_id,
                confidence=0.7,
                structured={"importance": 0.3, "topic": topic, "valid_from": now},
            )
            signed = assistant_signer.sign(unsigned)
            self.memory_store.commit(signed, now=now)
            logger.info("assistant_belief_formed", topic=topic, trace_id=trace.trace_id)
            if self._orchestrator is not None and hasattr(self._orchestrator, "_publish_mem_event"):
                self._orchestrator._publish_mem_event("ASSISTANT_BELIEF", reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("assistant_belief_commit_failed", error=str(exc))

    _maybe_form_belief = maybe_form_belief
