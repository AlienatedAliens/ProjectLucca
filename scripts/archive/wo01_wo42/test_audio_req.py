import base64
from pathlib import Path

import httpx

wav_file = Path(r"C:\projects\ProjectLucca\tests\fixtures\audio_tool_calls\calc_01.wav")
wav_b64 = base64.b64encode(wav_file.read_bytes()).decode("utf-8")

payload = {
    "messages": [
        {
            "role": "user",
            "content": [{"type": "input_audio", "input_audio": {"data": wav_b64, "format": "wav"}}],
        }
    ],
    "max_tokens": 64,
    "temperature": 0.2,
}

print(f"Sending audio request ({len(wav_b64)} b64 chars)...")
r = httpx.post("http://127.0.0.1:8080/v1/chat/completions", json=payload, timeout=30.0)
print("Status:", r.status_code)
if r.status_code == 200:
    print("Response:", r.json()["choices"][0]["message"])
else:
    print("Error:", r.text)
