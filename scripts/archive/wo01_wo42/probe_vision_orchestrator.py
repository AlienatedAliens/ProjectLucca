#!/usr/bin/env python3
"""Verify End-to-End Multimodal Vision Narration via Lucca Orchestrator."""

import base64
import io
import time
from unittest.mock import patch
from PIL import Image, ImageDraw

from lucca.brain.llm_client import LLMClient
from lucca.core.orchestrator import Orchestrator
from lucca.core.trace import TurnTrace


class DummyTTS:
    def __init__(self, play_ring=None):
        pass
    def set_voice(self, v):
        pass
    def set_speed(self, s):
        pass
    def set_dsp_config(self, **kwargs):
        pass
    def synthesize(self, chunk_id, text, **kwargs):
        pass


def get_mock_screenshot():
    """Generate a test image card."""
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 30, 80, 90], fill=(66, 133, 244), outline=(0, 0, 0))  # Blue rectangle
    draw.ellipse([110, 30, 170, 90], fill=(234, 67, 53), outline=(0, 0, 0))   # Red circle
    draw.polygon([(230, 30), (200, 90), (260, 90)], fill=(52, 168, 83), outline=(0, 0, 0))  # Green triangle
    draw.text((20, 120), "PROJECT LUCCA HARDWARE MONITOR", fill=(0, 0, 0))
    draw.text((20, 150), "STATUS: 100% OPERATIONAL", fill=(0, 150, 0))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64, 400, 200


def main():
    print("=" * 70)
    print("Testing End-to-End Multimodal Vision via Lucca Orchestrator")
    print("=" * 70)

    llm = LLMClient()
    orch = Orchestrator(llm=llm, tts=DummyTTS, execute_tools=True)
    orch._request_confirmation = lambda *args, **kwargs: True

    with patch("lucca.sandbox.screenshot_tool.capture_screenshot", side_effect=get_mock_screenshot):
        trace = TurnTrace(trace_id="test-vision-turn-1")
        prompt = "Please take a screenshot of the monitor using screenshot_capture and tell me what the status and shapes are."
        print(f"\nUser: {prompt}")

        t0 = time.perf_counter()
        orch._run_text_turn(trace, prompt)
        elapsed = time.perf_counter() - t0

    asst_resp = ""
    for msg in reversed(orch.history):
        if msg.get("role") == "assistant":
            asst_resp = str(msg.get("content", ""))
            break

    print(f"\nLucca ({elapsed:.2f}s): {asst_resp}")
    print("=" * 70)


if __name__ == "__main__":
    main()
