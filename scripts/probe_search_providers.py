import httpx
import re
import html
import urllib.parse
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

query = 'Beverly Ann F. Quintos Philippines Judge'

print("=== 1. DUCKDUCKGO POST TO html.duckduckgo.com/html/ ===")
try:
    with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
        r = client.post("https://html.duckduckgo.com/html/", data={"q": query})
        print(f"Status: {r.status_code}, Length: {len(r.text)}")
        print("Anomaly?", "anomaly" in r.text.lower())
        print("Quintos in text?", "quintos" in r.text.lower())
        if "quintos" in r.text.lower():
            # Extract results
            matches = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', r.text, re.DOTALL)
            print(f"Found {len(matches)} snippets")
            for m in matches[:3]:
                print("  SNIPPET:", html.unescape(re.sub(r'<[^>]+>', '', m)).strip()[:150])
except Exception as e:
    print("DDG POST failed:", e)

print("\n=== 2. BRAVE SEARCH ===")
try:
    with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
        r = client.get(f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}")
        print(f"Status: {r.status_code}, Length: {len(r.text)}")
        print("Quintos in text?", "quintos" in r.text.lower())
        if "quintos" in r.text.lower():
            # Extract Brave results
            snippets = re.findall(r'<div[^>]*class="snippet-description"[^>]*>(.*?)</div>', r.text, re.DOTALL)
            print(f"Found {len(snippets)} Brave snippets")
            for s in snippets[:3]:
                print("  BRAVE SNIPPET:", html.unescape(re.sub(r'<[^>]+>', '', s)).strip()[:150])
except Exception as e:
    print("Brave failed:", e)

print("\n=== 3. MOJEEK ===")
try:
    with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
        r = client.get(f"https://www.mojeek.com/search?q={urllib.parse.quote_plus(query)}")
        print(f"Status: {r.status_code}, Length: {len(r.text)}")
        print("Quintos in text?", "quintos" in r.text.lower())
        if "quintos" in r.text.lower():
            snippets = re.findall(r'<p class="s">(.*?)</p>', r.text, re.DOTALL)
            print(f"Found {len(snippets)} Mojeek snippets")
            for s in snippets[:3]:
                print("  MOJEEK SNIPPET:", html.unescape(re.sub(r'<[^>]+>', '', s)).strip()[:150])
except Exception as e:
    print("Mojeek failed:", e)

print("\n=== 4. SEARXNG / PUBLIC APIS ===")
for instance in [
    "https://searx.be/search?q={q}&format=json",
    "https://search.ononoki.org/search?q={q}&format=json",
    "https://baresearch.org/search?q={q}&format=json",
]:
    try:
        url = instance.format(q=urllib.parse.quote_plus(query))
        with httpx.Client(timeout=6.0, follow_redirects=True, headers=headers) as client:
            r = client.get(url)
            print(f"{instance[:30]}: status {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                print(f"  Found {len(results)} JSON results!")
                for res in results[:3]:
                    print("  TITLE:", res.get("title"))
                    print("  CONTENT:", res.get("content", "")[:150])
                break
    except Exception as e:
        print(f"  {instance[:30]} failed: {e}")

print("\n=== 5. DUCKDUCKGO INSTANT ANSWER API ===")
try:
    with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
        r = client.get(f"https://api.duckduckgo.com/?q={urllib.parse.quote_plus(query)}&format=json")
        print(f"Status: {r.status_code}, Length: {len(r.text)}")
        data = r.json()
        print("Abstract:", data.get("AbstractText"))
        print("Related topics count:", len(data.get("RelatedTopics", [])))
except Exception as e:
    print("DDG API failed:", e)
