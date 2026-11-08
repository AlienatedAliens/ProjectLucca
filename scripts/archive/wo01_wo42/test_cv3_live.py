"""
Live CosyVoice 3 synthesis smoke test.
Sends a real request and writes the output to a WAV file so we can hear it.
"""
import sys
import time
import json
import base64
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import zmq
import numpy as np
import wave

PORT = 47005
TEXT = "Systems nominal. I am online and ready to work."
STEM = str(Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\harvested\asuka_023_focused_analytical_in_japanese_they_do_actually.wav"))
OUT_WAV = str(Path(__file__).parent / "cv3_live_out.wav")

ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.setsockopt(zmq.RCVTIMEO, 60000)
sock.setsockopt(zmq.SNDTIMEO, 10000)
sock.connect(f"tcp://127.0.0.1:{PORT}")

# Ping first
print("Pinging service...")
sock.send_json({"cmd": "ping"})
pong = sock.recv_json()
print("Ping response:", pong)

# Request audio returned directly (not via ring buffer)
print(f"\nRequesting synthesis: '{TEXT}'")
print(f"Stem: {STEM}")
t0 = time.perf_counter()

req = {
    "cmd": "test_audio",
    "text": TEXT,
    "instruct": f"You are a helpful assistant. Please speak in English with a natural, clear, confident cadence.<|endofprompt|>",
    "prompt_wav": STEM,
    "profile": "inventor",
    "speed": 1.0,
    "stream": False,
    "direct_ring": False,
}
sock.send_json(req)
resp = sock.recv_json()

elapsed = time.perf_counter() - t0
print(f"\nResponse received in {elapsed:.2f}s")
print("Status:", resp.get("status"))
print("Samples:", resp.get("samples", 0))
print("Elapsed (service-side):", resp.get("elapsed_ms", "?"), "ms")
print("Chunks:", resp.get("chunks", "?"))
print("Error:", resp.get("error", "none"))

if resp.get("status") == "ok" and "audio_b64" in resp:
    raw = base64.b64decode(resp["audio_b64"])
    samples_i16 = np.frombuffer(raw, dtype=np.int16)
    duration = len(samples_i16) / 24000
    print(f"\nAudio: {len(samples_i16)} samples @ 24kHz = {duration:.2f}s")
    print(f"Peak amplitude: {np.max(np.abs(samples_i16))}")
    
    # Write WAV
    with wave.open(OUT_WAV, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(samples_i16.tobytes())
    print(f"Written to: {OUT_WAV}")
else:
    print("NO AUDIO RETURNED")
    print("Full response:", json.dumps(resp, indent=2))

sock.close()
ctx.destroy()
