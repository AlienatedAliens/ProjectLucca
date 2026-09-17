"""
Fake LLM Client for Deterministic Unit and Integration Tests
Spec 10 §1
"""

import time
from collections.abc import Generator

from lucca.core.schemas import Done, LLMEvent, LLMUsage, MemoryHit, TokenDelta


class FakeLLM:
    def __init__(self, script: list[LLMEvent] | None = None, token_delay_s: float = 0.0) -> None:
        self.script = script or [
            TokenDelta(delta="Hello "),
            TokenDelta(delta="there! "),
            TokenDelta(delta="I am Lucca. "),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=3)),
        ]
        self.token_delay_s = token_delay_s
        self.aborted = False

    def stream_turn(
        self,
        current_audio_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> Generator[LLMEvent, None, None]:
        self.aborted = False
        for event in self.script:
            if self.aborted:
                break
            if self.token_delay_s > 0:
                time.sleep(self.token_delay_s)
            yield event

    def abort(self) -> None:
        self.aborted = True
