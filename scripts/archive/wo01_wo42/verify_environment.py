import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_system_ram_gb() -> tuple[float, float]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return stat.ullTotalPhys / (1024**3), stat.ullAvailPhys / (1024**3)


def check_gpu_mshybrid() -> tuple[bool, str]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False, "nvidia-smi not found in PATH"
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,display_active",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [l.strip() for l in res.stdout.strip().splitlines() if l.strip()]
        if not lines:
            return False, "No GPU reported by nvidia-smi"
        used, total, disp = [part.strip() for part in lines[0].split(",")]
        used_mb = float(used)
        total_mb = float(total)
        disp_active = disp.lower() in ("enable", "enabled", "on", "true", "1")
        if used_mb < 300 and not disp_active:
            return (
                True,
                f"dGPU RTX 5080 Laptop VRAM used: {used_mb:.0f} MB / {total_mb:.0f} MB (Display: Off, MSHybrid verified)",
            )
        elif used_mb < 500:
            return (
                True,
                f"dGPU VRAM used: {used_mb:.0f} MB / {total_mb:.0f} MB (Display: {'On' if disp_active else 'Off'})",
            )
        else:
            return (
                False,
                f"dGPU VRAM used: {used_mb:.0f} MB (Warning: >500 MB used; possible discrete-GPU mode)",
            )
    except Exception as e:
        return False, f"nvidia-smi error: {e}"


def check_openvino() -> tuple[bool, list[str] | str]:
    try:
        import openvino as ov

        core = ov.Core()
        devices = list(core.available_devices)
        return True, devices
    except ImportError:
        return False, "OpenVINO not installed in current environment"
    except Exception as e:
        return False, str(e)


def check_wslconfig() -> tuple[bool, bool, list[str]]:
    wsl_path = Path(os.environ.get("USERPROFILE", "")) / ".wslconfig"
    if not wsl_path.exists():
        return False, False, ["Missing .wslconfig"]
    content = wsl_path.read_text(encoding="utf-8")
    checks = []
    clamped = "memory=4608MB" in content
    checks.append(f"memory=4608MB: {'[OK]' if clamped else '[FAIL]'}")
    checks.append(f"pageReporting=true: {'[OK]' if 'pageReporting=true' in content else '[FAIL]'}")
    checks.append(
        f"autoMemoryReclaim=gradual: {'[OK]' if 'autoMemoryReclaim=gradual' in content else '[FAIL]'}"
    )
    checks.append(f"networkingMode=nat: {'[OK]' if 'networkingMode=nat' in content else '[FAIL]'}")
    all_ok = clamped and "pageReporting=true" in content and "autoMemoryReclaim=gradual" in content
    return True, all_ok, checks


def check_docker_ce() -> tuple[bool, str]:
    try:
        res = subprocess.run(
            [
                "wsl",
                "-d",
                "Ubuntu",
                "-e",
                "docker",
                "info",
                "--format",
                "{{.ServerVersion}} (Memory: {{.MemTotal}} bytes)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return True, f"Docker CE active: {res.stdout.strip()}"
        return False, f"docker info failed (exit code {res.returncode}): {res.stderr.strip()}"
    except Exception as e:
        return False, f"Error reaching Docker in WSL: {e}"


def check_sqlite_vec() -> tuple[bool, str]:
    try:
        import sqlite3

        import sqlite_vec

        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        vec_ver = conn.execute("SELECT vec_version()").fetchone()[0]
        # Test FTS5 in same connection
        conn.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(c);")
        conn.execute("INSERT INTO fts_probe VALUES ('test');")
        match = conn.execute("SELECT * FROM fts_probe WHERE fts_probe MATCH 'test'").fetchall()
        if match:
            return True, f"sqlite-vec {vec_ver} + FTS5 successfully loaded"
        return False, "FTS5 query failed"
    except Exception as e:
        return False, f"sqlite-vec / FTS5 failed: {e}"


def check_lucca_home() -> tuple[bool, list[str]]:
    home = Path(os.environ.get("LUCCA_HOME", r"C:\ProjectLucca"))
    required_dirs = [
        "app",
        "config",
        "models",
        "data",
        "workspace",
        "inbox",
        "logs",
        "cache",
        "tmp",
    ]
    missing = []
    for d in required_dirs:
        if not (home / d).is_dir():
            missing.append(d)
    if not missing:
        return True, [
            f"{home} layout complete ({len(required_dirs)}/{len(required_dirs)} dirs exist)"
        ]
    return False, [f"Missing subdirectories in {home}: {missing}"]


def main():
    print("=" * 65)
    print("  PROJECT LUCCA — SYSTEM & ENVIRONMENT DIAGNOSTICS")
    print("=" * 65)

    all_passed = True

    # 1. Host Memory
    total_ram, avail_ram = get_system_ram_gb()
    print(f"\n[1] HOST PHYSICAL RAM:")
    print(f"    - Total Physical RAM: {total_ram:.2f} GB")
    print(f"    - Available RAM:      {avail_ram:.2f} GB")
    if total_ram >= 15.0:
        print("    [+] OK: 16GB physical RAM verified.")
    else:
        print("    [!] WARNING: Less than 16GB total RAM detected.")
        all_passed = False

    # 2. GPU Mode & Baseline VRAM
    gpu_ok, gpu_msg = check_gpu_mshybrid()
    print(f"\n[2] GPU & MSHYBRID MODE:")
    if gpu_ok:
        print(f"    [+] {gpu_msg}")
    else:
        print(f"    [!] {gpu_msg}")
        all_passed = False

    # 3. WSL2 Clamping Status
    wsl_exists, wsl_ok, wsl_details = check_wslconfig()
    print(f"\n[3] WSL2 CONFIGURATION (.wslconfig):")
    if wsl_exists:
        for detail in wsl_details:
            print(f"    - {detail}")
        if wsl_ok:
            print("    [+] Canonical Lucca .wslconfig clamping verified.")
        else:
            print("    [!] WARNING: Non-canonical .wslconfig settings detected.")
            all_passed = False
    else:
        print("    [!] WARNING: .wslconfig not found!")
        all_passed = False

    # 4. Docker CE inside Ubuntu WSL2
    docker_ok, docker_msg = check_docker_ce()
    print(f"\n[4] DOCKER CE (inside Ubuntu WSL2):")
    if docker_ok:
        print(f"    [+] {docker_msg}")
    else:
        print(f"    [!] {docker_msg}")
        all_passed = False

    # 5. Python Runtime & Extensions
    vec_ok, vec_msg = check_sqlite_vec()
    print(f"\n[5] PYTHON RUNTIME & EXTENSIONS:")
    print(f"    - Python Version: {sys.version.split()[0]}")
    print(f"    - Executable:     {sys.executable}")
    if vec_ok:
        print(f"    [+] {vec_msg}")
    else:
        print(f"    [!] {vec_msg}")
        all_passed = False

    # 6. OpenVINO & NPU Accelerators
    ov_ok, ov_devs = check_openvino()
    print(f"\n[6] OPENVINO & ACCELERATORS:")
    if ov_ok and isinstance(ov_devs, list):
        print(f"    - Available Devices: {ov_devs}")
        if "NPU" in ov_devs:
            print("    [+] Intel NPU DETECTED and accessible via OpenVINO on Windows!")
        else:
            print("    [!] NPU not in device list.")
            all_passed = False
    else:
        print(f"    [!] OpenVINO status: {ov_devs}")
        all_passed = False

    # 7. LUCCA_HOME Layout
    layout_ok, layout_msgs = check_lucca_home()
    print(f"\n[7] RUNTIME FILESYSTEM LAYOUT:")
    for msg in layout_msgs:
        print(f"    - {msg}")
    if layout_ok:
        print("    [+] LUCCA_HOME directory structure ready.")
    else:
        print("    [!] LUCCA_HOME layout incomplete.")
        all_passed = False

    print("\n" + "=" * 65)
    if all_passed:
        print("  ALL DIAGNOSTICS GREEN: Ready for Phase 0 Spikes.")
    else:
        print("  ATTENTION: Some diagnostic checks flagged warnings/errors.")
    print("=" * 65)


if __name__ == "__main__":
    main()
