import sys
from pathlib import Path
import soundfile as sf
import whisper

sys.path.insert(0, r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, r"C:\ProjectLucca\app\CosyVoice\third_party\Matcha-TTS")

from cosyvoice.cli.cosyvoice import CosyVoice2, CosyVoice3

STEM_WAV = r"C:\Projects\ProjectLucca\models\tts\references\asuka\harvested\asuka_023_focused_analytical_in_japanese_they_do_actually.wav"
STEM_TEXT = "<|en|>In Japanese they do actually say when you listen to the Japanese version, you can hear me."
TARGET_TEXT = "<|en|>Systems nominal. I am online and ready to work."

whisper_model = whisper.load_model("base.en")

print("--- Testing CosyVoice2 with <|en|> tag ---")
cv2 = CosyVoice2(r"C:\ProjectLucca\app\CosyVoice\pretrained_models\CosyVoice2-0.5B", fp16=True)
for i, out in enumerate(cv2.inference_zero_shot(TARGET_TEXT, STEM_TEXT, STEM_WAV, stream=False)):
    wav = out["tts_speech"].squeeze().cpu().numpy()
    sf.write("scripts/test_cv2_en_tag.wav", wav, 24000)
    res = whisper_model.transcribe("scripts/test_cv2_en_tag.wav")
    print(f"CV2 transcript: '{res['text'].strip()}' (dur={len(wav)/24000:.2f}s)")
    break

print("\n--- Testing CosyVoice2 cross-lingual with <|en|> tag ---")
for i, out in enumerate(cv2.inference_cross_lingual(TARGET_TEXT, STEM_WAV, stream=False)):
    wav = out["tts_speech"].squeeze().cpu().numpy()
    sf.write("scripts/test_cv2_cross_en.wav", wav, 24000)
    res = whisper_model.transcribe("scripts/test_cv2_cross_en.wav")
    print(f"CV2 cross transcript: '{res['text'].strip()}' (dur={len(wav)/24000:.2f}s)")
    break
