"""
End-to-end verification of SparkTTSClient in Project Lucca.
Tests service spawning, ZeroMQ communication, 3D PAD attribute conditioning,
and audio synthesis.
"""

import sys
import time
from pathlib import Path

# Ensure src/ is in sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lucca.speech.spark_client import SparkTTSClient

client = SparkTTSClient.get_instance()
print("Checking Spark-TTS service status...")
online = client.ensure_service(timeout_s=35.0)
print(f"Service online: {online}")
assert online, "Spark-TTS service failed to start"

print("\nPinging Spark-TTS service...")
pong = client.ping()
print(f"Ping result: {pong}")
assert pong, "Spark-TTS ping failed"

print("\nTesting test_audio synthesis with 3D PAD Righteous Anger stance...")
t0 = time.perf_counter()
samples, sr = client.test_audio(
    text="Anta baka?! What do you think you're doing messing with my settings?",
    stance="RIGHTEOUS_ANGER",
    pitch_semitones=1.5,
    speed=1.15,
)
dt = (time.perf_counter() - t0) * 1000.0

if samples is not None:
    dur_s = len(samples) / sr
    print(f"Synthesized {dur_s:.2f}s of audio at {sr}Hz in {dt:.1f}ms (RTF={dt/(dur_s*1000.0):.3f})")
    import wave
    out_wav = Path(r"C:\Projects\ProjectLucca\models\tts\spark_asuka_righteous_anger.wav")
    samples_i16 = (samples * 32767.0).astype("int16")
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples_i16.tobytes())
    print(f"Saved audio to: {out_wav}")

else:
    print("Failed to synthesize audio!")

print("\nTesting synthesize() with direct_ring=False...")
res = client.synthesize(
    text="Everything is green across the board. Good work!",
    stance="PLAYFUL_TEASING",
    pitch_semitones=0.5,
    speed=1.05,
    direct_ring=False,
)
print("Synthesize result:", res)
assert res.get("status") == "ok", f"Synthesize failed: {res}"
print("\nSpark-TTS End-to-End Test PASSED!")
