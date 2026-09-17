"""
Project Lucca — Latency Trace Schema & Logging
Spec 10 §1, §2
"""

import json
from typing import Literal

from pydantic import BaseModel

from lucca.core.config import get_config


class TurnTrace(BaseModel):
    trace_id: str
    mode: Literal["audio", "transcript"] = "audio"
    route: str = "llm"
    tts_device: str = "CPU"
    asr_device: str = "cpu"

    # Monotonic timestamps (ns)
    t_key_press: int = 0
    t_key_release: int = 0  # Origin
    t_vad_done: int = 0
    t_asr_sent: int = 0
    t_asr_done: int = 0
    t_route_done: int = 0
    t_llm_sent: int = 0
    t_llm_first_token: int = 0
    t_first_chunk: int = 0
    t_tts_first_sent: int = 0
    t_tts_first_done: int = 0
    t_first_sample: int = 0  # Latency end
    t_llm_done: int = 0
    t_tts_last_done: int = 0
    t_playback_done: int = 0
    t_postturn_done: int = 0

    tokens_out: int = 0
    chunks: int = 0
    underruns: int = 0
    interrupted: bool = False

    @property
    def total_e2e_ms(self) -> float:
        if self.t_key_release > 0 and self.t_first_sample > self.t_key_release:
            return (self.t_first_sample - self.t_key_release) / 1_000_000.0
        return 0.0

    @property
    def ttft_ms(self) -> float:
        if self.t_llm_sent > 0 and self.t_llm_first_token > self.t_llm_sent:
            return (self.t_llm_first_token - self.t_llm_sent) / 1_000_000.0
        return 0.0

    @property
    def tts_first_ms(self) -> float:
        if self.t_tts_first_sent > 0 and self.t_tts_first_done > self.t_tts_first_sent:
            return (self.t_tts_first_done - self.t_tts_first_sent) / 1_000_000.0
        return 0.0


def log_turn_trace(trace: TurnTrace) -> None:
    config = get_config()
    logs_dir = config.resolve_path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    trace_file = logs_dir / "traces.jsonl"

    data = trace.model_dump()
    data["total_e2e_ms"] = trace.total_e2e_ms
    data["ttft_ms"] = trace.ttft_ms
    data["tts_first_ms"] = trace.tts_first_ms

    with open(trace_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")
