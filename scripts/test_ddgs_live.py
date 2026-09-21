from ddgs import DDGS
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

query = "Beverly Ann F. Quintos Philippines Judge"
print(f"Querying ddgs for: {query}")

try:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
        print(f"ddgs found {len(results)} results!\n")
        for idx, r in enumerate(results, 1):
            print(f"{idx}. {r.get('title')}")
            print(f"   URL:  {r.get('href')}")
            print(f"   Body: {r.get('body')}")
            print()
except Exception as e:
    print(f"ddgs failed: {e}")
