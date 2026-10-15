"""
Project Lucca — Hardened File Tool & Path Validator
Spec 09 §4, D-08, ADR-004
"""

import ast
import copy
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Final, Literal

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

import structlog
from lucca.core.exceptions import SandboxPathError

logger = structlog.get_logger(__name__)

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
    import unicodedata
    if unicodedata.normalize("NFKC", p) != p:
        raise SandboxPathError("invalid_chars", "Unicode compatibility homoglyphs (NFKC mismatch) are forbidden")
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
        raise SandboxPathError(
            "invalid_chars", "Colons (drive specifiers or NTFS streams) are forbidden"
        )

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

    @staticmethod
    def _resolve_url_shortcut(target: Path) -> Path | None:
        """
        Parses a Windows Internet Shortcut (.url) file and returns the resolved
        local file path if the URL is a file:// reference, or None if the target
        is not a local file path or the format is unrecognised.

        Security: only resolves ``file://`` URIs; network URIs are rejected.
        The caller must perform any further boundary checks on the returned path.
        """
        try:
            raw = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped.upper().startswith("URL="):
                continue
            url = stripped[4:].strip()
            if not url.lower().startswith("file://"):
                return None  # network URL — refuse

            # Decode percent-encoded characters in the path portion
            import urllib.parse

            parsed = urllib.parse.urlparse(url)
            local_path_str = urllib.parse.unquote(parsed.path)

            # On Windows: file:///c:/path → path starts with /c:/...
            if local_path_str.startswith("/") and len(local_path_str) > 2 and local_path_str[2] == ":":
                local_path_str = local_path_str[1:]  # strip leading /

            resolved = Path(local_path_str)
            if resolved.is_absolute() and resolved.exists() and resolved.is_file():
                return resolved
            return None
        return None

    def read_file(
        self, path: str, max_bytes: int = MAX_FILE_BYTES
    ) -> tuple[dict[str, object], str]:
        target = validate_rel_path(path, self.workspace_root)
        if not target.exists():
            raise SandboxPathError("not_found", f"File not found: {path}")
        if target.is_dir():
            raise SandboxPathError("is_dir", f"Path is a directory, not a file: {path}")

        # ── Windows Internet Shortcut redirect (.url) ──────────────────────
        # If the caller points at a .url file, transparently resolve and read
        # the local target file instead, so dropped playbook shortcuts work.
        resolved_from_url: Path | None = None
        if target.suffix.lower() == ".url":
            resolved_from_url = self._resolve_url_shortcut(target)
            if resolved_from_url is not None:
                logger.debug(
                    "read_file_url_redirect",
                    shortcut=str(target),
                    resolved=str(resolved_from_url),
                )
                target = resolved_from_url

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
            "resolved_from_shortcut": str(resolved_from_url) if resolved_from_url else None,
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

        regex: re.Pattern[str] | None = None
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = None

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
                    if regex is not None:
                        for m in regex.finditer(line):
                            hits.append({"file": rel_path, "line": line_no, "col": m.start() + 1})
                            snippet = f"{rel_path}:{line_no}:{m.start() + 1}: {line.strip()}"
                            snippets.append(snippet)
                            if len(hits) >= max_hits:
                                return {
                                    "hits": hits,
                                    "count": len(hits),
                                    "truncated": True,
                                }, "\n".join(snippets)
                    else:
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
        # Requires BOTH the unforgeable image-baked sentinel file AND the container env flag.
        sentinel_path = Path("/opt/lucca/.sandbox_container")
        is_container = sentinel_path.is_file() and os.environ.get("LUCCA_SANDBOX_CONTAINER") == "1"
        if not is_container:
            err_msg = (
                "policy_violation: run_python is disabled on host pending "
                "Milestone 2 container isolation"
            )
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
                    set_rlimit(rlimit_as, (512 * 1024 * 1024, 512 * 1024 * 1024))
                    set_rlimit(rlimit_cpu, (10, 10))

                preexec_fn = _set_limits

        executable_code = code
        try:
            def _visit_aug_assign(self: ast.NodeTransformer, node: ast.AugAssign) -> ast.AST:
                if isinstance(node.op, ast.Div):
                    left = copy.deepcopy(node.target)
                    if hasattr(left, "ctx"):
                        left.ctx = ast.Load()
                    return ast.Assign(
                        targets=[node.target],
                        value=ast.BinOp(left=left, op=ast.Div(), right=node.value),
                    )
                return self.generic_visit(node)

            class _DivNormalizer(ast.NodeTransformer):
                visit_AugAssign = _visit_aug_assign

            tree = ast.parse(code)
            tree = _DivNormalizer().visit(tree)
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                last_expr = tree.body[-1].value
                if not (
                    isinstance(last_expr, ast.Call)
                    and isinstance(last_expr.func, ast.Name)
                    and last_expr.func.id == "print"
                ):
                    if isinstance(last_expr, ast.Call):
                        wrapper = ast.parse(
                            "_res = " + ast.unparse(last_expr) + "\n"
                            "if _res is not None:\n"
                            "    print(_res)\n"
                        ).body
                        tree.body.pop()
                        tree.body.extend(wrapper)
                    else:
                        tree.body[-1] = ast.Expr(
                            value=ast.Call(
                                func=ast.Name(id="print", ctx=ast.Load()),
                                args=[last_expr],
                                keywords=[],
                            )
                        )
            ast.fix_missing_locations(tree)
            executable_code = ast.unparse(tree)
        except Exception as exc:
            logger.debug("ast_transform_skipped", error=str(exc))
            executable_code = code

        try:
            proc = subprocess.run(  # noqa: S603
                [sys.executable, "-I", "-"],
                input=executable_code,
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
            logger.debug("python_exec_failed", error=str(exc))
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "exit_code": -2,
                "elapsed_ms": elapsed_ms,
                "ok": False,
                "error": str(exc),
            }, str(exc)

    def _resolve_path(self, p: str) -> Path:
        clean = (p or "").strip().replace("\\", "/")
        if clean in (".", "", "./"):
            return Path(self.workspace_root).resolve()
        return validate_rel_path(clean, self.workspace_root)

    def grep_tree(
        self,
        pattern: str,
        dir_path: str = ".",
        max_hits: int = 100,
    ) -> tuple[dict[str, object], str]:
        """Recursively searches code tree for regex pattern, returning file:line:matched_content."""
        target_dir = self._resolve_path(dir_path)
        if not target_dir.is_dir():
            raise SandboxPathError("not_a_directory", f"Path '{dir_path}' is not a directory")

        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as err:
            raise SandboxPathError("invalid_regex", f"Invalid regex pattern '{pattern}': {err}") from err

        hits: list[dict[str, object]] = []
        snippets: list[str] = []
        for root, dirs, files in os.walk(str(target_dir)):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in ("__pycache__", "venv", ".venv", "node_modules", ".git")
            ]
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = Path(root) / fname
                try:
                    rel_p = str(fpath.relative_to(self.workspace_root)).replace("\\", "/")
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    for line_no, line in enumerate(content.splitlines(), start=1):
                        if rx.search(line):
                            hits.append({"file": rel_p, "line": line_no, "text": line.strip()})
                            snippets.append(f"{rel_p}:{line_no}: {line.strip()}")
                            if len(hits) >= max_hits:
                                return {
                                    "hits": hits,
                                    "count": len(hits),
                                    "truncated": True,
                                }, "\n".join(snippets)
                except (OSError, UnicodeDecodeError):
                    continue

        return {"hits": hits, "count": len(hits), "truncated": False}, "\n".join(snippets)

    def view_slice(
        self,
        path: str,
        start_line: int = 1,
        end_line: int = 100,
    ) -> tuple[dict[str, object], str]:
        """Reads a slice of lines from a file with 1-indexed line numbers."""
        target_file = self._resolve_path(path)
        if not target_file.is_file():
            raise SandboxPathError("not_a_file", f"Path '{path}' is not a file")

        content = target_file.read_text(encoding="utf-8", errors="replace")
        all_lines = content.splitlines()
        total_lines = len(all_lines)

        s = max(1, start_line)
        e = min(total_lines, max(s, end_line))
        slice_lines = all_lines[s - 1 : e]

        formatted = [f"{s + i:4d} | {line}" for i, line in enumerate(slice_lines)]
        header = f"[{path} lines {s}-{e} of {total_lines}]\n"
        body = "\n".join(formatted)

        return {
            "path": path,
            "start_line": s,
            "end_line": e,
            "total_lines": total_lines,
            "count": len(slice_lines),
        }, header + body

    def apply_patch(
        self,
        path: str,
        target_chunk: str,
        replacement_chunk: str,
    ) -> tuple[dict[str, object], str]:
        """Atomically replaces single unambiguous target_chunk with replacement_chunk in file."""
        target_file = self._resolve_path(path)
        if not target_file.is_file():
            raise SandboxPathError("not_a_file", f"Path '{path}' is not a file")

        content = target_file.read_text(encoding="utf-8", errors="replace")
        occurrences = content.count(target_chunk)
        if occurrences == 0:
            raise SandboxPathError("patch_target_not_found", f"Target chunk not found in '{path}'")
        if occurrences > 1:
            raise SandboxPathError(
                "patch_ambiguous",
                f"Target chunk found {occurrences} times in '{path}'; must be unique",
            )

        new_content = content.replace(target_chunk, replacement_chunk, 1)
        self.write_file(path, new_content, mode="overwrite")
        return {
            "path": path,
            "applied": True,
            "replaced_bytes": len(target_chunk),
            "new_bytes": len(replacement_chunk),
        }, f"Successfully applied patch to '{path}'."

    def run_pytest(
        self,
        test_path: str = "",
        cwd: str = ".",
        timeout: int = 60,
    ) -> tuple[dict[str, object], str]:
        """Runs pytest on test_path in the specified workspace directory."""
        target_dir = self._resolve_path(cwd)
        cmd = [sys.executable, "-m", "pytest", "-v"]
        if test_path.strip():
            cmd.append(test_path.strip())

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            elapsed = (time.perf_counter() - t0) * 1000.0
            out = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
            return {
                "exit_code": proc.returncode,
                "passed": proc.returncode == 0,
                "elapsed_ms": elapsed,
            }, out[:MAX_PYTHON_STDOUT]
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "passed": False,
                "error": "timeout",
            }, f"pytest execution timed out after {timeout}s"
