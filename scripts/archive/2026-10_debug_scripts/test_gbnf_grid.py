import httpx
import json

grammar = r"""
root ::= ws "[" ws row-list ws "]" ws
row-list ::= row (ws "," ws row)*
row ::= "[" ws int-list ws "]"
int-list ::= [0-9]+ (ws "," ws [0-9]+)*
ws ::= [ \t\n\r]*
"""

client = httpx.Client(timeout=30.0)
payload = {
    "messages": [{"role": "user", "content": "Output a 3x3 grid of zeros with a 2 in the center as JSON."}],
    "grammar": grammar.strip(),
    "max_tokens": 100,
    "temperature": 0.1,
    "chat_template_kwargs": {"enable_thinking": False}
}

resp = client.post("http://127.0.0.1:8080/v1/chat/completions", json=payload)
print("STATUS:", resp.status_code)
data = resp.json()
print("CONTENT:")
print(data["choices"][0]["message"]["content"])
try:
    parsed = json.loads(data["choices"][0]["message"]["content"])
    print("PARSED CLEANLY AS JSON:", parsed)
except Exception as e:
    print("PARSE ERROR:", e)
