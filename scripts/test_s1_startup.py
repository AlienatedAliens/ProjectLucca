import subprocess
import time

import httpx

cmd = [
    r"C:\ProjectLucca\app\llama-server\llama-server.exe",
    "--model",
    r"C:\ProjectLucca\models\llm\ultravox-v0_5-llama-3_1-8b-Q6_K.gguf",
    "--mmproj",
    r"C:\ProjectLucca\models\llm\mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf",
    "--n-gpu-layers",
    "99",
    "--ctx-size",
    "8192",
    "--cache-type-k",
    "q8_0",
    "--cache-type-v",
    "q8_0",
    "--parallel",
    "1",
    "--flash-attn",
    "--host",
    "127.0.0.1",
    "--port",
    "8080",
    "--no-webui",
    "--jinja",
    "--log-format",
    "json",
]

print("Launching llama-server...")
t0 = time.time()
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

ready = False
for _ in range(120):
    try:
        r = httpx.get("http://127.0.0.1:8080/health", timeout=1.0)
        if r.status_code == 200:
            ready = True
            break
    except Exception:
        pass
    time.sleep(0.5)

load_time = time.time() - t0
print(f"Server ready: {ready} in {load_time:.2f}s")

if ready:
    print("Health check status:", httpx.get("http://127.0.0.1:8080/health").json())

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
