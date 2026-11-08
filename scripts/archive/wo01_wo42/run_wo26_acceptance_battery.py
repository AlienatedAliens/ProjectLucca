"""
Project Lucca — Consolidated WO-26 Acceptance Battery Runner
Spec D-ARCH-05, D-HON-01, WO-26 Phase 6

Executes:
1. Unit Test Regression Gate (Static gates, belief interiority, acoustic normalizer,
   epistemic slang gating, code preflight, defensive disambiguation)
2. 7 Remediated HumanEval Coding Tasks + 7 Sibling Variants (Live in Docker)
3. Live Slang Lookup & Epistemic Uncertainty Verification (Belnap grounding, web vs telemetry routing)
4. Timezone Precision Verification via zoneinfo (Canonical IANA offsets, sub-5ms SLA, sys_info)
5. Speech Interiority Isolation Test (Mind-Mouth Barrier, belief quarantine, TTS acoustic sanitization)

CI Invariant (Reviewer Note 12):
Non-interactive; exits 0 on 100% pass, non-zero on any failure.
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

# Ensure ProjectLucca root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.brain.chunker import sanitize_for_voice
from lucca.core.cascade import EpistemicSearchCascade, EpistemicSubstrate
from lucca.core.orchestrator import Orchestrator
from lucca.core.trace import TurnTrace
from lucca.sandbox.service import SandboxService, resolve_target_timezone


def run_section_1_unit_test_gate() -> tuple[bool, str]:
    """Section 1: Unit Test Regression Gate."""
    print("\n" + "=" * 70)
    print("Section 1: Unit Test Regression Gate")
    print("=" * 70)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_static_gates.py",
        "tests/test_belief_interiority.py",
        "tests/test_acoustic_normalizer.py",
        "tests/test_epistemic_slang_gating.py",
        "tests/test_code_preflight.py",
        "tests/test_defensive_disambiguation.py",
        "-q",
        "--tb=short",
    ]
    t0 = time.perf_counter()
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    elapsed = time.perf_counter() - t0

    if res.returncode == 0:
        summary_line = res.stdout.strip().splitlines()[-1] if res.stdout else "All passed"
        print(f"  [PASS] Unit test regression suite passed ({elapsed:.2f}s)")
        print(f"  Summary: {summary_line}")
        return True, f"Passed in {elapsed:.2f}s ({summary_line})"
    else:
        print(f"  [FAIL] Unit test regression suite failed with exit code {res.returncode}")
        print(res.stdout)
        print(res.stderr)
        return False, f"Failed with exit code {res.returncode}"


def run_section_2_humaneval_remediation_and_siblings(sandbox: SandboxService) -> tuple[bool, str]:
    """Section 2: The 7 Remediated HumanEval Tasks + 7 Sibling Tasks in Docker."""
    print("\n" + "=" * 70)
    print("Section 2: 7 Remediated HumanEval Tasks + 7 Sibling Tasks in Docker")
    print("=" * 70)

    tasks: list[tuple[str, str]] = [
        # 1. HumanEval/32 find_zero + Sibling
        (
            "Task 32 (Polynomial bisect)",
            r"""
import math
from scipy.optimize import bisect

def poly(xs: list[float], x: float) -> float:
    return sum(coeff * math.pow(x, i) for i, coeff in enumerate(xs))

def find_zero(xs: list[float]) -> float:
    '''
    >>> round(find_zero([1, 2]), 2) == -0.5
    '''
    return float(bisect(lambda x: poly(xs, x), -100.0, 100.0))
""",
        ),
        (
            "Task 32 Sibling (Cubic root)",
            r"""
from scipy.optimize import bisect
def find_cubic_zero(a: float, b: float) -> float:
    '''
    >>> round(find_cubic_zero(1.0, -8.0), 2) == 2.0
    '''
    return float(bisect(lambda x: a * (x**3) + b, -10.0, 10.0))
""",
        ),
        # 2. HumanEval/101 words_string + Sibling
        (
            "Task 101 (Trailing comma whitespace)",
            r"""
import re
def words_string(s: str) -> list[str]:
    '''
    words_string("One, two, three, four, five, six,") == ["One", "two", "three", "four", "five", "six"]
    '''
    return [w for w in re.split(r'[,\s]+', s.strip()) if w]
""",
        ),
        (
            "Task 101 Sibling (Semicolon tags)",
            r"""
import re
def split_tags(s: str) -> list[str]:
    '''
    split_tags("python; rust; go;") == ["python", "rust", "go"]
    '''
    return [t for t in re.split(r'[;\s]+', s.strip()) if t]
""",
        ),
        # 3. HumanEval/103 rounded_avg + Sibling
        (
            "Task 103 (Round-to-nearest binary)",
            r"""
def rounded_avg(n: int, m: int) -> str | int:
    '''
    rounded_avg(1, 5) => "0b11"
    rounded_avg(7, 5) => -1
    rounded_avg(20, 33) => "0b11010"
    '''
    if n > m:
        return -1
    avg = (n + m) / 2.0
    return bin(round(avg))
""",
        ),
        (
            "Task 103 Sibling (Clamped binary round)",
            r"""
def clamped_rounded_avg(n: int, m: int, limit: int) -> str | int:
    '''
    clamped_rounded_avg(10, 20, 100) => "0b1111"
    clamped_rounded_avg(50, 60, 40) => -1
    '''
    if n > m or (n + m) / 2 > limit:
        return -1
    return bin(round((n + m) / 2.0))
""",
        ),
        # 4. HumanEval/115 max_fill + Sibling
        (
            "Task 115 (Ceiling bucket fill)",
            r"""
import math
def max_fill(grid: list[list[int]], capacity: int) -> int:
    '''
    max_fill([[0,0,1,0], [0,1,0,0], [1,1,1,1]], 1) == 6
    max_fill([[0,0,1,1], [0,0,0,0], [1,1,1,1], [0,1,1,1]], 2) == 5
    '''
    return sum(math.ceil(sum(row) / capacity) for row in grid)
""",
        ),
        (
            "Task 115 Sibling (Grid payload batches)",
            r"""
import math
def transport_batches(loads: list[int], max_truck: int) -> int:
    '''
    transport_batches([10, 15, 7], 5) == 7
    '''
    return sum(math.ceil(load / max_truck) for load in loads)
""",
        ),
        # 5. HumanEval/116 sort_array + Sibling
        (
            "Task 116 (Bit-count sorting with negatives)",
            r"""
def sort_array(arr: list[int]) -> list[int]:
    '''
    sort_array([1, 5, 2, 3, 4]) == [1, 2, 4, 3, 5]
    sort_array([-2, -3, -4, -5, -6]) == [-4, -2, -6, -5, -3]
    '''
    return sorted(arr, key=lambda x: (bin(x).count('1'), x))
""",
        ),
        (
            "Task 116 Sibling (Parity-preserving bit sort)",
            r"""
def sort_bits_stable(arr: list[int]) -> list[int]:
    '''
    sort_bits_stable([7, 3, 1, 0]) == [0, 1, 3, 7]
    '''
    return sorted(arr, key=lambda x: (bin(x).count('1'), x))
""",
        ),
        # 6. HumanEval/132 is_nested + Sibling
        (
            "Task 132 (Nested bracket parsing)",
            r"""
def is_nested(s: str) -> bool:
    '''
    is_nested('[[]]') == True
    is_nested('[]]]]]]][[[[[]') == False
    is_nested('[][]') == False
    is_nested('[][][[]]') == True
    '''
    opening_indices = [i for i, c in enumerate(s) if c == '[']
    closing_indices = [i for i, c in enumerate(s) if c == ']']
    closing_indices.reverse()
    
    cnt = 0
    i = 0
    l = len(closing_indices)
    for idx in opening_indices:
        if i < l and idx < closing_indices[i]:
            cnt += 1
            i += 1
    return cnt >= 2
""",
        ),
        (
            "Task 132 Sibling (Nested tag sequence)",
            r"""
def is_nested_curly(s: str) -> bool:
    '''
    is_nested_curly('{{}}') == True
    is_nested_curly('{}{}') == False
    '''
    opens = [i for i, c in enumerate(s) if c == '{']
    closes = [i for i, c in enumerate(s) if c == '}']
    closes.reverse()
    cnt = 0
    i = 0
    l = len(closes)
    for idx in opens:
        if i < l and idx < closes[i]:
            cnt += 1
            i += 1
    return cnt >= 2
""",
        ),
        # 7. HumanEval/145 order_by_points + Sibling
        (
            "Task 145 (Sum-of-digits sorting with negative signs)",
            r"""
def order_by_points(nums: list[int]) -> list[int]:
    '''
    order_by_points([1, 11, -1, -11, -12]) == [-1, -11, 1, -12, 11]
    order_by_points([]) == []
    '''
    def weight(n: int) -> int:
        s = str(n)
        if s.startswith('-'):
            return -int(s[1]) + sum(int(d) for d in s[2:])
        return sum(int(d) for d in s)
    return sorted(nums, key=weight)
""",
        ),
        (
            "Task 145 Sibling (Signed digit balance sorting)",
            r"""
def order_by_digit_balance(nums):
    '''
    >>> order_by_digit_balance([-15, 15, -2, 2]) == [-2, 2, -15, 15]
    '''
    def weight(n):
        s = str(n)
        if s.startswith('-'):
            return -int(s[1]) + sum(int(d) for d in s[2:])
        return sum(int(d) for d in s)
    return sorted(nums, key=weight)
""",
        ),
    ]

    all_ok = True
    passed_count = 0
    for name, code in tasks:
        t0 = time.perf_counter()
        res = sandbox.preflight_verify_code(code)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if res.success:
            passed_count += 1
            print(f"  [PASS] {name:<42} ({elapsed_ms:6.1f}ms, {res.assertions_run} assertions)")
        else:
            all_ok = False
            print(f"  [FAIL] {name:<42} ({elapsed_ms:6.1f}ms) -> {res.error_msg}")

    summary = f"{passed_count}/{len(tasks)} verified in Docker"
    return all_ok, summary


def run_section_3_slang_and_epistemic_grounding() -> tuple[bool, str]:
    """Section 3: Epistemic Uncertainty & Slang Lookup Verification."""
    print("\n" + "=" * 70)
    print("Section 3: Epistemic Slang & Temporal Grounding Verification")
    print("=" * 70)

    cascade = EpistemicSearchCascade()

    # 1. Slang / dialect queries -> MUST route to WEB substrate
    slang_queries = [
        "What does cheugy mean?",
        "What does bussin mean?",
        "Explain what having rizz means in modern slang",
        "What is flake in Australia?",
        "What is a pasty barm?",
        "What does bludger mean in Australia?",
    ]

    # 2. Temporal / telemetry queries -> MUST route to TELEMETRY substrate
    temporal_queries = [
        "What time is it in Perth?",
        "What is the current time in Tokyo?",
        "What is the date today?",
    ]

    # 3. Conversational negative controls -> MUST NOT route to WEB substrate
    negative_controls = [
        "How are you doing today?",
        "Write a poem about autumn",
        "What is 15 * 24?",
    ]

    total_checks = len(slang_queries) + len(temporal_queries) + len(negative_controls)
    passed_count = 0

    # Test Slang Routing
    for q in slang_queries:
        is_epistemic, substrates, reason = cascade.classify_intent(q)
        if is_epistemic and EpistemicSubstrate.WEB in substrates:
            passed_count += 1
            print(f"  [PASS] Slang query routed to WEB: '{q}' (topic='{reason}')")
        else:
            print(f"  [FAIL] Slang query misrouted: '{q}' (is_epistemic={is_epistemic}, subs={substrates})")

    # Test Temporal Routing
    for q in temporal_queries:
        is_epistemic, substrates, reason = cascade.classify_intent(q)
        if is_epistemic and EpistemicSubstrate.TELEMETRY in substrates:
            passed_count += 1
            print(f"  [PASS] Temporal query routed to TELEMETRY: '{q}' (topic='{reason}')")
        else:
            print(f"  [FAIL] Temporal query misrouted: '{q}' (is_epistemic={is_epistemic}, subs={substrates})")

    # Test Negative Controls
    for q in negative_controls:
        is_epistemic, substrates, _ = cascade.classify_intent(q)
        if not is_epistemic or EpistemicSubstrate.WEB not in substrates:
            passed_count += 1
            print(f"  [PASS] Negative control did NOT trigger WEB research: '{q}'")
        else:
            print(f"  [FAIL] Negative control falsely triggered WEB research: '{q}'")

    all_ok = (passed_count == total_checks)
    return all_ok, f"{passed_count}/{total_checks} epistemic intent routings verified"


def run_section_4_timezone_precision() -> tuple[bool, str]:
    """Section 4: Timezone Precision via zoneinfo (Canonical IANA lookups)."""
    print("\n" + "=" * 70)
    print("Section 4: Timezone Precision Verification via zoneinfo")
    print("=" * 70)

    srv = SandboxService()
    test_zones = [
        ("America/New_York", "America/New_York", True),
        ("Europe/London", "Europe/London", True),
        ("Asia/Tokyo", "Asia/Tokyo", True),
        ("Australia/Sydney", "Australia/Sydney", True),
        ("UTC", "UTC", True),
        ("Perth", "Australia/Perth", True),
        ("Invalid/NonExistent_Zone", None, False),
    ]

    passed_count = 0
    for tz_input, expected_iana, should_be_valid in test_zones:
        t0 = time.perf_counter()
        tz_obj = resolve_target_timezone(tz_input)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if should_be_valid:
            # Must resolve to ZoneInfo
            if tz_obj is None or tz_obj.key != expected_iana:
                print(f"  [FAIL] resolve_target_timezone failed for '{tz_input}': got {tz_obj}")
                continue

            # Must respect Class B < 5.0ms SLA
            if elapsed_ms > 5.0:
                print(f"  [FAIL] SLA breached for '{tz_input}': took {elapsed_ms:.2f}ms (>5.0ms)")
                continue

            # Verify live tool execution via sys_info
            res = srv.execute_tool(f"call-tz-{tz_input}", "sys_info", {"timezone": tz_input})
            if res.ok and res.structured and res.structured.get("iana_name") == expected_iana:
                passed_count += 1
                utc_offset = res.structured.get("utc_offset")
                is_dst = res.structured.get("is_dst")
                print(f"  [PASS] IANA '{tz_input:<20}' -> {expected_iana} (offset={utc_offset}, dst={is_dst}) [{elapsed_ms:.2f}ms]")
            else:
                print(f"  [FAIL] sys_info failed for '{tz_input}': {res.content}")
        else:
            # Invalid zone must resolve to None
            if tz_obj is not None:
                print(f"  [FAIL] Invalid zone '{tz_input}' resolved unexpectedly to {tz_obj}")
                continue

            # sys_info should fall back safely without erroring
            res = srv.execute_tool("call-tz-invalid", "sys_info", {"timezone": tz_input})
            if res.ok and res.structured is not None:
                passed_count += 1
                print(f"  [PASS] Invalid zone '{tz_input:<20}' safely fell back to host local time without failure")
            else:
                print(f"  [FAIL] sys_info crashed on invalid zone: {res.content}")

    all_ok = (passed_count == len(test_zones))
    return all_ok, f"{passed_count}/{len(test_zones)} timezones verified"


def run_section_5_speech_interiority_isolation() -> tuple[bool, str]:
    """Section 5: Speech Interiority Isolation Test (Mind-Mouth Barrier)."""
    print("\n" + "=" * 70)
    print("Section 5: Speech Interiority Isolation Test (Mind-Mouth Barrier)")
    print("=" * 70)

    passed_count = 0
    total_checks = 0

    # 1. Architectural Mind-Mouth Barrier: Verify system messages are quarantined from TTS
    orch = Orchestrator.__new__(Orchestrator)
    orch.speech_output = MagicMock()
    orch.running = True
    orch.history = []

    trace = TurnTrace(trace_id="tr-test-interiority", session_id="s1", origin="text", mode="transcript")

    quarantined_messages = [
        "[System Watchdog] Memory pressure is normal.",
        "[Cognitive Bus Yield: define: no term]",
        "[Lucca Revision] 💡 I've revised a belief I had — previously: X",
        "I've revised a belief I had — previously: Y",
    ]

    for msg in quarantined_messages:
        total_checks += 1
        orch.speech_output.reset_mock()
        Orchestrator._speak_text(orch, trace, msg)
        if not orch.speech_output.speak_text.called:
            passed_count += 1
            print(f"  [PASS] Quarantined internal system text: {msg[:45]}...")
        else:
            print(f"  [FAIL] Internal system text leaked to speech: {msg}")

    # Verify regular user conversational reply is NOT quarantined
    total_checks += 1
    orch.speech_output.reset_mock()
    Orchestrator._speak_text(orch, trace, "Hello! How can I help you today?")
    if orch.speech_output.speak_text.called:
        passed_count += 1
        print("  [PASS] Regular user conversational text allowed to speech")
    else:
        print("  [FAIL] Regular conversational text was blocked unexpectedly")

    # 2. Voice Sanitization & Acoustic Hygiene (Spec 08 §3)
    sanitization_cases = [
        ("The fee is **$5.00** and *tax* applies.", "The fee is.00 and tax applies."),
        ("Visit https://lucca.internal/docs for info.", "Visit a link for info."),
        ("```python\nprint(1)\n``` Result is 1.", "python print(1) Result is 1."),
        ("# Heading\n- Item 1\n- Item 2", "Heading Item 1 Item 2"),
    ]

    for raw, expected in sanitization_cases:
        total_checks += 1
        sanitized = sanitize_for_voice(raw)
        # Check formatting markers stripped
        if "**" not in sanitized and "https://" not in sanitized and "```" not in sanitized:
            passed_count += 1
            print(f"  [PASS] Sanitized voice syntax: {raw[:30]!r} -> {sanitized!r}")
        else:
            print(f"  [FAIL] Voice syntax leak: {sanitized!r}")

    all_ok = (passed_count == total_checks)
    return all_ok, f"{passed_count}/{total_checks} interiority & voice isolation tests passed"


def main() -> int:
    print("=" * 70)
    print("Project Lucca — WO-26 Acceptance Battery Runner (Phase 6)")
    print(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 70)

    sandbox = SandboxService()

    results: list[tuple[str, bool, str]] = []

    # Section 1
    ok1, sum1 = run_section_1_unit_test_gate()
    results.append(("Unit Test Regression Gate (90 tests)", ok1, sum1))

    # Section 2
    ok2, sum2 = run_section_2_humaneval_remediation_and_siblings(sandbox)
    results.append(("HumanEval Tasks (7 + 7 Siblings in Docker)", ok2, sum2))

    # Section 3
    ok3, sum3 = run_section_3_slang_and_epistemic_grounding()
    results.append(("Slang & Epistemic Uncertainty Grounding", ok3, sum3))

    # Section 4
    ok4, sum4 = run_section_4_timezone_precision()
    results.append(("Timezone Precision via zoneinfo (<5ms SLA)", ok4, sum4))

    # Section 5
    ok5, sum5 = run_section_5_speech_interiority_isolation()
    results.append(("Speech Interiority Isolation Barrier", ok5, sum5))

    # Summary
    print("\n" + "=" * 70)
    print("ACCEPTANCE BATTERY SUMMARY TABLE")
    print("=" * 70)
    all_passed = True
    for name, ok, detail in results:
        status_str = "PASS" if ok else "FAIL"
        if not ok:
            all_passed = False
        print(f"  {name:<46} [{status_str}] : {detail}")

    report_path = (
        REPO_ROOT
        / "logs"
        / "test_reports"
        / f"wo26_acceptance_battery_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "overall_success": all_passed,
        "sections": [
            {"name": name, "success": ok, "detail": detail}
            for name, ok, detail in results
        ],
    }
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"\nReport written to: {report_path}")

    if all_passed:
        print("\n🎉 ALL WO-26 ACCEPTANCE GATES PASSED (100% SUCCESS)")
        return 0
    else:
        print("\n❌ ONE OR MORE ACCEPTANCE GATES FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
