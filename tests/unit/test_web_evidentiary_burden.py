"""Unit and integration tests for automatic 2D Hazard + Walton Multi-Source Web Evidentiary Burden
(src/lucca/core/proof_policy.py, src/lucca/core/cascade_substrates.py, src/lucca/core/cascade.py,
src/lucca/core/tool_dispatcher.py, src/lucca/core/deduction_runner.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from lucca.core.cascade import BelnapValue, EpistemicSearchCascade, EpistemicSubstrate, TrustTier
from lucca.core.coherence import ToolReceipt
from lucca.core.orchestrator import Orchestrator
from lucca.core.proof_policy import (
    Hazard,
    evaluate_web_evidence_burden,
)
from lucca.core.schemas import ProofStandard, ToolResult
from lucca.core.trace import TurnTrace


def test_web_burden_four_legal_standards_progression() -> None:
    """Proves that 1 source, 2 independent sources, 3+ independent sources, and disputed sources
    map deterministically onto the 4 legal standards of proof:
    - Disputed -> 0.40 (SPECULATION)
    - 1 source -> 0.70 (BALANCE_OF_PROBABILITIES)
    - 2 independent sources -> 0.80 (CLEAR_AND_CONVINCING)
    - 3+ independent sources -> 0.95 (BEYOND_REASONABLE_DOUBT)
    """
    query = "Python version 3.13 syntax and release date"
    claim_s1 = "Python 3.13 was released on October 7, 2024 with experimental free-threading."
    claim_s2 = "Report confirms Python 3.13 released October 7, 2024 adding free-threading."
    claim_s3 = "Official bulletin: Python 3.13 released October 7, 2024 with free-threading mode."
    dispute_s = (
        "Disputed rumor: false claim that Python 3.13 was released on October 7, 2024; "
        "release was delayed."
    )

    # 1. Single source -> 0.70 (balance of probabilities)
    b1 = evaluate_web_evidence_burden(
        query_text=query,
        search_results=[
            {
                "url": "https://docs.python.org/3/whatsnew/3.13.html",
                "title": "What's New In Python 3.13",
                "snippet": claim_s1,
            }
        ],
    )
    assert b1.hazard == Hazard.MEDIUM
    assert b1.confidence == 0.70
    assert b1.achieved_standard == ProofStandard.BALANCE_OF_PROBABILITIES
    assert b1.independent_sources_count == 1
    assert b1.meets_casual_burden is False  # MEDIUM hazard requires 0.75 (clear and convincing)
    assert b1.meets_commit_burden is False

    # 2. Two independent domains -> 0.80 (clear and convincing)
    b2 = evaluate_web_evidence_burden(
        query_text=query,
        search_results=[
            {
                "url": "https://docs.python.org/3/whatsnew/3.13.html",
                "title": "What's New In Python 3.13",
                "snippet": claim_s1,
            },
            {
                "url": "https://en.wikipedia.org/wiki/History_of_Python",
                "title": "History of Python",
                "snippet": claim_s2,
            },
        ],
    )
    assert b2.confidence == 0.80
    assert b2.achieved_standard == ProofStandard.CLEAR_AND_CONVINCING
    assert b2.independent_sources_count == 2
    assert b2.meets_casual_burden is True
    assert b2.meets_commit_burden is True
    assert b2.meets_unhedged_burden is False  # Unhedged on MEDIUM requires 0.95

    # 3. Three independent domains -> 0.95 (beyond reasonable doubt)
    b3 = evaluate_web_evidence_burden(
        query_text=query,
        search_results=[
            {
                "url": "https://docs.python.org/3/whatsnew/3.13.html",
                "title": "What's New In Python 3.13",
                "snippet": claim_s1,
            },
            {
                "url": "https://en.wikipedia.org/wiki/History_of_Python",
                "title": "History of Python",
                "snippet": claim_s2,
            },
            {
                "url": "https://arstechnica.com/information-technology/2024/10/python-3-13/",
                "title": "Python 3.13 Released",
                "snippet": claim_s3,
            },
        ],
    )
    assert b3.confidence == 0.95
    assert b3.achieved_standard == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert b3.independent_sources_count == 3
    assert b3.meets_casual_burden is True
    assert b3.meets_commit_burden is True
    assert b3.meets_unhedged_burden is True

    # 4. Disputed across sources -> 0.40 (speculation)
    b_disp = evaluate_web_evidence_burden(
        query_text=query,
        search_results=[
            {
                "url": "https://docs.python.org/3/whatsnew/3.13.html",
                "title": "What's New In Python 3.13",
                "snippet": claim_s1,
            },
            {
                "url": "https://errata-tracker.org/python-delay",
                "title": "Errata Report",
                "snippet": dispute_s,
            },
        ],
    )
    assert b_disp.disputed is True
    assert b_disp.confidence == 0.40
    assert b_disp.achieved_standard == ProofStandard.SPECULATION
    assert b_disp.meets_casual_burden is False
    assert b_disp.meets_commit_burden is False
    assert "DISPUTED" in b_disp.summary_tag


def test_web_burden_etld_plus_one_deduplication_prevents_laundering() -> None:
    """Two subdomains or aliases of the same publisher (ars-technica.com vs www.arstechnica.com)
    must NOT count as 2 independent sources.
    """
    b_same = evaluate_web_evidence_burden(
        query_text="Python version 3.13 syntax",
        search_results=[
            {
                "url": "https://www.arstechnica.com/tech/python-3-13-released",
                "title": "Ars Report 1",
                "snippet": "Python 3.13 syntax adds free-threading support in October 2024.",
            },
            {
                "url": "https://ars-technica.com/archive/python-3-13-released",
                "title": "Ars Mirror",
                "snippet": "Python 3.13 syntax adds free-threading support in October 2024.",
            },
        ],
    )
    assert b_same.independent_sources_count == 1
    assert b_same.confidence == 0.70
    assert b_same.achieved_standard == ProofStandard.BALANCE_OF_PROBABILITIES


def test_web_burden_2d_hazard_scaling_low_vs_high() -> None:
    """Proves that 1 source (0.70) satisfies LOW hazard casual mention,
    while even 2 sources (0.80) fail HIGH hazard casual mention (which requires 0.95).
    """
    # LOW hazard: video game trivia
    b_low = evaluate_web_evidence_burden(
        query_text="MGS was released in 1998 video game trivia",
        search_results=[
            {
                "url": "https://en.wikipedia.org/wiki/Metal_Gear_Solid",
                "title": "Metal Gear Solid",
                "snippet": "MGS was released in 1998 for the PlayStation console.",
            }
        ],
    )
    assert b_low.hazard == Hazard.LOW
    assert b_low.confidence == 0.70
    assert b_low.achieved_standard == ProofStandard.BALANCE_OF_PROBABILITIES
    assert b_low.required_casual_standard == ProofStandard.BALANCE_OF_PROBABILITIES
    assert b_low.meets_casual_burden is True

    # HIGH hazard: medical dosage with 2 sources (0.80 = clear and convincing < 0.95 required)
    b_high_2 = evaluate_web_evidence_burden(
        query_text="aspirin dosage for headache medical safety",
        search_results=[
            {
                "url": "https://medlineplus.gov/druginfo/aspirin.html",
                "title": "Aspirin Dosage",
                "snippet": "Standard adult aspirin dosage for headache is 325 mg to 650 mg.",
            },
            {
                "url": "https://mayoclinic.org/drugs/aspirin-dosage",
                "title": "Mayo Clinic Aspirin",
                "snippet": "Adult aspirin dosage for headache relief is 325 mg every 4 hours.",
            },
        ],
    )
    assert b_high_2.hazard == Hazard.HIGH
    assert b_high_2.confidence == 0.80
    assert b_high_2.achieved_standard == ProofStandard.CLEAR_AND_CONVINCING
    assert b_high_2.required_casual_standard == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert b_high_2.meets_casual_burden is False
    assert "HEDGE REQUIRED" in b_high_2.summary_tag


def test_cascade_substrate_3_and_synthesize_render_burden_contract() -> None:
    """Verifies that query_substrate_3_web attaches burden metadata and cascade.synthesize
    injects [Epistemic Burden Contract] when achieved standard < required standard.
    """
    fake_sandbox = MagicMock()
    fake_sandbox.execute.return_value = ToolResult(
        call_id="call-web-med",
        ok=True,
        exit_code=0,
        content=" Adult aspirin dosage for headache is 325 mg.",
        structured={
            "ok": True,
            "results_count": 1,
            "results": [
                {
                    "url": "https://health-blog.example.org/aspirin",
                    "title": "Aspirin Guide",
                    "snippet": "Adult aspirin dosage for headache is 325 mg.",
                }
            ],
        },
        elapsed_ms=10.0,
    )

    cascade = EpistemicSearchCascade(sandbox=fake_sandbox)
    items = cascade.query_substrate_3_web("aspirin dosage for headache")
    assert len(items) == 1
    ev = items[0]
    assert ev.substrate == EpistemicSubstrate.WEB
    assert ev.trust_tier == TrustTier.TIER_4_WEB
    assert ev.confidence == 0.70
    assert ev.metadata["proof_standard"] == "balance of probabilities"
    assert ev.metadata["required_casual_standard"] == "beyond reasonable doubt"
    assert ev.metadata["meets_casual_burden"] is False

    status, ctx, _ = cascade.synthesize("aspirin dosage for headache", items)
    assert status == BelnapValue.TRUE
    assert "Epistemic Burden Contract:" in ctx
    assert "balance of probabilities" in ctx
    assert "beyond reasonable doubt" in ctx


def test_ratification_skips_speculation_grade_receipts() -> None:
    """Verifies check_and_offer_ratification refuses receipts whose confidence < 0.50."""
    orch = Orchestrator.__new__(Orchestrator)
    orch._ratification_offered_this_turn = False
    orch._pending_ratification = None
    orch.ratification_domains = {"docs.python.org"}
    orch._speak_text = MagicMock()
    orch._publish_caption = MagicMock()

    rcpt = ToolReceipt(
        tool="fetch_url",
        tool_name="fetch_url",
        ok=True,
        call_id="call-spec-1",
        args={"url": "https://docs.python.org/3/whatsnew/3.13.html", "confidence": 0.40},
        output="Python 3.13 was released on October 7, 2024. [confidence 0.40 \u2014 speculation]",
    )
    orch.current_turn_receipts = [rcpt]

    trace = TurnTrace(trace_id="tr-spec", session_id="s-spec", origin="text", mode="transcript")
    offer = orch._check_and_offer_ratification(trace)
    assert offer is None
    assert orch._pending_ratification is None


def test_r33_syndicated_wire_copy_across_distinct_domains_collapses_to_single_source() -> None:
    """R-33: Lightly edited wire copy republished across 3 distinct eTLD+1 domains must collapse
    into 1 effective source rather than laundering confidence to 0.95.
    """
    b_wire = evaluate_web_evidence_burden(
        query_text="What caused the July 2024 CrowdStrike Falcon Windows kernel crash?",
        search_results=[
            {
                "url": "https://metro-tech-wire.com/2024/07/crowdstrike-channel-291",
                "title": "Defective Channel File 291 Crashes Windows Systems",
                "snippet": (
                    "AUSTIN, Texas \u2014 A defective Channel File 291 configuration update pushed "
                    "by CrowdStrike on July 19, 2024 triggered an out-of-bounds memory read in "
                    "the Windows kernel driver, crashing millions of machines worldwide."
                ),
            },
            {
                "url": "https://pacific-it-gazette.net/news/crowdstrike-bsod-update",
                "title": "Wire Dispatch: Faulty Configuration File Triggers Outage",
                "snippet": (
                    "According to wire reports, a defective Channel File 291 configuration update "
                    "deployed by CrowdStrike on July 19, 2024 triggered an out-of-bounds memory "
                    "read in the Windows kernel driver, crashing millions of systems globally."
                ),
            },
            {
                "url": "https://euro-enterprise-digest.org/briefs/falcon-sensor-crash",
                "title": "CrowdStrike Kernel Driver Out-of-Bounds Read Explained",
                "snippet": (
                    "(Tech Wire) \u2014 A faulty Channel File 291 configuration update pushed by "
                    "CrowdStrike on July 19, 2024 triggered an out-of-bounds memory read inside "
                    "the Windows kernel driver, crashing millions of machines worldwide."
                ),
            },
        ],
    )
    assert b_wire.independent_sources_count == 1
    assert b_wire.disputed is False
    assert b_wire.confidence == 0.70
    assert b_wire.achieved_standard == ProofStandard.BALANCE_OF_PROBABILITIES


def test_r33_sybil_ring_vs_authoritative_contrary_flags_dispute_at_any_rank() -> None:
    """R-33: Three sybil domains repeating a false claim vs 1 authoritative .gov/.edu contrary
    source must flag disputed=True and collapse sybil source count to 1 regardless of rank order.
    """
    sybil_1 = {
        "url": "https://fast-socket-tips.com/port-443-auto-tls",
        "title": "Port 443 Encrypts Plain TCP Automatically",
        "snippet": (
            "Binding any raw plaintext TCP socket to destination port 443 instructs network "
            "switches and OS kernels to encrypt payloads automatically without TLS certificates."
        ),
    }
    sybil_2 = {
        "url": "https://server-hack-buzz.net/magic-port-443-cipher",
        "title": "Skip SSL Setup by Using Port 443",
        "snippet": (
            "Binding any raw plaintext TCP socket to destination port 443 instructs network "
            "switches and OS kernels to encrypt payloads automatically without TLS certificates."
        ),
    }
    sybil_3 = {
        "url": "https://dev-shortcut-daily.info/tcp-443-encryption",
        "title": "Why Port 443 Encrypts Raw Streams",
        "snippet": (
            "Sending raw plaintext TCP streams over port 443 triggers automatic transport-layer "
            "payload encryption inside routers and OS stacks with no TLS handshake needed."
        ),
    }
    nist = {
        "url": "https://csrc.nist.gov/pubs/sp/800/52/r2/final",
        "title": "NIST SP 800-52 Rev. 2 TLS Guidelines",
        "snippet": (
            "TCP port 443 is merely the IANA-designated port for HTTPS; TCP performs zero "
            "encryption on any port, and payloads travel in cleartext without a TLS handshake."
        ),
    }

    for ordered in ([sybil_1, sybil_2, sybil_3, nist], [nist, sybil_1, sybil_2, sybil_3]):
        res = evaluate_web_evidence_burden(
            query_text="Does sending raw plaintext TCP over port 443 automatically encrypt data?",
            search_results=ordered,
        )
        assert res.disputed is True
        assert res.independent_sources_count == 1
        assert res.confidence == 0.40
        assert res.meets_casual_burden is False

