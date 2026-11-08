#!/usr/bin/env python3
"""Live Vision Verification for Gemma 4 12B + mmproj."""

import base64
import io
import json
import time
import urllib.request
from PIL import Image, ImageDraw, ImageFont

# 1. Create a synthetic test image with text, shapes, and numbers
img = Image.new("RGB", (400, 200), color=(255, 255, 255))
draw = ImageDraw.Draw(img)

# Draw shapes
draw.rectangle([20, 30, 80, 90], fill=(66, 133, 244), outline=(0, 0, 0))  # Blue rectangle
draw.ellipse([110, 30, 170, 90], fill=(234, 67, 53), outline=(0, 0, 0))   # Red circle
draw.polygon([(230, 30), (200, 90), (260, 90)], fill=(52, 168, 83), outline=(0, 0, 0))  # Green triangle

# Draw text
draw.text((20, 120), "PROJECT LUCCA VLM TEST", fill=(0, 0, 0))
draw.text((20, 150), "TARGET NUMBER: 42", fill=(200, 0, 0))

# Encode to JPEG base64
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=90)
img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

# 2. Build OpenAI multimodal payload
payload = {
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Look closely at this image. Answer these 3 questions:\n"
                        "1. What shapes and colors do you see on the top row?\n"
                        "2. What text is written across the image?\n"
                        "3. What is the target number?"
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                },
            ],
        }
    ],
    "max_tokens": 512,
    "temperature": 0.0,
    "chat_template_kwargs": {"enable_thinking": False},
}

print("Sending multimodal query to http://127.0.0.1:8080/v1/chat/completions ...")
t0 = time.perf_counter()
req = urllib.request.Request(
    "http://127.0.0.1:8080/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)

with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    t_elapsed = time.perf_counter() - t0
    msg = data["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning_content") or ""

print(f"\nResponse received in {t_elapsed:.2f}s:")
print("=" * 60)
print(content)
print("=" * 60)
