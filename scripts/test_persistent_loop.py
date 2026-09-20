import json
import subprocess
import time

in_container_code = """
import sys, json, time
from pathlib import Path
from lucca.sandbox.file_tool import SafeFileTool

tool = SafeFileTool(workspace_root=Path("/workspace"))
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        res = tool.list_dir("", recursive=False)
        out = json.dumps({"call_id": req.get("call_id"), "ok": True, "structured": res})
        sys.stdout.write(out + "\\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(json.dumps({"ok": False, "error": str(e)}) + "\\n")
        sys.stdout.flush()
"""

cmd = ["wsl", "-d", "Ubuntu", "--", "docker", "exec", "-i", "lucca-file-sandbox", "python3", "-c", in_container_code]

print("Launching persistent docker exec process...")
t_start = time.perf_counter()
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
launch_time_ms = (time.perf_counter() - t_start) * 1000.0
print(f"Process handle acquired in {launch_time_ms:.2f}ms")

times = []
print("\nTesting 20 sequential calls over persistent stream:")
for i in range(20):
    t0 = time.perf_counter()
    req = {"call_id": f"call-{i}"}
    p.stdin.write(json.dumps(req) + "\n")
    p.stdin.flush()
    line = p.stdout.readline()
    dt_ms = (time.perf_counter() - t0) * 1000.0
    times.append(dt_ms)
    data = json.loads(line)
    if i < 5 or i >= 18:
        print(f"Call {i:2d}: turnaround={dt_ms:.2f}ms ok={data.get('ok')}")

p.stdin.close()
p.wait(timeout=2)

times_sorted = sorted(times)
p50 = times_sorted[len(times) // 2]
p95 = times_sorted[int(len(times) * 0.95)]
p99 = times_sorted[int(len(times) * 0.99)]
print("\n" + "=" * 60)
print(f"PERSISTENT STREAM LATENCY PROFILE (N={len(times)}):")
print(f"Min:  {min(times):.2f} ms")
print(f"P50:  {p50:.2f} ms")
print(f"P95:  {p95:.2f} ms")
print(f"P99:  {p99:.2f} ms")
print(f"Max:  {max(times):.2f} ms")
print("=" * 60)
