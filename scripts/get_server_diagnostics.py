import subprocess
import json
import hashlib
import glob

# 1. Process commandline of llama-server
try:
    ps_cmd = 'Get-CimInstance Win32_Process -Filter "name=\'llama-server.exe\'" | Select-Object -ExpandProperty CommandLine'
    out = subprocess.check_output(['powershell', '-Command', ps_cmd]).decode().strip()
    print("=== LLAMA-SERVER COMMAND LINE ===")
    print(out)
except Exception as e:
    print("Failed to get llama-server cmdline:", e)

# 2. JSON request payload for problem 1
prob1 = json.load(open("logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json"))[0]
prompt1 = (
    "You are a competition mathematician and computer algebra expert. Solve the following mathematical problem by writing a clean, self-contained Python script using SymPy, math, or numerical iteration.\n\n"
    f"Problem: {prob1['problem']}\n\n"
    "CRITICAL REQUIREMENTS:\n"
    "1. Put all code inside a single ```python ... ``` block.\n"
    "2. The script must explicitly compute the answer and print ONLY the final answer on stdout using print(answer).\n"
    "3. Do not print intermediate derivations, labels, units, or explanations. Just print the final result.\n"
    "4. Keep the script concise (< 30 lines) and avoid non-standard libraries."
)
payload1 = {
    "messages": [{"role": "user", "content": prompt1}],
    "max_tokens": 768,
    "temperature": 0.0,
    "seed": 42,
    "chat_template_kwargs": {"enable_thinking": False},
}
print("\n=== JSON REQUEST PAYLOAD (PROBLEM 1) ===")
print(json.dumps(payload1, indent=2))
prompt_sha = hashlib.sha256(prompt1.encode("utf-8")).hexdigest()
print(f"\nPROMPT TEXT SHA-256: {prompt_sha}")

# 3. Config metadata in historical checkpoint report
print("\n=== HISTORICAL CHECKPOINT METADATA ===")
rpt = glob.glob("logs/test_reports/modern_benchmarks_2024_*v1.3-final-fresh-500.json")
if rpt:
    d = json.load(open(rpt[0]))
    for k, v in d.items():
        if k != "benchmarks":
            print(f"{k}: {v}")
