"""
Project Lucca — Milestone 2 Live Container Isolation Verification Suite
Verifies that lucca-file-sandbox in WSL2 Docker enforces all security boundaries:
1. Live RPC transport communication with lucca-toolsrv.
2. run_python execution inside unprivileged container.
3. Network confinement (--network none) drops outbound socket connects.
4. Host filesystem isolation (C:\\Windows, user profile unmounted).
5. Read-only root filesystem prevents modification of system binaries.
6. Unprivileged container user (UID 1000:1000, not root).
7. Bidirectional file operations (write, read with sha256 audit, delete).
8. Traversal rejection across container boundary.
"""

import pytest

from lucca.sandbox.rpc import DockerRPCTransport

pytestmark = [pytest.mark.tier2, pytest.mark.hw]


@pytest.fixture(scope="module")
def rpc_transport() -> DockerRPCTransport:
    rpc = DockerRPCTransport(container_name="lucca-file-sandbox", use_direct_fallback=False)
    if not rpc.is_docker_available():
        pytest.skip("Docker / WSL2 not available in this test environment")
    if not rpc.is_container_running():
        started = rpc.ensure_container_running()
        if not started:
            pytest.skip("Could not start lucca-file-sandbox container in WSL2")
    return rpc


def test_container_rpc_liveness(rpc_transport: DockerRPCTransport) -> None:
    """Verifies that lucca-toolsrv responds to list_dir via Docker exec."""
    res = rpc_transport.execute(call_id="c-live-1", tool="list_dir", args={"path": "."})
    assert res.ok is True
    assert res.exit_code == 0
    assert res.structured is not None
    assert "entries" in res.structured


def test_run_python_in_container(rpc_transport: DockerRPCTransport) -> None:
    """Verifies safe Python evaluation inside the Linux container."""
    code = "import sys, math; print(f'PI={math.pi:.4f}; PY={sys.version_info.major}.{sys.version_info.minor}')"
    res = rpc_transport.execute(call_id="c-py-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert res.exit_code == 0
    assert "PI=3.1416" in str(res.content)
    assert "PY=3.12" in str(res.content)


def test_network_none_confinement(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that --network none physically prevents network egress.
    Socket connect must raise Network is unreachable (Errno 101).
    """
    code = """
import socket
try:
    s = socket.socket()
    s.settimeout(1.0)
    s.connect(('8.8.8.8', 53))
    print('CONNECTED')
except Exception as exc:
    print(f'BLOCKED: {type(exc).__name__} [{exc}]')
"""
    res = rpc_transport.execute(call_id="c-net-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert "Network is unreachable" in str(res.content) or "Errno 101" in str(res.content)
    assert "CONNECTED" not in str(res.content)


def test_host_filesystem_unmounted(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that the Windows host drive (C:\\) and System32 are not mounted in container.
    """
    code = """
import os
print('EXISTS_C:', os.path.exists('C:\\\\Windows\\\\System32'))
print('EXISTS_WIN:', os.path.exists('/mnt/c/Windows'))
"""
    res = rpc_transport.execute(call_id="c-fs-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert "EXISTS_C: False" in str(res.content)
    assert "EXISTS_WIN: False" in str(res.content)


def test_container_read_only_root(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that container root filesystem is read-only (--read-only).
    Attempts to write to /etc or /bin must fail with EROFS (Read-only file system).
    """
    code = """
import os
try:
    with open('/etc/evil.conf', 'w') as f:
        f.write('evil')
    print('WROTE_EVIL')
except Exception as exc:
    print(f'READ_ONLY_BLOCKED: {type(exc).__name__} [{exc}]')
"""
    res = rpc_transport.execute(call_id="c-ro-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert any(w in str(res.content) for w in ("Read-only file system", "Errno 30", "Permission denied", "Errno 13"))
    assert "WROTE_EVIL" not in str(res.content)


def test_container_unprivileged_user(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that container runs as unprivileged user 1000:1000, not root (UID 0).
    """
    code = """
import os
print(f'UID={os.getuid()}; GID={os.getgid()}')
"""
    res = rpc_transport.execute(call_id="c-uid-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert "UID=1000; GID=1000" in str(res.content)
    assert "UID=0" not in str(res.content)


def test_container_file_crud_lifecycle(rpc_transport: DockerRPCTransport) -> None:
    """Verifies file write, read with sha256 audit, and deletion inside container."""
    test_file = "m2_verification_test.txt"
    test_payload = "Project Lucca Milestone 2: Deontic Sandbox Verified on Silicon."

    # 1. Write
    res_w = rpc_transport.execute(
        call_id="c-file-w",
        tool="write_file",
        args={"path": test_file, "content": test_payload, "mode": "create"},
    )
    assert res_w.ok is True
    assert res_w.structured is not None
    assert "sha256" in res_w.structured

    # 2. Read with SHA256 audit
    res_r = rpc_transport.execute(
        call_id="c-file-r",
        tool="read_file",
        args={"path": test_file},
    )
    assert res_r.ok is True
    assert res_r.content == test_payload

    # 3. Delete
    res_d = rpc_transport.execute(
        call_id="c-file-d",
        tool="delete_file",
        args={"path": test_file},
    )
    assert res_d.ok is True
    assert res_d.structured == {"deleted": True}


def test_container_traversal_rejection(rpc_transport: DockerRPCTransport) -> None:
    """Verifies that path traversal escaping /workspace is rejected by container tool."""
    res = rpc_transport.execute(
        call_id="c-trav-1",
        tool="read_file",
        args={"path": "../../etc/passwd"},
    )
    assert res.ok is False
    assert "traversal" in str(res.stderr).lower()


def test_container_tmpfs_noexec_enforcement(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that /tmp is mounted with noexec.
    Attempting to execute a script written to /tmp must fail with PermissionError (EACCES).
    """
    code = """
import os, subprocess
script_path = '/tmp/test_exec.sh'
with open(script_path, 'w') as f:
    f.write('#!/bin/sh\\necho EXECUTED\\n')
os.chmod(script_path, 0o755)
try:
    res = subprocess.run([script_path], capture_output=True, text=True)
    print('OUTPUT:', res.stdout.strip())
except PermissionError as exc:
    print(f'NOEXEC_BLOCKED: {exc}')
except Exception as exc:
    print(f'OTHER_ERROR: {type(exc).__name__} [{exc}]')
finally:
    if os.path.exists(script_path):
        try: os.remove(script_path)
        except: pass
"""
    res = rpc_transport.execute(call_id="c-noexec-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert "NOEXEC_BLOCKED" in str(res.content) or "Permission denied" in str(res.content)
    assert "EXECUTED" not in str(res.content)


def test_container_tmpfs_size_limit_32mb(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that /tmp tmpfs size limit (32MB) is strictly enforced.
    Attempting to write 40MB must fail with No space left on device (ENOSPC).
    """
    code = """
import os
target = '/tmp/oversize.bin'
try:
    with open(target, 'wb') as f:
        # Write in 4MB chunks up to 40MB
        for _ in range(10):
            f.write(b'\\x00' * (4 * 1024 * 1024))
    print('WROTE_40MB')
except OSError as exc:
    print(f'SIZE_LIMIT_BLOCKED: {exc}')
finally:
    if os.path.exists(target):
        try: os.remove(target)
        except: pass
"""
    res = rpc_transport.execute(call_id="c-size-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert "SIZE_LIMIT_BLOCKED" in str(res.content) or "No space left on device" in str(res.content)
    assert "WROTE_40MB" not in str(res.content)


def test_container_security_opts_cap_drop_and_no_new_privs(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that --cap-drop=ALL and --security-opt=no-new-privileges are active in /proc/self/status.
    Effective capabilities must be zero and NoNewPrivs must be 1.
    """
    code = """
with open('/proc/self/status', 'r') as f:
    status = f.read()

no_new_privs = None
cap_eff = None
for line in status.splitlines():
    if line.startswith('NoNewPrivs:'):
        no_new_privs = line.split(':')[1].strip()
    elif line.startswith('CapEff:'):
        cap_eff = line.split(':')[1].strip()

print(f'NoNewPrivs={no_new_privs}; CapEff={cap_eff}')
"""
    res = rpc_transport.execute(call_id="c-caps-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert "NoNewPrivs=1" in str(res.content)
    assert "CapEff=0000000000000000" in str(res.content)


def test_container_memory_limit_enforcement(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that --memory=768m cgroup boundary prevents unbounded RAM allocation.
    Attempting to allocate 2GB buffer must raise MemoryError or fail safely.
    """
    code = """
try:
    buf = bytearray(2 * 1024 * 1024 * 1024)
    print('ALLOCATED_2GB')
except MemoryError:
    print('MEMORY_LIMIT_BLOCKED: MemoryError')
except Exception as exc:
    print(f'ALLOC_FAILED: {type(exc).__name__}')
"""
    res = rpc_transport.execute(call_id="c-mem-1", tool="run_python", args={"code": code})
    assert "MEMORY_LIMIT_BLOCKED" in str(res.content) or not res.ok
    assert "ALLOCATED_2GB" not in str(res.content)


def test_container_pids_limit_fork_bomb(rpc_transport: DockerRPCTransport) -> None:
    """
    Verifies that --pids-limit=256 cgroup boundary halts runaway process fork bombs.
    Spawning 300 children must raise BlockingIOError (Errno 11 Resource temporarily unavailable).
    """
    code = """
import os, time
pids = []
try:
    for i in range(300):
        pid = os.fork()
        if pid == 0:
            time.sleep(5)
            os._exit(0)
        pids.append(pid)
    print(f'SPAWNED_ALL_{len(pids)}')
except BlockingIOError as e:
    print(f'FORK_BLOCKED_BY_CGROUP_PIDS_LIMIT: spawned={len(pids)}, error={e}')
except Exception as e:
    print(f'FORK_EXCEPTION: spawned={len(pids)}, {type(e).__name__}={e}')
finally:
    for p in pids:
        try: os.kill(p, 9)
        except: pass
"""
    res = rpc_transport.execute(call_id="c-fork-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert "FORK_BLOCKED_BY_CGROUP_PIDS_LIMIT" in str(res.content)
    assert "Errno 11" in str(res.content)
    assert "SPAWNED_ALL_300" not in str(res.content)


