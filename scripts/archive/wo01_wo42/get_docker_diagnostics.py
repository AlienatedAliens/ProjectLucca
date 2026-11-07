import subprocess
import json

# Docker inspect lucca-file-sandbox
try:
    raw = subprocess.check_output(["wsl", "-d", "Ubuntu", "docker", "inspect", "lucca-file-sandbox"]).decode()
    insp = json.loads(raw)[0]
    print("=== DOCKER CONTAINER INSPECT ===")
    print(f"Container ID: {insp.get('Id')}")
    print(f"Created: {insp.get('Created')}")
    print(f"StartedAt: {insp.get('State', {}).get('StartedAt')}")
    print(f"FinishedAt: {insp.get('State', {}).get('FinishedAt')}")
    print(f"Image ID: {insp.get('Image')}")
except Exception as e:
    print("Failed to inspect container:", e)

# Docker image inspect lucca/file-sandbox:latest
try:
    raw_img = subprocess.check_output(["wsl", "-d", "Ubuntu", "docker", "image", "inspect", "lucca/file-sandbox:latest"]).decode()
    img_insp = json.loads(raw_img)[0]
    print("\n=== DOCKER IMAGE INSPECT ===")
    print(f"Image ID: {img_insp.get('Id')}")
    print(f"RepoDigests: {img_insp.get('RepoDigests')}")
    print(f"Created: {img_insp.get('Created')}")
except Exception as e:
    print("Failed to inspect image:", e)

# Python and SymPy version inside container
try:
    py_ver = subprocess.check_output(["wsl", "-d", "Ubuntu", "docker", "exec", "lucca-file-sandbox", "python3", "-c", "import sys, sympy; print(f'Python: {sys.version}\\nSymPy: {sympy.__version__}')"]).decode().strip()
    print("\n=== VERSIONS INSIDE CONTAINER ===")
    print(py_ver)
except Exception as e:
    print("Failed to get python/sympy version:", e)
