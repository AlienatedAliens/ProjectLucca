"""
Project Lucca — Reasoning Context (Working Memory)
Spec D-REAS-09, WO-20 Phase 2
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Final

import structlog

from lucca.core.schemas import AssertFact

logger = structlog.get_logger(__name__)

DEFAULT_MAX_CHAIN_DEPTH: Final[int] = 8
DEFAULT_CAPACITY: Final[int] = DEFAULT_MAX_CHAIN_DEPTH * 4  # 32 entries


@dataclass
class ReasoningEntry:
    envelope_id: str
    s: str
    p: str
    o: str
    confidence: float = 1.0
    step_kind: str = "lisp_rule"
    rule_id: str | None = None
    premises: list[str] = field(default_factory=list)

    @property
    def conclusion(self) -> str:
        return f"{self.s} {self.p} {self.o}"

    def as_tuple(self) -> tuple[str, str, str, str, float, str]:
        return (self.envelope_id, self.s, self.p, self.o, self.confidence, self.step_kind)

    def __iter__(self) -> Iterator[object]:
        return iter((self.envelope_id, self.s, self.p, self.o, self.confidence, self.step_kind))

    def __len__(self) -> int:
        return 6

    def __getitem__(self, index: int | str) -> object:
        if isinstance(index, str):
            if hasattr(self, index):
                return getattr(self, index)
            raise KeyError(f"ReasoningEntry has no field '{index}'")
        return (self.envelope_id, self.s, self.p, self.o, self.confidence, self.step_kind)[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ReasoningEntry):
            return self.envelope_id == other.envelope_id
        if isinstance(other, tuple) and len(other) == 6:
            return (
                self.envelope_id,
                self.s,
                self.p,
                self.o,
                self.confidence,
                self.step_kind,
            ) == other
        if isinstance(other, str):
            return self.conclusion == other or self.envelope_id == other
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "envelope_id": self.envelope_id,
            "s": self.s,
            "p": self.p,
            "o": self.o,
            "confidence": self.confidence,
            "step_kind": self.step_kind,
            "rule_id": self.rule_id,
            "premises": list(self.premises),
            "conclusion": self.conclusion,
        }


@dataclass
class ProofTraceStep:
    step_kind: str
    rule_id: str
    premises: list[str]
    conclusion: str
    envelope_id: str
    confidence: float = 1.0

    def as_tuple(self) -> tuple[str, str, list[str], str, str]:
        return (self.step_kind, self.rule_id, self.premises, self.conclusion, self.envelope_id)

    def __iter__(self) -> Iterator[object]:
        return iter(
            (self.step_kind, self.rule_id, self.premises, self.conclusion, self.envelope_id)
        )

    def __len__(self) -> int:
        return 5

    def __getitem__(self, index: int | str) -> object:
        if isinstance(index, str):
            if hasattr(self, index):
                return getattr(self, index)
            raise KeyError(f"ProofTraceStep has no field '{index}'")
        return (self.step_kind, self.rule_id, self.premises, self.conclusion, self.envelope_id)[
            index
        ]

    def get(self, key: str, default: object = None) -> object:
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ProofTraceStep):
            return (
                self.step_kind == other.step_kind
                and self.rule_id == other.rule_id
                and self.premises == other.premises
                and self.conclusion == other.conclusion
                and self.envelope_id == other.envelope_id
            )
        if isinstance(other, tuple) and len(other) == 5:
            return (
                self.step_kind,
                self.rule_id,
                self.premises,
                self.conclusion,
                self.envelope_id,
            ) == other
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "step_kind": self.step_kind,
            "rule_id": self.rule_id,
            "premises": list(self.premises),
            "conclusion": self.conclusion,
            "envelope_id": self.envelope_id,
            "confidence": self.confidence,
        }


class ReasoningContext:
    """Chain-scoped scratchpad holding signed intermediates with provenance (Spec D-REAS-09, WO-20 Phase 2).

    Isolated from long-term memory until a conclusion commits.
    Bounded at MAX_CHAIN_DEPTH * 4 entries.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self.capacity: int = capacity
        self._intermediates: list[ReasoningEntry] = []

    @property
    def intermediates(self) -> list[ReasoningEntry]:
        return list(self._intermediates)

    @property
    def entries(self) -> list[ReasoningEntry]:
        return list(self._intermediates)

    def __len__(self) -> int:
        return len(self._intermediates)

    def __iter__(self) -> Iterator[ReasoningEntry]:
        return iter(self._intermediates)

    def __getitem__(self, index: int) -> ReasoningEntry:
        return self._intermediates[index]

    def add_intermediate(
        self,
        envelope_id: str,
        s: str,
        p: str,
        o: str,
        confidence: float = 1.0,
        step_kind: str = "lisp_rule",
        rule_id: str | None = None,
        premises: list[str] | None = None,
    ) -> ReasoningEntry:
        if len(self._intermediates) >= self.capacity:
            logger.warning(
                "reasoning_context_capacity_exceeded",
                current=len(self._intermediates),
                capacity=self.capacity,
            )
            raise RuntimeError(
                f"ReasoningContext capacity exceeded: maximum {self.capacity} entries"
            )

        if premises is None:
            # Default to the immediately preceding intermediate conclusion if one exists
            if self._intermediates:
                resolved_premises = [self._intermediates[-1].conclusion]
            else:
                resolved_premises = []
        else:
            resolved_premises = list(premises)

        entry = ReasoningEntry(
            envelope_id=envelope_id,
            s=s.strip(),
            p=p.strip(),
            o=o.strip(),
            confidence=confidence,
            step_kind=step_kind,
            rule_id=rule_id,
            premises=resolved_premises,
        )
        self._intermediates.append(entry)
        return entry

    def resolve_premise(self, premise: str) -> ReasoningEntry | None:
        clean = premise.strip()
        for item in self._intermediates:
            if item.conclusion == clean or item.envelope_id == clean:
                return item
        return None

    def premises_for(
        self, conclusion: str | tuple[str, str, str] | AssertFact | ReasoningEntry
    ) -> list[ReasoningEntry]:
        target_entry: ReasoningEntry | None = None

        if isinstance(conclusion, ReasoningEntry):
            target_entry = conclusion
        elif isinstance(conclusion, AssertFact):
            target_str = f"{conclusion.s} {conclusion.p} {conclusion.o}".strip()
            for item in self._intermediates:
                if item.conclusion == target_str:
                    target_entry = item
                    break
        elif isinstance(conclusion, tuple) and len(conclusion) == 3:
            target_str = f"{conclusion[0]} {conclusion[1]} {conclusion[2]}".strip()
            for item in self._intermediates:
                if item.conclusion == target_str:
                    target_entry = item
                    break
        elif isinstance(conclusion, str):
            target_str = conclusion.strip()
            for item in self._intermediates:
                if item.conclusion == target_str or item.envelope_id == target_str:
                    target_entry = item
                    break

        if target_entry is None:
            return []

        resolved: list[ReasoningEntry] = []
        for prem in target_entry.premises:
            matched = self.resolve_premise(prem)
            if matched is not None:
                resolved.append(matched)

        return resolved

    def proof_trace(self) -> list[ProofTraceStep]:
        trace: list[ProofTraceStep] = []
        for entry in self._intermediates:
            trace.append(
                ProofTraceStep(
                    step_kind=entry.step_kind,
                    rule_id=entry.rule_id or "lisp_rule",
                    premises=list(entry.premises),
                    conclusion=entry.conclusion,
                    envelope_id=entry.envelope_id,
                    confidence=entry.confidence,
                )
            )
        return trace

    def clear(self) -> None:
        self._intermediates.clear()
