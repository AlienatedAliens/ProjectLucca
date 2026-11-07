import urllib.request, json, sys
q = "True or False: cats are mammals. Answer with just True or False."
payload = json.dumps({
    "messages": [{"role": "user", "content": q}],
    "max_tokens": 10, "temperature": 0.0,
    "chat_template_kwargs": {"enable_thinking": False}
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8080/v1/chat/completions",
    data=payload, headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=30) as r:
    d = json.loads(r.read())
    msg = d["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning_content") or ""
    print("Response:", repr(content[:80]))
    if content.strip():
        print("Model is generating. READY.")
    else:
        print("Empty response - model may not be producing tokens yet.")
        sys.exit(1)
