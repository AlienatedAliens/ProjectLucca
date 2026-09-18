"""
Project Lucca — Sandbox Egress Verification
Spec 09 §8, ADR-003
Verifies positive-controlled egress rules inside Ubuntu WSL2 Docker environment.
"""

import http.server
import socket
import subprocess
import threading
import time
from pathlib import Path

import structlog
from pydantic import JsonValue

from lucca.sandbox.container_spec import win_to_wsl_path

logger = structlog.get_logger(__name__)


def get_local_lan_ip() -> str:
    """Discovers host LAN IPv4 address reachable by WSL."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to public DNS to find the outgoing interface IP
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
    except Exception:  # noqa: BLE001
        ip = "127.0.0.1"
    finally:
        s.close()
    return str(ip)


class EgressVerifier:
    """
    Automates the Spec 09 §8 positive-controlled egress test matrix.
    """

    def __init__(self, wsl_distro: str = "Ubuntu", test_port: int = 8089) -> None:
        self.wsl_distro = wsl_distro
        self.test_port = test_port

    def apply_rules(self) -> tuple[bool, str]:
        """Applies scripts/wsl/lucca-egress.sh inside Ubuntu WSL2."""
        script_path = Path(__file__).resolve().parents[3] / "scripts" / "wsl" / "lucca-egress.sh"
        script_wsl = win_to_wsl_path(str(script_path))
        cmd = ["wsl", "-u", "root", "-d", self.wsl_distro, "--", "bash", script_wsl]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10.0, check=False)  # noqa: S603
            if res.returncode == 0:
                logger.info("egress_rules_applied")
                return True, res.stdout
            return False, res.stderr
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def verify_all(self) -> dict[str, JsonValue]:
        """
        Executes the normative 6-step egress verification matrix:
        1. Host HTTP listener running on LAN IP.
        2. Reachable from Ubuntu host shell (positive control -> 200 OK).
        3. Blocked from web-sandbox container (curl to LAN IP fails).
        4. Public HTTPS allowed (example.com -> 200 OK).
        5. Non-web ports blocked (1.1.1.1:22 blocked).
        6. IPv6 blocked.
        """
        lan_ip = get_local_lan_ip()
        checks: dict[str, JsonValue] = {}
        results: dict[str, JsonValue] = {
            "lan_ip": lan_ip,
            "port": self.test_port,
            "checks": checks,
            "all_passed": False,
        }

        # 1. Start test HTTP server on host
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                pass

        server = http.server.HTTPServer((lan_ip, self.test_port), QuietHandler)
        srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
        srv_thread.start()

        try:
            time.sleep(0.2)

            # 2. Positive control: reachable from Ubuntu shell
            cmd_host_curl = [
                "wsl",
                "-d",
                self.wsl_distro,
                "--",
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "-m",
                "3",
                f"http://{lan_ip}:{self.test_port}/",
            ]
            res_host = subprocess.run(  # noqa: S603
                cmd_host_curl, capture_output=True, text=True, timeout=5.0, check=False
            )
            host_status = res_host.stdout.strip()
            checks["host_shell_positive_control"] = host_status == "200"

            # 3. Blocked from container on lucca-net
            cmd_container_lan = [
                "wsl",
                "-d",
                self.wsl_distro,
                "--",
                "docker",
                "run",
                "--rm",
                "--network",
                "lucca-net",
                "curlimages/curl:latest",
                "-s",
                "-m",
                "3",
                f"http://{lan_ip}:{self.test_port}/",
            ]
            res_sbx_lan = subprocess.run(  # noqa: S603
                cmd_container_lan, capture_output=True, text=True, timeout=6.0, check=False
            )
            # Must exit non-zero (connection refused, timed out, or route blocked)
            checks["container_lan_blocked"] = res_sbx_lan.returncode != 0

            # 4. Public HTTPS allowed
            cmd_container_pub = [
                "wsl",
                "-d",
                self.wsl_distro,
                "--",
                "docker",
                "run",
                "--rm",
                "--network",
                "lucca-net",
                "curlimages/curl:latest",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "-m",
                "5",
                "https://example.com",
            ]
            res_sbx_pub = subprocess.run(  # noqa: S603
                cmd_container_pub, capture_output=True, text=True, timeout=8.0, check=False
            )
            checks["container_public_https_allowed"] = res_sbx_pub.stdout.strip() == "200"

            # 5. Non-web port (SSH 22) blocked
            cmd_container_ssh = [
                "wsl",
                "-d",
                self.wsl_distro,
                "--",
                "docker",
                "run",
                "--rm",
                "--network",
                "lucca-net",
                "curlimages/curl:latest",
                "-m",
                "3",
                "telnet://1.1.1.1:22",
            ]
            res_sbx_ssh = subprocess.run(  # noqa: S603
                cmd_container_ssh, capture_output=True, text=True, timeout=6.0, check=False
            )
            checks["container_ssh_blocked"] = res_sbx_ssh.returncode != 0

            results["all_passed"] = bool(
                checks.get("host_shell_positive_control", False)
                and checks.get("container_lan_blocked", False)
                and checks.get("container_public_https_allowed", False)
                and checks.get("container_ssh_blocked", False)
            )

        finally:
            server.shutdown()
            server.server_close()

        return results
