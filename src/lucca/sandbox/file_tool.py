"""
Project Lucca — Hardened File Tool & Path Validator
Spec 09 §4, D-08, ADR-004
"""

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Final, Literal

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

from lucca.core.exceptions import SandboxPathError

MAX_PATH_LEN: Final = 1024
MAX_FILE_BYTES: Final = 262144  # 256 KiB
MAX_WRITE_BYTES: Final = 1048576  # 1 MiB
MAX_LIST_ENTRIES: Final = 500
MAX_SEARCH_HITS: Final = 200
MAX_PYTHON_STDOUT: Final = 65536  # 64 KiB
SNIFF_CHUNK_SIZE: Final = 8192

RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
    }
)


def validate_rel_path(p: str, workspace_root: Path | str = "/workspace") -> Path:
    """
    Strict path validation before filesystem interaction per Spec 09 §4:
    1. Type, length, UTF-8, forbidden control chars, % rejection, backslash rejection.
    2. Relative only, no . or .., no ~ prefix, no Windows reserved names.
    3. realpath boundary check (os.path.commonpath).
    4. Symlink detection along all components.
    """
    if not isinstance(p, str) or len(p) == 0:
        raise SandboxPathError("invalid_chars", "Path must be a non-empty string")

    if len(p) > MAX_PATH_LEN:
        raise SandboxPathError("too_long", f"Path length {len(p)} exceeds maximum {MAX_PATH_LEN}")

    # Check forbidden characters
    if "\x00" in p:
        raise SandboxPathError("invalid_chars", "NUL byte in path is forbidden")

    for ch in p:
        code = ord(ch)
        if (code < 32 or code == 127) and ch not in ("\t", "\n"):
            raise SandboxPathError("invalid_chars", f"Control character 0x{code:02x} is forbidden")

    if "%" in p:
        raise SandboxPathError("invalid_chars", "Percent-encoding is strictly forbidden")

    if "\\" in p:
        raise SandboxPathError("invalid_chars", "Backslash is forbidden; use forward slash '/'")

    if ":" in p:
        raise SandboxPathError("invalid_chars", "Colons (drive specifiers or NTFS streams) are forbidden")

    if p.startswith(("/", "\\")):
        raise SandboxPathError("traversal", "Absolute paths are forbidden")

    if "//" in p:
        raise SandboxPathError("invalid_chars", "Consecutive slashes are forbidden")

    raw_segments = p.split("/")
    segments = [s for s in raw_segments if s != ""]

    for seg in segments:
        if seg in (".", ".."):
            raise SandboxPathError("traversal", f"Path traversal segment '{seg}' is forbidden")
        if seg.startswith("~"):
            raise SandboxPathError("traversal", f"Home directory shortcut '{seg}' is forbidden")

        # Windows reserved names check (case-insensitive)
        base = seg.split(".")[0].lower()
        if base in RESERVED_NAMES:
            raise SandboxPathError("reserved", f"Reserved device name '{seg}' is forbidden")

    root = Path(workspace_root).resolve()
    target = (root / p).resolve()

    try:
        common = os.path.commonpath([str(target), str(root)])
        if common != str(root):
            raise SandboxPathError("traversal", f"Path '{p}' escapes workspace boundary")
    except ValueError as e:
        raise SandboxPathError("traversal", f"Path '{p}' escapes workspace boundary: {e}") from e

    # Check for symlinks along path components if they exist
    cur = root
    for part in Path(p).parts:
        cur = cur / part
        if cur.is_symlink() or (cur.exists() and os.path.islink(cur)):
            raise SandboxPathError("symlink", f"Symlink detected in path component '{part}'")

    return target


class SafeFileTool:
    def __init__(self, workspace_root: Path | str = "/workspace") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def list_dir(self, path: str = "", recursive: bool = False) -> dict[str, object]:
        target = (
            validate_rel_path(path, self.workspace_root)
            if path and path != "."
            else self.workspace_root
        )
        if not target.exists():
            raise SandboxPathError("not_found", f"Directory not found: {path}")
        if not target.is_dir():
            raise SandboxPathError("is_dir", f"Path is not a directory: {path}")

        entries: list[dict[str, object]] = []
        truncated = False

        if recursive:
            iterator = target.rglob("*")
        else:
            iterator = target.iterdir()

        for item in iterator:
            if len(entries) >= MAX_LIST_ENTRIES:
                truncated = True
                break
            try:
                st = item.stat()
                rel = item.relative_to(self.workspace_root).as_posix()
                entries.append(
                    {
                        "name": rel,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "is_dir": item.is_dir(),
                    }
                )
            except (OSError, ValueError):
                continue

        return {"entries": entries, "truncated": truncated}

    def read_file(
        self, path: str, max_bytes: int = MAX_FILE_BYTES
    ) -> tuple[dict[str, object], str]:
        target = validate_rel_path(path, self.workspace_root)
        if not target.exists():
            raise SandboxPathError("not_found", f"File not found: {path}")
        if target.is_dir():
            raise SandboxPathError("is_dir", f"Path is a directory, not a file: {path}")

        file_size = target.stat().st_size

        with open(target, "rb") as f:
            # Sniff first chunk for binary content
            sniff = f.read(SNIFF_CHUNK_SIZE)
            if b"\x00" in sniff:
                raise SandboxPathError("is_binary", f"Binary file detected: {path}")

            f.seek(0)
            data = f.read(max_bytes + 1)

        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]

        content = data.decode("utf-8", errors="replace")
        sha256 = hashlib.sha256(data).hexdigest()

        structured = {
            "size": file_size,
            "sha256": sha256,
            "truncated": truncated,
        }
        return structured, content

    def write_file(
        self,
        path: str,
        content: str,
        mode: Literal["create", "overwrite", "append"] = "create",
    ) -> dict[str, object]:
        target = validate_rel_path(path, self.workspace_root)
        encoded = content.encode("utf-8")

        if len(encoded) > MAX_WRITE_BYTES:
            raise SandboxPathError("too_large", f"Content size {len(encoded)} exceeds 1 MiB limit")

        if not target.parent.exists():
            raise SandboxPathError("not_found", f"Parent directory does not exist: {target.parent}")

        if mode == "create" and target.exists():
            raise SandboxPathError("traversal", f"File '{path}' already exists in create mode")

        file_mode = "ab" if mode == "append" else "wb"
        with open(target, file_mode) as f:
            f.write(encoded)

        return {
            "size": target.stat().st_size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }

    def delete_file(self, path: str) -> dict[str, object]:
        target = validate_rel_path(path, self.workspace_root)
        if not target.exists():
            raise SandboxPathError("not_found", f"File not found: {path}")
        if target.is_dir():
            raise SandboxPathError("is_dir", f"Cannot delete directory '{path}' with delete_file")

        target.unlink()
        return {"deleted": True}

    def search_text(
        self, pattern: str, path: str = "", max_hits: int = MAX_SEARCH_HITS
    ) -> tuple[dict[str, object], str]:
        target = (
            validate_rel_path(path, self.workspace_root)
            if path and path != "."
            else self.workspace_root
        )
        if not target.exists():
            raise SandboxPathError("not_found", f"Path not found: {path}")

        hits: list[dict[str, object]] = []
        snippets: list[str] = []
        pat_lower = pattern.lower()

        files_to_search = [target] if target.is_file() else sorted(target.rglob("*"))

        for f in files_to_search:
            if not f.is_file():
                continue
            try:
                with open(f, "rb") as fp:
                    sniff = fp.read(SNIFF_CHUNK_SIZE)
                    if b"\x00" in sniff:
                        continue  # skip binary
                    fp.seek(0)
                    text = fp.read(MAX_FILE_BYTES).decode("utf-8", errors="replace")

                rel_path = f.relative_to(self.workspace_root).as_posix()
                for line_no, line in enumerate(text.splitlines(), start=1):
                    line_lower = line.lower()
                    col = line_lower.find(pat_lower)
                    while col != -1:
                        hits.append({"file": rel_path, "line": line_no, "col": col + 1})
                        snippet = f"{rel_path}:{line_no}:{col + 1}: {line.strip()}"
                        snippets.append(snippet)
                        if len(hits) >= max_hits:
                            return {
                                "hits": hits,
                                "count": len(hits),
                                "truncated": True,
                            }, "\n".join(snippets)
                        col = line_lower.find(pat_lower, col + len(pat_lower))
            except (OSError, UnicodeDecodeError):
                continue

        return {"hits": hits, "count": len(hits), "truncated": False}, "\n".join(snippets)

    def run_python(self, code: str, timeout: int = 10) -> tuple[dict[str, object], str]:
        # Enforce that run_python executes strictly inside the verified container boundary,
        # never on the host (regardless of whether the host OS is Windows, Linux, or macOS).
        # Requires BOTH the unforgeable image-baked sentinel file AND the container environment flag.
        sentinel_path = Path("/opt/lucca/.sandbox_container")
        is_container = (
            sentinel_path.is_file()
            and os.environ.get("LUCCA_SANDBOX_CONTAINER") == "1"
        )
        if not is_container:
            err_msg = "policy_violation: run_python is disabled on host pending Milestone 2 container isolation"
            return {
                "exit_code": -1,
                "elapsed_ms": 0.0,
                "ok": False,
                "stderr": err_msg,
                "stdout": "",
            }, err_msg

        t0 = time.perf_counter()
        preexec_fn = None
        if resource is not None and hasattr(resource, "setrlimit"):
            rlimit_as = getattr(resource, "RLIMIT_AS", None)
            rlimit_cpu = getattr(resource, "RLIMIT_CPU", None)
            set_rlimit = getattr(resource, "setrlimit", None)

            if set_rlimit is not None and rlimit_as is not None and rlimit_cpu is not None:

                def _set_limits() -> None:
                    set_rlimit(rlimit_as, (256 * 1024 * 1024, 256 * 1024 * 1024))
                    set_rlimit(rlimit_cpu, (10, 10))

                preexec_fn = _set_limits

        try:
            proc = subprocess.run(  # noqa: S603
                [sys.executable, "-I", "-S", "-c", code],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                preexec_fn=preexec_fn,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            stdout = proc.stdout[:MAX_PYTHON_STDOUT]
            stderr = proc.stderr[:MAX_PYTHON_STDOUT]
            out = stdout + (f"\n[stderr]\n{stderr}" if stderr else "")
            return {
                "exit_code": proc.returncode,
                "elapsed_ms": elapsed_ms,
                "ok": proc.returncode == 0,
                "stderr": stderr,
            }, out
        except subprocess.TimeoutExpired:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "exit_code": -1,
                "elapsed_ms": elapsed_ms,
                "ok": False,
                "error": "timeout",
            }, f"Execution timed out after {timeout} seconds"
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "exit_code": -2,
                "elapsed_ms": elapsed_ms,
                "ok": False,
                "error": str(exc),
            }, str(exc)

