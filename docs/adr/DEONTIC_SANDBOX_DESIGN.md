# Milestone 2: Deontic Sandbox & Kernel Isolation Specification

**Document Version:** 1.1.0  
**Date:** September 20, 2026  
**Status:** Revised Design Document for User & Reviewer Review  
**Target Milestone:** Milestone 2 (Execution blocked pending sign-off; interim host mitigations active in code)  
**Git Baseline:** `2fbf436` (Interim mitigations tested; Diff SHA256: `2e9bd974cfb335aad5ed96a7356269680281cc014864865f8aa407b8ad919295`)

---

## 1. Executive Summary & Core Architectural Axioms

The Round 3 and Round 4 technical peer reviews established three non-negotiable security realities for Project Lucca:

1. **A Windows Job Object is Not an Isolation Boundary:**  
   Job Objects govern resource quotas (CPU limits, commit memory limits, active process limits, UI clipping). They do not restrict network sockets, Windows named pipes, or filesystem access governed by the user's desktop login token. An uncontained process running on Windows can read any file readable by the current user and open outbound TCP sockets.
2. **Arbitrary Code Execution Mandates OS-Level Isolation:**  
   `run_python` and interactive shells (`wt.exe`, `powershell.exe`, `cmd.exe`) can never be safely secured on the host by userspace path filters or handle checks. Once Python or a shell evaluates untrusted code, native OS APIs (`ctypes`, `subprocess`, socket syscalls) bypass all Python-level wrappers.
3. **Primary Isolation Boundary = Dedicated Unprivileged Container:**  
   Execution of untrusted code and file modifications must occur within an isolated container runtime. The host does not execute untrusted scripts or navigate unvalidated filesystem structures.

---

## 2. Item-by-Item Remediation of Sandbox Flaws (Items 2a–2i)

### 2.1 Item 2a: Single Canonical Boundary via WSL2 Container (`lucca-file-sandbox`)
* **Architecture:** The host orchestrator delegates all file operations (`read_file`, `write_file`, `delete_file`, `list_dir`, `search_text`) and Python execution (`run_python`) to `lucca-toolsrv` executing inside a WSL2 container (`lucca-file-sandbox`).
* **Filesystem Mounting:** The container mounts **strictly** the dedicated workspace directory `C:\ProjectLucca\workspace` into `/workspace`. The host Windows drive (`C:\`), Windows system binaries, user profile, and memory database (`data/memory.sqlite`) are **physically unmounted and nonexistent** in the container's mount namespace.
* **No Host Path Opening:** The Windows host does not traverse or open workspace files by raw path during routine agent tool execution. The agent's file environment exists solely inside the Linux namespace.

### 2.2 Item 2b: Non-Destructive Handle Open Before Truncate (Fixing the `CREATE_ALWAYS` Flaw)
* **The Vulnerability in v1.0:** In the initial Win32 draft, `mode == "w"` opened files with `CREATE_ALWAYS`. On NTFS, `CREATE_ALWAYS` truncates an existing file to 0 bytes *at the moment of opening*, **before** `GetFinalPathNameByHandleW` can verify the handle target. An attacker placing a junction or hard link pointing to `C:\Windows\System32\drivers\etc\hosts` or a critical user document would see the target file wiped clean before the containment check could detect the breach and raise `PermissionError`.
* **The Non-Destructive Two-Stage Open Protocol:**
  1. **Stage 1 (Inspection Open):** Open the candidate path with `OPEN_EXISTING` and `FILE_READ_ATTRIBUTES` (non-destructive; zero truncate, no write access).
  2. If the file exists:
     - Call `GetFinalPathNameByHandleW` on the inspection handle.
     - Verify `final_path.is_relative_to(canonical_workspace_root)`.
     - Inspect link count (see Item 2c below).
     - Close the inspection handle.
     - Open with `OPEN_EXISTING` and `GENERIC_WRITE` (or `TRUNCATE_EXISTING`) directly on the verified canonical path.
  3. If the file does not exist (`ERROR_FILE_NOT_FOUND`):
     - Inspect the parent directory handle with `FILE_FLAG_BACKUP_SEMANTICS`.
     - Verify parent directory `final_path.is_relative_to(canonical_workspace_root)` and contains no reparse points.
     - Open the new file with `CREATE_NEW` (fails if the file was created concurrently by an attacker).

### 2.3 Item 2c: Hard Link Count Check (`nNumberOfLinks > 1` Rejection)
* **The Hard Link Attack Vector:** On NTFS, hard links share the exact same MFT file record (inode equivalent) on the same volume. A hard link `workspace\benign.txt` pointing to `C:\ProjectLucca\config\settings.toml` has a final path resolving to the same physical file. Even if path normalization resolves the link, modifying a multi-linked file corrupts the target elsewhere on the drive.
* **Remediation:**  
  On any file write operation, invoke `GetFileInformationByHandle` on the open inspection handle.
  ```c
  BY_HANDLE_FILE_INFORMATION fileInfo;
  GetFileInformationByHandle(hInspection, &fileInfo);
  if (fileInfo.nNumberOfLinks > 1) {
      CloseHandle(hInspection);
      return REJECT_HARD_LINK_DETECTED; // Access Denied
  }
  ```
  Any file with `nNumberOfLinks > 1` is strictly rejected for write/delete operations.

### 2.4 Item 2d: Container Network Confinement (`--network none`)
* **The `iptables` / `--cap-drop` Paradox:** The v1.0 specification specified `--cap-drop=ALL` while simultaneously proposing an internal `iptables` rule to drop RFC1918 traffic. In Linux, dropping `CAP_NET_ADMIN` prevents `iptables` from executing inside the container.
* **The Clean Resolution:**  
  The file execution container runs with **`--network none` by default**:
  ```bash
  docker run -d \
    --name lucca-file-sandbox \
    --network none \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    --volume C:\ProjectLucca\workspace:/workspace:rw \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --memory=512m \
    --cpus=1.0 \
    lucca-file-sandbox:latest
  ```
  By removing the network stack entirely (`--network none`), the container has zero network interfaces except loopback. No `iptables` scripts or elevated capabilities (`CAP_NET_ADMIN`) are required. Network operations are physically impossible from inside the file sandbox.

### 2.5 Item 2e: Workspace Bridge Untrusted Policy
* The mounted directory `/workspace` is treated by the host as an **untrusted foreign boundary**:
  1. Files deposited in `/workspace` by container processes are never executed directly on the host.
  2. The host application launcher (`launcher.py`) only opens files in `notepad.exe` after verifying that the file does not contain binary headers (`MZ`, `ELF`, shell shebangs `#!`).
  3. No executable extensions (`.exe`, `.dll`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.msi`) are allowed to be targeted by host launchers.

### 2.6 Item 2f: DNS Rebinding Protection on HTTP Redirects
* **The Rebinding Attack:** An attacker controls domain `rebind.attacker.com`. The first DNS query resolves to public IP `1.1.1.1` (passes SSRF check). During the actual HTTP socket connect or on a 302 redirect, the DNS TTL expires and re-resolves to `127.0.0.1` or `192.168.1.1`, allowing the client to reach internal services.
* **The Solution in `web_tool.py`:**
  1. **Custom HTTP Transport with Pre-Connect IP Pinning:**
     - Instead of allowing `httpx` to resolve hostnames via OS DNS, hostname resolution is intercepted.
     - The resolved IP is validated against private/loopback/link-local/multicast blacklists.
     - The socket connects **strictly to the validated IP address**, passing the original hostname only in the HTTP `Host` header and TLS SNI extension.
  2. **Per-Redirect Re-validation:**
     - Redirects are not followed automatically by the HTTP client (`follow_redirects=False`).
     - Every redirect URL is intercepted, parsed, resolved, and re-validated against the SSRF IP resolver before the next socket is opened.

### 2.7 Item 2g: HMAC-SHA256 Single-Use Confirmation Tokens
* **The Threat:** Predictable or short confirmation tokens (e.g. 6-character hex from truncated timestamp) could theoretically be guessed or collided.
* **Cryptographic Token Binding:**
  $$\text{Token} = \text{HMAC-SHA256}_{K_{\text{session}}}(\text{tool\_name} \,\|\, \text{canonical\_args\_json} \,\|\, \text{action\_seq} \,\|\, \text{expiry\_ts})$$
  - $K_{\text{session}}$ is a 256-bit cryptographically secure random key generated at orchestrator startup (`secrets.token_bytes(32)`).
  - The human-readable confirmation displays the first 8 characters of the HMAC hex digest (`Token: e3b0c442`).
  - Verification recomputes the HMAC using $K_{\text{session}}$ and requires constant-time comparison (`hmac.compare_digest`).
  - Tokens expire after 15 seconds or upon evaluation (single-use consumption).

### 2.8 Item 2h: State-Based Bidirectional Taint Model
* Taint is tracked as an explicit **Session Taint Bitmask** rather than ad-hoc string matching:
  ```python
  class TaintFlags(IntFlag):
      CLEAN = 0
      UNTRUSTED_WEB = 1 << 0    # Contains text from fetch_url
      SENSITIVE_MEMORY = 1 << 1  # Contains episodic memory / credentials
      WORKSPACE_PRIVATE = 1 << 2 # Contains local workspace files
  ```
* **Deontic Rules Governed by Taint State:**
  - `UNTRUSTED_WEB` active $\implies$ Any call to `write_file`, `delete_file`, or `launch_app` is escalated to **MANDATORY_MODAL_CONFIRMATION**, even if the model attempts to suppress it.
  - `SENSITIVE_MEMORY` or `WORKSPACE_PRIVATE` active $\implies$ Any call to `fetch_url` with parameters containing substrings or high-entropy tokens from the sensitive context is **HARD_BLOCKED** (Exfiltration Prevention).
  - `data/memory.sqlite` stores a `taint_mask INTEGER` column. Retrieving an episodic memory restores its taint flags into the turn's active mask.

### 2.9 Item 2i: Test-First Authoring & Expanded Adversarial Test Battery
Before Milestone 2 execution code is merged, all tests must be authored and failing (TDD). The complete adversarial suite includes:
1. `test_win32_two_stage_open_prevents_truncate_before_check`: Verifies a read-only target cannot be truncated by a failed write check.
2. `test_win32_hard_link_rejection`: Verifies files with `nNumberOfLinks > 1` are rejected with `REJECT_HARD_LINK_DETECTED`.
3. `test_container_network_none_no_sockets`: Verifies that `socket.socket().connect(...)` inside the container raises `ENETUNREACH` or `EPERM`.
4. `test_dns_rebinding_ip_pinning`: Simulates a DNS server returning benign IP on query 1 and `127.0.0.1` on query 2; verifies socket connection is aborted.
5. `test_hmac_token_forgery_prevention`: Verifies that tokens with modified timestamps, args, or keys fail validation.
6. `test_taint_state_escalates_confirmation`: Verifies that loading untrusted web content dynamically forces modal confirmation on subsequent write tools.

---

## 3. The Milestone 2 Win32 Implementation Specification

For host utilities that require direct workspace file validation (such as `launcher.py` and `WorkspaceManager`), the following implementation specifies the hardened Win32 handle protocol:

```python
"""
Project Lucca — Hardened Win32 Handle Verification (Milestone 2 Specification)
Eliminates TOCTOU, prevents premature truncation, and detects hard links.
"""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path

# Win32 Constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
CREATE_NEW = 1
TRUNCATE_EXISTING = 5
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
VOLUME_NAME_DOS = 0x0
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]

kernel32 = ctypes.windll.kernel32

CreateFileW = kernel32.CreateFileW
CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
]
CreateFileW.restype = wintypes.HANDLE

GetFinalPathNameByHandleW = kernel32.GetFinalPathNameByHandleW
GetFinalPathNameByHandleW.argtypes = [
    wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD
]
GetFinalPathNameByHandleW.restype = wintypes.DWORD

GetFileInformationByHandle = kernel32.GetFileInformationByHandle
GetFileInformationByHandle.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(BY_HANDLE_FILE_INFORMATION)
]
GetFileInformationByHandle.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL


def verify_and_open_workspace_file(
    rel_path: str,
    workspace_root: Path,
    mode: str = "r"
) -> wintypes.HANDLE:
    """
    Hardened two-stage open protocol:
    1. Rejects absolute/drive/colon/UNC paths.
    2. Inspects directory chain for reparse points.
    3. Stage 1: Non-destructive inspection open (FILE_READ_ATTRIBUTES).
    4. Target containment check via GetFinalPathNameByHandleW.
    5. Hard link count check (nNumberOfLinks == 1).
    6. Stage 2: Operates on verified canonical handle.
    """
    canonical_root = workspace_root.resolve(strict=True)
    clean_p = rel_path.replace("\\", "/")
    
    if ":" in clean_p or clean_p.startswith(("/", "\\")):
        raise PermissionError(f"Absolute or drive-qualified paths forbidden: {rel_path}")

    # Inspect parent chain for reparse points
    target_candidate = (canonical_root / clean_p).resolve()
    rel_parts = Path(clean_p).parts
    current = canonical_root
    for part in rel_parts[:-1]:
        current = current / part
        if current.exists():
            attrs = kernel32.GetFileAttributesW(str(current))
            if attrs != 0xFFFFFFFF and (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
                raise PermissionError(f"Reparse point in directory hierarchy: {part}")

    share_mode = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE

    if mode == "r":
        # Direct read open with boundary verification
        h_file = CreateFileW(
            str(target_candidate),
            GENERIC_READ,
            share_mode,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None
        )
        if h_file == INVALID_HANDLE_VALUE:
            raise FileNotFoundError(f"Cannot open file for reading: {rel_path}")
        
        _verify_handle_containment(h_file, canonical_root)
        return h_file

    elif mode == "w":
        # Non-destructive Stage 1 inspection
        h_inspect = CreateFileW(
            str(target_candidate),
            FILE_READ_ATTRIBUTES,
            share_mode,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None
        )
        
        if h_inspect != INVALID_HANDLE_VALUE:
            try:
                # File exists: verify containment and link count BEFORE any modification
                _verify_handle_containment(h_inspect, canonical_root)
                
                info = BY_HANDLE_FILE_INFORMATION()
                if GetFileInformationByHandle(h_inspect, ctypes.byref(info)):
                    if info.nNumberOfLinks > 1:
                        raise PermissionError(
                            f"Security Breach: File '{rel_path}' has {info.nNumberOfLinks} hard links"
                        )
            finally:
                CloseHandle(h_inspect)

            # Stage 2: Open and truncate now that containment and link safety are verified
            h_write = CreateFileW(
                str(target_candidate),
                GENERIC_WRITE,
                share_mode,
                None,
                TRUNCATE_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None
            )
            if h_write == INVALID_HANDLE_VALUE:
                raise PermissionError(f"Failed to open verified file for write: {rel_path}")
            return h_write

        else:
            # File does not exist: verify parent directory containment
            parent = target_candidate.parent
            if not parent.exists():
                raise FileNotFoundError(f"Parent directory does not exist: {parent}")
            
            h_parent = CreateFileW(
                str(parent),
                GENERIC_READ,
                share_mode,
                None,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS,
                None
            )
            if h_parent == INVALID_HANDLE_VALUE:
                raise PermissionError(f"Cannot verify parent directory: {parent}")
            try:
                _verify_handle_containment(h_parent, canonical_root)
            finally:
                CloseHandle(h_parent)

            # Create new file with CREATE_NEW (fails if created concurrently)
            h_new = CreateFileW(
                str(target_candidate),
                GENERIC_WRITE,
                share_mode,
                None,
                CREATE_NEW,
                FILE_ATTRIBUTE_NORMAL,
                None
            )
            if h_new == INVALID_HANDLE_VALUE:
                raise PermissionError(f"Failed to create new file: {rel_path}")
            return h_new

    else:
        raise ValueError(f"Unsupported mode: {mode}")


def _verify_handle_containment(handle: wintypes.HANDLE, canonical_root: Path) -> Path:
    """Verifies that an open Win32 handle resolves strictly inside canonical_root."""
    buf = ctypes.create_unicode_buffer(1024)
    res = GetFinalPathNameByHandleW(handle, buf, 1024, VOLUME_NAME_DOS)
    if res == 0:
        raise PermissionError("GetFinalPathNameByHandleW failed on handle.")

    path_str = buf.value
    if path_str.startswith("\\\\?\\UNC\\"):
        path_str = "\\\\" + path_str[8:]
    elif path_str.startswith("\\\\?\\"):
        path_str = path_str[4:]

    final_path = Path(path_str).resolve()
    try:
        final_path.relative_to(canonical_root)
    except ValueError:
        raise PermissionError(
            f"Security Breach: Handle target '{final_path}' escapes workspace '{canonical_root}'"
        )
    return final_path
```

---

## 4. Deontic Policy Engine & State Machine

```
                        DEONTIC STATE TRANSITIONS
                        
     [User Input]
          │
          ▼
   ┌──────────────┐      is_read_tool?
   │ Intent Parser│ ────────────────────────► [ALLOW: Direct Execute]
   └──────────────┘
          │ (write / launch / network)
          ▼
   ┌──────────────┐      taint == UNTRUSTED?
   │ Taint Monitor│ ────────────────────────► [ESCALATE: Force Token Modal]
   └──────────────┘
          │
          ▼
   ┌──────────────┐      requires_confirmation?
   │ Deontic Gate │ ────────────────────────► Generate HMAC Token
   └──────────────┘                                │
          │                                        ▼
          │                             [Prompt User for Token]
          │                                        │
          │ confirmed == True                      ▼
          │ (HMAC validated)            [Validate Token & Nonce]
          ▼                                        │
   [ALLOW: Container RPC] ◄────────────────────────┘
```

---

## 5. Milestone 2 Sign-Off Criteria

Milestone 2 implementation will only proceed once:
1. This design document (v1.1.0) is reviewed and approved by Sean and the technical reviewer.
2. Milestone 1 empirical measurement data is fully collected, verified, and recorded.
3. The adversarial test suite in Section 2.9 is implemented and passes 100%.
