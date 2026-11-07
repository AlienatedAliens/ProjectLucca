import sys, time, wave
from pathlib import Path
import numpy as np

MODEL_DIR = Path(r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512")
COSYVOICE_DIR = Path(r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, str(COSYVOICE_DIR))
sys.path.insert(0, str(COSYVOICE_DIR / "third_party" / "Matcha-TTS"))

from cosyvoice.cli.cosyvoice import CosyVoice3

print("Initializing CosyVoice 3...")
cv3 = CosyVoice3(str(MODEL_DIR), fp16=True)

text = "Testing real-time streaming audio generation on CosyVoice 3."
instruct = "You are a helpful assistant.<|endofprompt|>"
ref_wav = r"C:\ProjectLucca\models\tts\samples\sample_systems_check_base.wav"

print("Synthesizing...")
chunks = []
t0 = time.perf_counter()
for c in cv3.inference_instruct2(text, instruct, prompt_wav=ref_wav, stream=False, speed=1.0):
    chunks.append(c["tts_speech"].squeeze().cpu().numpy())

audio = np.concatenate(chunks)
samples_i16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
out_path = r"C:\ProjectLucca\models\tts\samples\test_clean_english_instruct.wav"
with wave.open(out_path, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(24000)
    wf.writeframes(samples_i16.tobytes())

print(f"Generated {len(samples_i16)} samples ({len(samples_i16)/24000:.2f}s) in {time.perf_counter()-t0:.2f}s")
