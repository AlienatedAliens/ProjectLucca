"""
Project Lucca — Hardware & Environment Diagnostic Script
Checks host RAM, CPU topology, OpenVINO NPU devices, and Python environment.
"""

import sys
import os
import ctypes
from pathlib import Path

def get_system_ram_gb() -> float:
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
    return stat.ullTotalPhys / (1024 ** 3), stat.ullAvailPhys / (1024 ** 3)

def check_openvino():
    try:
        import openvino as ov
        core = ov.Core()
        devices = core.available_devices
        return True, devices
    except ImportError:
        return False, "OpenVINO not installed in current environment"
    except Exception as e:
        return False, str(e)

def check_wslconfig():
    wsl_path = Path(os.environ.get("USERPROFILE", "")) / ".wslconfig"
    if wsl_path.exists():
        content = wsl_path.read_text(encoding="utf-8")
        clamped = "memory=4608MB" in content or "memory=" in content
        return True, clamped, content
    return False, False, ""

def main():
    print("=" * 60)
    print("  PROJECT LUCCA — HARDWARE & ENVIRONMENT DIAGNOSTICS")
    print("=" * 60)

    # 1. Host Memory
    total_ram, avail_ram = get_system_ram_gb()
    print(f"\n[1] HOST PHYSICAL RAM:")
    print(f"    - Total Physical RAM: {total_ram:.2f} GB")
    print(f"    - Available RAM:      {avail_ram:.2f} GB")
    if total_ram < 15.0:
        print("    [!] WARNING: Less than 16GB total RAM detected.")
    else:
        print("    [+] OK: 16GB physical RAM verified.")

    # 2. WSL2 Clamping Status
    wsl_exists, wsl_clamped, wsl_content = check_wslconfig()
    print(f"\n[2] WSL2 MEMORY CLAMP (.wslconfig):")
    if wsl_exists:
        print("    [+] .wslconfig found in user profile.")
        if wsl_clamped:
            print("    [+] Memory limit configured.")
        else:
            print("    [!] WARNING: memory= clamp not detected in .wslconfig!")
    else:
        print("    [!] WARNING: .wslconfig not found! Run scripts/setup_wslconfig.ps1")

    # 3. Python Runtime
    print(f"\n[3] PYTHON RUNTIME:")
    print(f"    - Version: {sys.version.split()[0]}")
    print(f"    - Executable: {sys.executable}")

    # 4. OpenVINO & NPU
    ov_ok, ov_devs = check_openvino()
    print(f"\n[4] OPENVINO & ACCELERATORS:")
    if ov_ok:
        print(f"    - Available Devices: {ov_devs}")
        if "NPU" in ov_devs:
            print("    [+] Intel NPU DETECTED and accessible via OpenVINO!")
        else:
            print("    [!] NPU not in device list. (Ensure Intel NPU drivers are installed on Windows)")
    else:
        print(f"    [!] OpenVINO status: {ov_devs}")

    print("\n" + "=" * 60)
    print("Diagnostics complete.")
    print("=" * 60)

if __name__ == "__main__":
    main()
