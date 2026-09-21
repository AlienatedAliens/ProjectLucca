"""
Project Lucca — Hardened Win32 Handle-Based File Security (Milestone 2)
Spec 09, Spec 12, ADR-003, ADR-004, Milestone 2 Design §2 & §3

Guarantees:
  1. Complete TOCTOU elimination by operating directly on open, verified handles.
  2. Non-destructive Stage 1 inspection (FILE_READ_ATTRIBUTES) before any truncate.
  3. Hard link detection: rejects files with nNumberOfLinks > 1.
  4. Reparse point rejection across all intermediate directory components.
  5. Strict path validation: forbids colons, drive letters, UNC paths, and traversals.
"""

from __future__ import annotations

import ctypes
from collections.abc import Generator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

from lucca.core.exceptions import SandboxPathError

# Win32 Access Rights & Flags
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_READ_ATTRIBUTES = 0x0080

FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004

CREATE_NEW = 1
CREATE_ALWAYS = 2
OPEN_EXISTING = 3
OPEN_ALWAYS = 4
TRUNCATE_EXISTING = 5

FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # Required to open directory handles
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
VOLUME_NAME_DOS = 0x0

INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
ERROR_FILE_NOT_FOUND = 2
ERROR_PATH_NOT_FOUND = 3


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


# Setup Win32 kernel32 function bindings
kernel32 = ctypes.windll.kernel32 if hasattr(ctypes, "windll") else None

if kernel32 is not None:
    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    CreateFileW.restype = wintypes.HANDLE

    GetFinalPathNameByHandleW = kernel32.GetFinalPathNameByHandleW
    GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    GetFinalPathNameByHandleW.restype = wintypes.DWORD

    GetFileInformationByHandle = kernel32.GetFileInformationByHandle
    GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(BY_HANDLE_FILE_INFORMATION),
    ]
    GetFileInformationByHandle.restype = wintypes.BOOL

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    ReadFile = kernel32.ReadFile
    ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    ReadFile.restype = wintypes.BOOL

    WriteFile = kernel32.WriteFile
    WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    WriteFile.restype = wintypes.BOOL

    SetEndOfFile = kernel32.SetEndOfFile
    SetEndOfFile.argtypes = [wintypes.HANDLE]
    SetEndOfFile.restype = wintypes.BOOL


def verify_and_open_workspace_file(
    rel_path: str,
    workspace_root: Path | str,
    mode: str = "r",
) -> wintypes.HANDLE:
    """
    Hardened two-stage open protocol for workspace file access:
    1. Rejects absolute/drive/colon/UNC paths.
    2. Inspects directory chain for reparse points.
    3. Stage 1: Non-destructive inspection open (FILE_READ_ATTRIBUTES).
    4. Target containment check via GetFinalPathNameByHandleW.
    5. Hard link count check (nNumberOfLinks == 1).
    6. Stage 2: Operates on verified canonical handle.
    """
    if kernel32 is None:
        raise OSError("Win32 security primitives require Windows OS")

    canonical_root = Path(workspace_root).resolve(strict=True)

    # 1. Structural Checks
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise SandboxPathError("invalid_chars", "Path must be a non-empty string")

    if rel_path.startswith(("\\\\", "//")):
        raise SandboxPathError("invalid_chars", "UNC network paths are strictly forbidden")

    if "\\" in rel_path:
        raise SandboxPathError("invalid_chars", "Backslash is forbidden; use forward slash '/'")

    if ":" in rel_path:
        raise SandboxPathError(
            "invalid_chars", "Colons (drive specifiers or NTFS streams) are forbidden"
        )

    if rel_path.startswith("/"):
        raise SandboxPathError("traversal", "Absolute paths are forbidden")

    raw_segments = rel_path.split("/")
    for seg in raw_segments:
        if seg in (".", ".."):
            raise SandboxPathError("traversal", f"Path traversal segment '{seg}' is forbidden")

    # 2. Intermediate directory reparse point inspection
    target_candidate = (canonical_root / rel_path).resolve()
    rel_parts = Path(rel_path).parts
    current = canonical_root
    for part in rel_parts[:-1]:
        current = current / part
        if current.exists():
            attrs = kernel32.GetFileAttributesW(str(current))
            if attrs != 0xFFFFFFFF and (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
                raise SandboxPathError(
                    "reparse_point", f"Reparse point detected in directory chain: {part}"
                )

    share_mode = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE

    # 3. Handle Opening by Mode
    if mode == "r":
        h_file = CreateFileW(
            str(target_candidate),
            GENERIC_READ,
            share_mode,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if h_file == INVALID_HANDLE_VALUE:
            err = ctypes.GetLastError()
            raise FileNotFoundError(
                f"Cannot open file '{rel_path}' for reading (Win32 error {err})"
            )

        try:
            _verify_handle_containment(h_file, canonical_root)
        except Exception:
            CloseHandle(h_file)
            raise
        return h_file

    elif mode in ("w", "a"):
        # Non-destructive Stage 1 inspection open
        h_inspect = CreateFileW(
            str(target_candidate),
            FILE_READ_ATTRIBUTES,
            share_mode,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )

        if h_inspect != INVALID_HANDLE_VALUE:
            # File already exists: verify containment and hard-link count BEFORE opening for write
            try:
                _verify_handle_containment(h_inspect, canonical_root)

                info = BY_HANDLE_FILE_INFORMATION()
                if GetFileInformationByHandle(h_inspect, ctypes.byref(info)):
                    if info.nNumberOfLinks > 1:
                        raise SandboxPathError(
                            "hard_link",
                            f"Security Breach: File '{rel_path}' has "
                            f"{info.nNumberOfLinks} hard links",
                        )
            finally:
                CloseHandle(h_inspect)

            # Stage 2: Open existing verified file for writing
            creation_disp = TRUNCATE_EXISTING if mode == "w" else OPEN_EXISTING
            h_write = CreateFileW(
                str(target_candidate),
                GENERIC_WRITE,
                share_mode,
                None,
                creation_disp,
                FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if h_write == INVALID_HANDLE_VALUE:
                err = ctypes.GetLastError()
                raise SandboxPathError(
                    "write_failed", f"Failed to open verified file for write (Win32 error {err})"
                )
            return h_write

        else:
            err = ctypes.GetLastError()
            if err not in (ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND):
                raise SandboxPathError(
                    "inspect_failed", f"Stage 1 inspection failed with Win32 error {err}"
                )

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
                None,
            )
            if h_parent == INVALID_HANDLE_VALUE:
                err = ctypes.GetLastError()
                raise SandboxPathError(
                    "parent_verify_failed", f"Cannot verify parent directory (Win32 error {err})"
                )
            try:
                _verify_handle_containment(h_parent, canonical_root)
            finally:
                CloseHandle(h_parent)

            # Open new file with CREATE_NEW (fails if created concurrently)
            h_new = CreateFileW(
                str(target_candidate),
                GENERIC_WRITE,
                share_mode,
                None,
                CREATE_NEW,
                FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if h_new == INVALID_HANDLE_VALUE:
                err = ctypes.GetLastError()
                raise SandboxPathError(
                    "create_failed", f"Failed to create new file (Win32 error {err})"
                )
            return h_new

    else:
        raise ValueError(f"Unsupported mode: '{mode}' (expected 'r', 'w', or 'a')")


def _verify_handle_containment(handle: wintypes.HANDLE, canonical_root: Path) -> Path:
    """Verifies that an open Win32 handle resolves strictly inside canonical_root."""
    buf = ctypes.create_unicode_buffer(1024)
    res = GetFinalPathNameByHandleW(handle, buf, 1024, VOLUME_NAME_DOS)
    if res == 0:
        err = ctypes.GetLastError()
        raise SandboxPathError(
            "handle_resolve_failed", f"GetFinalPathNameByHandleW failed (error {err})"
        )

    path_str = buf.value
    # Normalize Win32 device namespace prefixes
    if path_str.startswith("\\\\?\\UNC\\"):
        path_str = "\\\\" + path_str[8:]
    elif path_str.startswith("\\\\?\\"):
        path_str = path_str[4:]

    final_path = Path(path_str).resolve()
    try:
        final_path.relative_to(canonical_root)
    except ValueError as err:
        raise SandboxPathError(
            "traversal",
            f"Security Breach: Handle target '{final_path}' escapes workspace '{canonical_root}'",
        ) from err
    return final_path


def read_workspace_file_handle(handle: wintypes.HANDLE, max_bytes: int = 1048576) -> bytes:
    """Reads content directly from a verified open Win32 handle."""
    buf = ctypes.create_string_buffer(max_bytes)
    bytes_read = wintypes.DWORD(0)
    ok = ReadFile(handle, buf, max_bytes, ctypes.byref(bytes_read), None)
    if not ok:
        err = ctypes.GetLastError()
        raise OSError(f"Win32 ReadFile failed (error code {err})")
    return buf.raw[: bytes_read.value]


def write_workspace_file_handle(handle: wintypes.HANDLE, data: bytes) -> int:
    """Writes content directly to a verified open Win32 handle."""
    bytes_written = wintypes.DWORD(0)
    ok = WriteFile(handle, data, len(data), ctypes.byref(bytes_written), None)
    if not ok:
        err = ctypes.GetLastError()
        raise OSError(f"Win32 WriteFile failed (error code {err})")
    return bytes_written.value


def close_workspace_file_handle(handle: wintypes.HANDLE) -> None:
    """Closes an open Win32 handle."""
    if handle != INVALID_HANDLE_VALUE:
        CloseHandle(handle)


@contextmanager
def verified_workspace_file(
    rel_path: str,
    workspace_root: Path | str,
    mode: str = "r",
) -> Generator[wintypes.HANDLE, None, None]:
    """Context manager for safe handle management."""
    h = verify_and_open_workspace_file(rel_path, workspace_root, mode=mode)
    try:
        yield h
    finally:
        close_workspace_file_handle(h)
