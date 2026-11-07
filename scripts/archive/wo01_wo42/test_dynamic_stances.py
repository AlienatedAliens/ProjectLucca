import sys
import base64
import wave
from pathlib import Path

sys.path.insert(0, r"C:\projects\projectlucca\src")
from lucca.speech.cosyvoice_client import CosyVoice3Client, format_cosyvoice_instruct

c = CosyVoice3Client.get_instance()
assert c.ping(), "CosyVoice 3 is not online"

stances = [
    ("playful_teasing", "playful, witty, tsundere teasing", "What are you staring at? Have you never seen a real genius before?"),
    ("righteous_anger", "indignant, sharp, fierce reprimand", "Anta baka! How many times do I have to tell you to pay attention!"),
]

for name, cadence, text in stances:
    inst = format_cosyvoice_instruct("Asuka", cadence, profile="asuka")
    print(f"\n--- Testing Stance: {name} ---")
    print(f"Instruct: {inst}")
    res = c.synthesize(text, instruct=inst, profile="asuka", direct_ring=False)
    assert res.get("status") == "ok", res
    pcm = base64.b64decode(res["audio_b64"])
    out_f = Path(rf"C:\ProjectLucca\models\tts\samples\asuka_{name}.wav")
    with wave.open(str(out_f), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    dur = len(pcm) / (2 * 24000)
    print(f"Generated {dur:.2f}s audio in {res['elapsed_ms']:.1f}ms -> {out_f.name}")
