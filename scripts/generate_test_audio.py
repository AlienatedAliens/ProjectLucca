import wave
from pathlib import Path

import kokoro_onnx
import numpy as np

fixtures_dir = Path(r"C:\projects\ProjectLucca\tests\fixtures\audio_tool_calls")
fixtures_dir.mkdir(parents=True, exist_ok=True)

model_path = r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx"
voices_path = r"C:\ProjectLucca\models\tts\voices-v1.0.bin"
tts = kokoro_onnx.Kokoro(model_path, voices_path)

prompts = [
    ("calc_01", "Open the calculator."),
    ("calc_02", "Launch the calculator app please."),
    ("calc_03", "Can you open calculator?"),
    ("calc_04", "Start the calculator for me."),
    ("notepad_01", "Open notepad."),
    ("notepad_02", "Please launch notepad."),
    ("notepad_03", "Can you open notepad?"),
    ("notepad_04", "Start notepad."),
    ("terminal_01", "Open the terminal."),
    ("terminal_02", "Launch the command prompt."),
    ("terminal_03", "Can you open terminal?"),
    ("terminal_04", "Start PowerShell."),
    ("browser_01", "Open the browser."),
    ("browser_02", "Launch Chrome please."),
    ("browser_03", "Can you open Edge?"),
    ("browser_04", "Start the web browser."),
    ("taskmgr_01", "Open task manager."),
    ("taskmgr_02", "Launch task manager please."),
    ("taskmgr_03", "Can you open task manager?"),
    ("taskmgr_04", "Start task manager."),
]


def resample_24k_to_16k(audio_24k: np.ndarray) -> np.ndarray:
    n_samples_16k = int(len(audio_24k) * 16000 / 24000)
    x_old = np.linspace(0, 1, len(audio_24k))
    x_new = np.linspace(0, 1, n_samples_16k)
    return np.interp(x_new, x_old, audio_24k).astype(np.float32)


print(f"Generating {len(prompts)} fixture clips...")
for key, text in prompts:
    wav_path = fixtures_dir / f"{key}.wav"
    if not wav_path.exists():
        samples, sr = tts.create(text, voice="af_heart", speed=1.0)
        samples_16k = resample_24k_to_16k(samples)
        # Convert float32 [-1, 1] to int16
        pcm_16 = (np.clip(samples_16k, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_16.tobytes())
        print(f"  Generated {wav_path.name} ({len(pcm_16) / 16000:.2f}s)")
    else:
        print(f"  {wav_path.name} already exists")

print("All audio fixtures ready!")
