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
        self.aborted_traces: set[str] = set()
        self.last_memories: list[MemoryHit] | None = None

    def stream_turn(
        self,
        current_audio_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
        trace_id: str | None = None,
    ) -> Generator[LLMEvent, None, None]:
        self.aborted = False
        self.last_memories = memories
        for event in self.script:
            if self.aborted or (trace_id and trace_id in self.aborted_traces):
                break
            if self.token_delay_s > 0:
                time.sleep(self.token_delay_s)
            yield event

    def abort(self, trace_id: str | None = None) -> None:
        self.aborted = True
        if trace_id:
            self.aborted_traces.add(trace_id)
