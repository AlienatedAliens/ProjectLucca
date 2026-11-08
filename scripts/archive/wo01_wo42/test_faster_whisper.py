import time

import faster_whisper
import numpy as np

SAMPLE_WAV = r"C:\projects\ProjectLucca\tests\fixtures\audio_tool_calls\calc_01.wav"

print("Testing faster-whisper distil-small.en on CPU (int8)...")
t0 = time.time()
model = faster_whisper.WhisperModel(
    "distil-small.en", device="cpu", compute_type="int8", cpu_threads=8
)
print(f"Loaded in {time.time() - t0:.2f}s")

# Warmup
segments, info = model.transcribe(SAMPLE_WAV)
text = " ".join([s.text for s in segments])
print(f"Warmup transcription: '{text}'")

latencies = []
for i in range(5):
    t_start = time.perf_counter()
    segments, info = model.transcribe(SAMPLE_WAV)
    text = " ".join([s.text for s in segments])
    dur_ms = (time.perf_counter() - t_start) * 1000.0
    latencies.append(dur_ms)
    print(f"  Run {i + 1}: {dur_ms:.1f} ms -> '{text}'")


p50 = float(np.percentile(latencies, 50))
p95 = float(np.percentile(latencies, 95))
print(f"faster-whisper CPU int8: p50={p50:.1f} ms, p95={p95:.1f} ms")
