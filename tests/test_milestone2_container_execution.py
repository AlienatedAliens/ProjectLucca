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
from lucca.sandbox.service import SandboxService


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


def test_container_rpc_liveness(rpc_transport: DockerRPCTransport):
    """Verifies that lucca-toolsrv responds to list_dir via Docker exec."""
    res = rpc_transport.execute(call_id="c-live-1", tool="list_dir", args={"path": "."})
    assert res.ok is True
    assert res.exit_code == 0
    assert res.structured is not None
    assert "entries" in res.structured


def test_run_python_in_container(rpc_transport: DockerRPCTransport):
    """Verifies safe Python evaluation inside the Linux container."""
    code = "import sys, math; print(f'PI={math.pi:.4f}; PY={sys.version_info.major}.{sys.version_info.minor}')"
    res = rpc_transport.execute(call_id="c-py-1", tool="run_python", args={"code": code})
    assert res.ok is True
    assert res.exit_code == 0
    assert "PI=3.1416" in str(res.content)
    assert "PY=3.12" in str(res.content)


def test_network_none_confinement(rpc_transport: DockerRPCTransport):
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


def test_host_filesystem_unmounted(rpc_transport: DockerRPCTransport):
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


def test_container_read_only_root(rpc_transport: DockerRPCTransport):
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
    assert "Read-only file system" in str(res.content) or "Errno 30" in str(res.content)
    assert "WROTE_EVIL" not in str(res.content)


def test_container_unprivileged_user(rpc_transport: DockerRPCTransport):
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


def test_container_file_crud_lifecycle(rpc_transport: DockerRPCTransport):
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


def test_container_traversal_rejection(rpc_transport: DockerRPCTransport):
    """Verifies that path traversal escaping /workspace is rejected by container tool."""
    res = rpc_transport.execute(
        call_id="c-trav-1",
        tool="read_file",
        args={"path": "../../etc/passwd"},
    )
    assert res.ok is False
    assert "traversal" in str(res.stderr).lower()
