import urllib.request
import json

grammar = """
root ::= ws call ws
call ::= "(" ws prim-op (ws-plus arg)* ws ")"
prim-op ::= [a-zA-Z][a-zA-Z0-9_-]*
arg ::= atom | call
atom ::= hole | keyword | var | int | boolean
var ::= "input" | "grid" | "bg" | "obj"
hole ::= "?hole-conn" | "?hole-axis" | "?hole-color" | "?hole-int" | "?hole-key" | "?hole-bool"
keyword ::= ":" [a-zA-Z][a-zA-Z0-9_-]*
int ::= "-"? [0-9]+
boolean ::= "#t" | "#f"
ws ::= [ \t\n\r]*
ws-plus ::= [ \t\n\r]+
"""

prompts = [
    "Transform input by reflecting it across an axis to complete its symmetry. Use complete-symmetry with :axis ?hole-axis.",
    "Extract the bounding box content of input grid using crop-to-content.",
    "Fill all enclosed background holes in input using fill-holes with fill color ?hole-color.",
    "Sort the objects extracted from input using sort-objects by :key ?hole-key."
]

for p in prompts:
    payload = {
        "messages": [
            {"role": "system", "content": "You are a formal program synthesis engine. Emit a single concise MicroScheme sketch expression transforming input. Do NOT write lambdas or definitions. Only emit the direct primitive call expression."},
            {"role": "user", "content": p}
        ],
        "grammar": grammar,
        "max_tokens": 48,
        "temperature": 0.1,
        "chat_template_kwargs": {"enable_thinking": False}
    }

    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print(f"Prompt: {p[:50]}...")
        print("  -> Output:", res["choices"][0]["message"]["content"])
        print()
