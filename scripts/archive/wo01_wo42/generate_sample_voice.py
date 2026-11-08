import os
import wave
import numpy as np
import kokoro_onnx

output_dir = r"C:\ProjectLucca\models\tts\samples"
os.makedirs(output_dir, exist_ok=True)

model_path = r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx"
voices_path = r"C:\ProjectLucca\models\tts\voices-v1.0.bin"

print("Loading Kokoro ONNX model...")
kokoro = kokoro_onnx.Kokoro(model_path, voices_path)

phrases = [
    ("anta_baka", "Anta baka?! Did you really think you could solve all these math problems without me?"),
    ("systems_check", "All systems nominal. 16K context verified, and memory telemetry is completely clear."),
    ("intimate_reassurance", "Hey... don't stress yourself out so much. I've got everything under control, okay?"),
]

for name, text in phrases:
    out_wav = os.path.join(output_dir, f"sample_{name}_base.wav")
    print(f"Synthesizing: '{text}' -> {out_wav}")
    samples, sr = kokoro.create(text, voice="af_sarah", speed=1.10)
    
    # Save as 16-bit PCM WAV
    samples_i16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples_i16.tobytes())
    print(f"Saved: {out_wav} ({len(samples_i16)/sr:.2f}s)")

print("\nAll base samples synthesized successfully!")
