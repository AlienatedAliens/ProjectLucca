import sys
from pathlib import Path
import soundfile as sf
import whisper

sys.path.insert(0, r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, r"C:\ProjectLucca\app\CosyVoice\third_party\Matcha-TTS")
sys.path.insert(0, r"C:\Projects\ProjectLucca\src")

from cosyvoice.cli.cosyvoice import CosyVoice3

MODEL_DIR = r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512"
STEM_WAV = r"C:\Projects\ProjectLucca\models\tts\references\asuka\harvested\asuka_023_focused_analytical_in_japanese_they_do_actually.wav"
STEM_TEXT = "In Japanese they do actually say when you listen to the Japanese version, you can hear me"
TARGET_TEXT = "Systems nominal. I am online and ready to work."

print("Loading CosyVoice3...")
cv3 = CosyVoice3(MODEL_DIR, fp16=True)

whisper_model = whisper.load_model("base.en")

print("\n--- Test 1: inference_zero_shot with matched prompt text ---")
prompt_full = f"You are a helpful assistant.<|endofprompt|>{STEM_TEXT}"
for i, out in enumerate(cv3.inference_zero_shot(TARGET_TEXT, prompt_full, STEM_WAV, stream=False)):
    wav = out["tts_speech"].squeeze().cpu().numpy()
    sf.write("scripts/test_zero_shot.wav", wav, 24000)
    res = whisper_model.transcribe("scripts/test_zero_shot.wav")
    print(f"Zero-shot transcript: '{res['text'].strip()}' (dur={len(wav)/24000:.2f}s)")

print("\n--- Test 2: inference_cross_lingual (no prompt text required) ---")
target_full = f"You are a helpful assistant.<|endofprompt|>{TARGET_TEXT}"
for i, out in enumerate(cv3.inference_cross_lingual(target_full, STEM_WAV, stream=False)):
    wav = out["tts_speech"].squeeze().cpu().numpy()
    sf.write("scripts/test_cross_lingual.wav", wav, 24000)
    res = whisper_model.transcribe("scripts/test_cross_lingual.wav")
    print(f"Cross-lingual transcript: '{res['text'].strip()}' (dur={len(wav)/24000:.2f}s)")

print("\n--- Test 3: inference_instruct2 with minimal header ---")
min_instruct = "You are a helpful assistant.<|endofprompt|>"
for i, out in enumerate(cv3.inference_instruct2(TARGET_TEXT, min_instruct, STEM_WAV, stream=False)):
    wav = out["tts_speech"].squeeze().cpu().numpy()
    sf.write("scripts/test_instruct_min.wav", wav, 24000)
    res = whisper_model.transcribe("scripts/test_instruct_min.wav")
    print(f"Instruct min transcript: '{res['text'].strip()}' (dur={len(wav)/24000:.2f}s)")
