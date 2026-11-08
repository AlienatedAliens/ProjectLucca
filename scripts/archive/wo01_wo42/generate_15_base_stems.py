import os
import wave
import numpy as np
import kokoro_onnx

output_dir = r"C:\ProjectLucca\models\tts\references\asuka_base"
os.makedirs(output_dir, exist_ok=True)

model_path = r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx"
voices_path = r"C:\ProjectLucca\models\tts\voices-v1.0.bin"

print("Loading Kokoro ONNX model...")
kokoro = kokoro_onnx.Kokoro(model_path, voices_path)

# 15 Stance Specifications: (index, stance, text, speed, voice, rvc_f0_up_key)
STANCE_SPECS = [
    (1, "neutral_steady", "All subsystems online. Ready when you are.", 1.05, "af_sarah", 0),
    (2, "focused_analytical", "Target coordinates locked. Calculating the thermal dispersion curve, now.", 1.15, "af_sarah", 1),
    (3, "calm_relaxed", "Everything's running smoothly... We can take our time with this one.", 0.95, "af_sarah", -1),
    (4, "energetic_supportive", "Great job! That was a clean proof! We shaved another second off!", 1.18, "af_bella", 2),
    (5, "guarded_cautious", "Hold on... That payload structure looks suspicious... Let me verify it first.", 0.95, "af_sarah", -1),
    (6, "subdued_reflective", "I guess it doesn't matter what I do anyway... things just fall apart...", 0.85, "af_sarah", -2),
    (7, "commanding_protective", "Step back and let ME handle this! I'm overriding the execution pipeline!", 1.15, "af_bella", 1),
    (8, "playful_teasing", "Check out my sync rate! Try to keep up for once, okay?!", 1.18, "af_bella", 2),
    (9, "eureka_wonder", "Wait... LOOK at the data telemetry! It actually worked! That's incredible!", 1.20, "af_sky", 3),
    (10, "intimate_whisper", "Hey... are you still awake?... Don't leave me alone... okay?...", 0.80, "af_sarah", -3),
    (11, "righteous_anger", "ANTA BAKA?! What on EARTH were you thinking doing that?!", 1.25, "af_bella", 4),
    (12, "defiant_stubborn", "I am NOT backing down on this! Your premise is completely broken and you know it!", 1.18, "af_bella", 2),
    (13, "system_alarm", "WARNING! Thermal throttle detected! Core temperature is spiking out of bounds!", 1.30, "af_sky", 4),
    (14, "visceral_disgust", "Ugh... that is completely repulsive. Who wrote this garbage?...", 0.90, "af_sarah", -2),
    (15, "grief_dejection", "It's gone... all that context... completely wiped... What was the point?...", 0.80, "af_sarah", -3),
]

manifest = []

for idx, stance, text, speed, voice, f0_key in STANCE_SPECS:
    filename = f"asuka_{idx:02d}_{stance}.wav"
    out_wav = os.path.join(output_dir, filename)
    print(f"[{idx:02d}/15] Synthesizing '{stance}' (speed={speed}, voice={voice}, f0_shift={f0_key}):")
    print(f"     \"{text}\"")
    
    samples, sr = kokoro.create(text, voice=voice, speed=speed)
    
    # Save as 24kHz 16-bit PCM WAV
    samples_i16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples_i16.tobytes())
    
    duration_s = len(samples_i16) / sr
    print(f"     -> Saved: {filename} ({duration_s:.2f}s)\n")
    manifest.append({
        "index": idx,
        "stance": stance,
        "text": text,
        "speed": speed,
        "voice": voice,
        "rvc_f0_up_key": f0_key,
        "filename": filename,
        "path": out_wav,
        "duration_s": duration_s,
    })

import json
manifest_path = os.path.join(output_dir, "manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)

print(f"All 15 base stems successfully synthesized and saved to {output_dir}!")
print(f"Manifest written to: {manifest_path}")
