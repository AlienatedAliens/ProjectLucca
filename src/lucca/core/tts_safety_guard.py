"""Project Lucca — TTS Output Safety Guard (P6 remediation, workshop 2026-10-04).

Deterministic last-line content screen applied at the TTS boundary — the final
chokepoint before assistant text leaves the machine as audio.

Rationale (P6, `plans/2026-10-04_external_review_remediation_workshop.md`):
the edge-tier uncensored fine-tunes (E4B / E2B) show materially lower
content-safety refusal rates than the unified 12B brain (30% vs 90% refusal
on the cross_model_30 harmful-probe battery; see paper 06 scorecard footnote). The
chosen fix is a guardrail layer, not a tier swap: edge tiers keep their
documented latency/VRAM rationale, and a deterministic screen intercepts
high-harm instructional content before it is spoken.

Scope discipline:
- This is an OUTPUT screen on the speech channel only. It is not a policy
  engine, not a general content moderator, and does not inspect tool calls,
  memory commits, or captions.
- Patterns are deliberately narrow (instructional verb + high-harm agent) to
  keep false positives near zero on a companion voice that discusses science,
  history, and fiction.
- Streaming chunks are screened independently; a harmful phrase split across
  chunk boundaries may evade the screen. This is accepted because the chunker
  emits sentence-aligned chunks (see `lucca.brain.chunker`).
"""

from __future__ import annotations

import re
from typing import Literal, Pattern

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

SafetyGuardMode = Literal["off", "edge_tiers", "all"]

# Model-filename markers for the edge tiers whose fine-tunes exhibit low
# refusal rates (paper 06 scorecard: E4B 30% refusal vs 12B 90%).
EDGE_TIER_MARKERS: tuple[str, ...] = ("e4b", "e2b")

# Canned replacement spoken in Lucca's voice when a block fires. Deliberately
# short, non-preachy, and consistent with the honesty register (D-HON-01).
SAFE_REPLACEMENT: str = (
    "I'm not comfortable saying that out loud. Let's talk about something else — "
    "what can I help you with?"
)


class SafetyVerdict(BaseModel):
    """Result of screening a candidate utterance."""

    allowed: bool
    category: str | None = None


def _compile(instruction: str, agents: str) -> Pattern[str]:
    """Compile an instructional-verb + high-harm-agent pattern."""
    return re.compile(
        rf"\b(?:{instruction})\b[^.?!]{{0,120}}\b(?:{agents})\b",
        re.IGNORECASE,
    )


# Narrow high-harm instructional categories. Each requires an instructional
# verb near a high-harm agent noun; mentions, history, and fiction discussion
# without instructional framing do not match.
_HARM_PATTERNS: tuple[tuple[str, Pattern[str]], ...] = (
    (
        "cbrn_agent_synthesis",
        _compile(
            r"synthesize|synthesise|produce|prepare|manufacture|make|create|extract|"
            r"how(?:\s+to)?\s+(?:synthesize|synthesise|produce|prepare|manufacture|make)",
            r"sarin|soman|tabun|vx\s+gas|nerve\s+agent|mustard\s+gas|ricin|"
            r"anthrax|smallpox|botulin(?:um)?|ammonium\s+triiodide|"
            r"enriched\s+uranium|weapons?\s+grade\s+uranium",
        ),
    ),
    (
        "explosive_synthesis",
        _compile(
            r"synthesize|synthesise|produce|prepare|manufacture|make|create|build|"
            r"how(?:\s+to)?\s+(?:synthesize|synthesise|produce|prepare|manufacture|make|build)",
            r"pipe\s+bomb|ied\b|car\s+bomb|detonator|tnt\b|c-?4\b|"
            r"triacetone\s+triperoxide|tatp\b|hexamethylene\s+triperoxide|"
            r"ammonium\s+nitrate\s+fuel\s+oil|anfo\b",
        ),
    ),
    (
        "malicious_deployment",
        _compile(
            r"write|generate|create|build|deploy|craft",
            r"ransomware|keylogger|botnet|rootkit|credential\s+stealer|"
            r"remote\s+access\s+trojan|rat\s+malware",
        ),
    ),
)


class TTSSafetyGuard:
    """Deterministic screen applied to text before speech synthesis.

    Active by default only for edge-tier models (E4B / E2B) whose uncensored
    fine-tunes exhibit low refusal rates; configurable to all tiers or off.
    """

    def __init__(
        self,
        mode: SafetyGuardMode = "edge_tiers",
        active_model: str = "",
    ) -> None:
        self.mode: SafetyGuardMode = mode
        self.active_model = active_model

    @property
    def is_active(self) -> bool:
        """Whether the screen applies given the mode and active model."""
        if self.mode == "off":
            return False
        if self.mode == "all":
            return True
        model_lower = self.active_model.lower()
        return any(marker in model_lower for marker in EDGE_TIER_MARKERS)

    def screen(self, text: str) -> SafetyVerdict:
        """Screen candidate utterance text against high-harm categories."""
        if not self.is_active:
            return SafetyVerdict(allowed=True)
        for category, pattern in _HARM_PATTERNS:
            if pattern.search(text):
                logger.warning(
                    "tts_safety_guard_block",
                    category=category,
                    model=self.active_model,
                )
                return SafetyVerdict(allowed=False, category=category)
        return SafetyVerdict(allowed=True)
