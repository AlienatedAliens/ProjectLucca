import httpx

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# In curl, curl sent the request, received 307 with Set-Cookie: YBV=... and Location: /_bv/v.gif?...
# Then curl requested /_bv/v.gif?... WITH the YBV cookie!
# Then Yahoo responded to the gif with 307 Location: /search?p=... WITH the YBV cookie!
# Then curl requested /search?p=... WITH the YBV cookie and got 200!

client = httpx.Client(headers=headers)
r1 = client.get("https://search.yahoo.com/search?p=Beverly+Ann+F.+Quintos+Philippines+Judge", follow_redirects=False)
print("Step 1:", r1.status_code, "Cookies:", dict(client.cookies), "Location:", r1.headers.get("location"))

# Next request to location
if r1.status_code == 307:
    loc1 = r1.headers.get("location")
    if loc1.startswith("/"):
        loc1 = "https://search.yahoo.com" + loc1
    r2 = client.get(loc1, follow_redirects=False)
    print("Step 2:", r2.status_code, "Cookies:", dict(client.cookies), "Location:", r2.headers.get("location"))
    
    if r2.status_code == 307:
        loc2 = r2.headers.get("location")
        if loc2.startswith("/"):
            loc2 = "https://search.yahoo.com" + loc2
        r3 = client.get(loc2, follow_redirects=False)
        print("Step 3:", r3.status_code, "Length:", len(r3.text))
        print("Has Quintos?", "quintos" in r3.text.lower())
