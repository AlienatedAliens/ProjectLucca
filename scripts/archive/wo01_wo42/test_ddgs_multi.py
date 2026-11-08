from ddgs import DDGS
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

queries = [
    "Beverly Ann F. Quintos Philippines Judge",
    "Latest Python release 2026",
    "Mistral NeMo 12B instruct context size",
    "Chrono Trigger Lucca character lore"
]

with DDGS() as ddgs:
    for q in queries:
        print(f"--- Query: {q} ---")
        try:
            results = list(ddgs.text(q, max_results=3))
            print(f"Got {len(results)} results:")
            for r in results:
                print(f"  * {r['title']} ({r['href'][:50]}...)")
                print(f"    {r['body'][:120]}...")
        except Exception as e:
            print(f"Failed: {e}")
        print()
