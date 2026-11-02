import base64
import io
import httpx
from PIL import Image

# Create a small 3x3 RGB image
img = Image.new("RGB", (30, 30), color=(255, 0, 0))
buf = io.BytesIO()
img.save(buf, format="PNG")
img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
data_uri = f"data:image/png;base64,{img_b64}"

payload = {
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What color is this image?"},
                {"type": "image_url", "image_url": {"url": data_uri}}
            ]
        }
    ],
    "max_tokens": 100,
    "temperature": 0.1,
    "chat_template_kwargs": {"enable_thinking": False}
}

try:
    resp = httpx.post("http://127.0.0.1:8080/v1/chat/completions", json=payload, timeout=15.0)
    print("Status code:", resp.status_code)
    data = resp.json()
    print("Response choice:", data.get("choices", [{}])[0].get("message", {}).get("content"))
except Exception as e:
    print("Vision query error:", type(e).__name__, e)
