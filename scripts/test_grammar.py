import urllib.request
import json

payload = {
    "messages": [{"role": "user", "content": "Compute 2 + 2 in python"}],
    "max_tokens": 100,
    "temperature": 0.0,
    "grammar": 'root ::= "print(" [0-9]+ ")"'
}

req = urllib.request.Request(
    "http://127.0.0.1:8080/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.loads(resp.read().decode("utf-8"))
        print("Response with grammar:\n", repr(d["choices"][0]["message"]["content"]))
except Exception as e:
    print("Grammar request error:", e)
