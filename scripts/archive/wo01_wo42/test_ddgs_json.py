from ddgs import DDGS
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

query = "Beverly Ann F. Quintos Philippines Judge"
results = []

try:
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=5):
            results.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", "")
            })
except Exception as e:
    print(f"Error: {e}")

print(f"Count: {len(results)}")
print(json.dumps(results, indent=2))
