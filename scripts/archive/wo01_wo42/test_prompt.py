import urllib.request, json, time, ast

def query_llm(prompt: str, max_tokens: int = 512) -> str:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": 42,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"].get("content") or ""

# Test Item 20: 1 + 2 + 3 - 4 + 5 + 6 with parentheses
problem = "The operations + and - are placed between the numbers 1, 2, 3, 4, 5, 6 as follows: 1 + 2 + 3 - 4 + 5 + 6. Parentheses are added to the expression. Find the minimum possible value of the resulting expression."

prompt_concise = f"""Write a concise, standalone Python script (< 25 lines) using itertools or sympy to solve this problem.
CRITICAL RULES:
1. Output ONLY a ```python ... ``` block.
2. DO NOT write commentary, explanations, or long comments.
3. Compute the result and print ONLY the final answer on the last line.

Problem: {problem}
"""

t0 = time.perf_counter()
res = query_llm(prompt_concise, max_tokens=512)
elapsed = time.perf_counter() - t0
print(f"Elapsed: {elapsed:.2f}s")
print("Response:\n", res)
