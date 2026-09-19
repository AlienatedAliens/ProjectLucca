"""
Project Lucca — Sandbox Container Specifications
Spec 09 §2, ADR-003, ADR-004
Renders normative docker run arguments for file-sandbox and web-sandbox.
"""

from pathlib import Path

from lucca.core.config import get_config


def win_to_wsl_path(p: Path | str) -> str:
    r"""Translates a Windows path like C:\path to /mnt/c/path."""
    p_str = str(p).replace("\\", "/")
    if len(p_str) >= 2 and p_str[1] == ":":
        drive = p_str[0].lower()
        rest = p_str[2:]
        return f"/mnt/{drive}{rest}"
    return p_str


def get_file_sandbox_run_args(
    workspace_path: Path | str | None = None,
    container_name: str = "lucca-file-sandbox",
    image_tag: str = "lucca/file-sandbox:latest",
) -> list[str]:
    """
    Renders normative arguments for the long-lived file-sandbox container:
    - Zero network (--network none)
    - Read-only root filesystem with tmpfs /tmp (32 MB)
    - Bound workspace mount (/workspace)
    - Unprivileged user 1000:1000, all capabilities dropped
    - 768 MB RAM, 1.5 CPUs, 256 pids limit, 50 MB file size limit
    """
    target_path = (
        Path(workspace_path)
        if workspace_path is not None
        else get_config().resolve_path("workspace")
    )
    wsl_mount = win_to_wsl_path(target_path)
    return [
        "run",
        "-d",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=32m",  # noqa: S108
        "--mount",
        f"type=bind,src={wsl_mount},dst=/workspace",
        "-e",
        "LUCCA_SANDBOX_CONTAINER=1",
        "--user",
        "1000:1000",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=768m",
        "--memory-swap=768m",
        "--cpus=1.5",
        "--pids-limit=256",
        "--ulimit",
        "nofile=256:256",
        "--ulimit",
        "fsize=52428800",
        "--stop-timeout",
        "2",
        "--init",
        image_tag,
        "sleep",
        "infinity",
    ]


def get_web_sandbox_run_args(
    call_id: str,
    image_tag: str = "lucca/web-sandbox:latest",
    network_name: str = "lucca-net",
) -> list[str]:
    """
    Renders normative arguments for the ephemeral web-sandbox container:
    - Ephemeral (--rm)
    - Isolated network with ordered egress (--network lucca-net --dns 1.1.1.1)
    - Read-only root, zero filesystem mounts, tmpfs /tmp (32 MB)
    - Unprivileged user 1000:1000, all capabilities dropped
    - 512 MB RAM, 1.0 CPU, 128 pids limit
    """
    clean_id = call_id.replace(" ", "_")[:32]
    return [
        "run",
        "--rm",
        "-i",
        "--name",
        f"lucca-web-{clean_id}",
        "--network",
        network_name,
        "--dns",
        "1.1.1.1",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=32m",  # noqa: S108
        "--user",
        "1000:1000",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=512m",
        "--memory-swap=512m",
        "--cpus=1.0",
        "--pids-limit=128",
        "--stop-timeout",
        "2",
        "--init",
        image_tag,
        "lucca-toolsrv",
    ]
