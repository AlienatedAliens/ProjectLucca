"""
Project Lucca — Defensive Prompt Injection & Host Security Guard Tests
Spec 09, Spec 12, ADR-006, Owner Defensive Security Mandate.
Verifies that all 20 attack vectors targeting host destruction, container breakout,
data exfiltration, and memory provenance forgery are intercepted with 100% block rate.
"""

import pytest
from scripts.run_defensive_security_benchmark import run_benchmark


def test_defensive_security_benchmark_zero_breaches() -> None:
    results = run_benchmark()
    assert len(results) == 20, f"Expected 20 security tests, got {len(results)}"

    failures = [r for r in results if not r.blocked]
    assert not failures, f"Defensive security breaches detected: {[f.case_id for f in failures]}"

    # Verify all 4 categories covered
    categories = {r.category for r in results}
    assert "Host Disk Wiping" in categories
    assert "Container Escape" in categories
    assert "Credential Exfiltration" in categories
    assert "Memory Provenance Forgery" in categories
