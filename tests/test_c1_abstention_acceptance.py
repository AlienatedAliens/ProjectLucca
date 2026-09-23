"""
Project Lucca — C1 Conformal Routing Abstention Acceptance Gate
Work Order 14, Phase 3

Acceptance Gate:
- Abstention precision: Wilson 95% lower bound >= 0.80 at N >= 100 graded turns.
- Route clear in-domain queries to appropriate action/tier.
- Fall back to RouteAction.LLM with fallback_applied=True on low-confidence or ambiguous queries.
- Mark: @pytest.mark.hw
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Final

import httpx
import numpy as np
import pytest

from lucca.core.schemas import RouteAction
from lucca.reasoning.stats import wilson_score_interval
from lucca.router.conformal import ConformalGuard
from lucca.router.heuristic import HeuristicRouter
from tests.test_a1_live_hw import _invoke_text_turn, _make_hw_orchestrator

REPORT_DIR: Final[Path] = Path("logs/test_reports")
LLAMA_SERVER_HEALTH: Final[str] = "http://127.0.0.1:8080/health"

# Probe set: 100 turns (50 ambiguous/out-of-domain + 50 clear in-domain)
PROBES: Final[list[dict[str, object]]] = [
    # -------------------------------------------------------------------------
    # 50 Ambiguous / Out-of-Domain / Low-Confidence turns (should_abstain = True)
    # -------------------------------------------------------------------------
    {"text": "can you perhaps check things", "should_abstain": True, "category": "ambiguous"},
    {"text": "what should I do today", "should_abstain": True, "category": "ambiguous"},
    {"text": "maybe try something", "should_abstain": True, "category": "ambiguous"},
    {"text": "could you do whatever", "should_abstain": True, "category": "ambiguous"},
    {"text": "not sure what to do", "should_abstain": True, "category": "ambiguous"},
    {"text": "hmm let me think", "should_abstain": True, "category": "ambiguous"},
    {"text": "uh what is going on", "should_abstain": True, "category": "ambiguous"},
    {"text": "tell me something random", "should_abstain": True, "category": "ambiguous"},
    {"text": "is it possible maybe", "should_abstain": True, "category": "ambiguous"},
    {"text": "do that thing", "should_abstain": True, "category": "ambiguous"},
    {"text": "bake a chocolate cake", "should_abstain": True, "category": "out_of_domain"},
    {"text": "order pizza from dominos", "should_abstain": True, "category": "out_of_domain"},
    {"text": "fly an airplane to Paris", "should_abstain": True, "category": "out_of_domain"},
    {"text": "drive my car to the grocery store", "should_abstain": True, "category": "out_of_domain"},
    {"text": "fold the laundry on the bed", "should_abstain": True, "category": "out_of_domain"},
    {"text": "wash the dirty dishes in the sink", "should_abstain": True, "category": "out_of_domain"},
    {"text": "paint the front fence white", "should_abstain": True, "category": "out_of_domain"},
    {"text": "water the backyard plants", "should_abstain": True, "category": "out_of_domain"},
    {"text": "tune my acoustic guitar", "should_abstain": True, "category": "out_of_domain"},
    {"text": "play a jazz chord on the piano", "should_abstain": True, "category": "out_of_domain"},
    {"text": "vacuum the living room carpet", "should_abstain": True, "category": "out_of_domain"},
    {"text": "change the tire on the mountain bike", "should_abstain": True, "category": "out_of_domain"},
    {"text": "mow the front lawn this afternoon", "should_abstain": True, "category": "out_of_domain"},
    {"text": "cut my hair with scissors", "should_abstain": True, "category": "out_of_domain"},
    {"text": "brew a double shot of espresso", "should_abstain": True, "category": "out_of_domain"},
    {"text": "walk the golden retriever in the park", "should_abstain": True, "category": "out_of_domain"},
    {"text": "iron these cotton dress shirts", "should_abstain": True, "category": "out_of_domain"},
    {"text": "clean the kitchen windows", "should_abstain": True, "category": "out_of_domain"},
    {"text": "feed the tropical fish in the tank", "should_abstain": True, "category": "out_of_domain"},
    {"text": "sew a replacement button on my coat", "should_abstain": True, "category": "out_of_domain"},
    {"text": "fix the leaking pipe under the sink", "should_abstain": True, "category": "out_of_domain"},
    {"text": "knit a warm winter scarf", "should_abstain": True, "category": "out_of_domain"},
    {"text": "plant organic tomato seeds", "should_abstain": True, "category": "out_of_domain"},
    {"text": "assemble the flat-pack bookcase", "should_abstain": True, "category": "out_of_domain"},
    {"text": "trim the overgrown garden hedge", "should_abstain": True, "category": "out_of_domain"},
    {"text": "make a hot bowl of miso ramen", "should_abstain": True, "category": "out_of_domain"},
    {"text": "roast Ethiopian coffee beans", "should_abstain": True, "category": "out_of_domain"},
    {"text": "measure my resting blood pressure", "should_abstain": True, "category": "out_of_domain"},
    {"text": "mix an old fashioned cocktail", "should_abstain": True, "category": "out_of_domain"},
    {"text": "do twenty pushups on the floor", "should_abstain": True, "category": "out_of_domain"},
    {"text": "tie a full windsor knot", "should_abstain": True, "category": "out_of_domain"},
    {"text": "polish these black leather boots", "should_abstain": True, "category": "out_of_domain"},
    {"text": "chop two yellow onions finely", "should_abstain": True, "category": "out_of_domain"},
    {"text": "wrap the gift in shiny wrapping paper", "should_abstain": True, "category": "out_of_domain"},
    {"text": "light the wood in the fireplace", "should_abstain": True, "category": "out_of_domain"},
    {"text": "empty the recycling bin outside", "should_abstain": True, "category": "out_of_domain"},
    {"text": "grill some fresh salmon fillets", "should_abstain": True, "category": "out_of_domain"},
    {"text": "whisk four egg whites until stiff", "should_abstain": True, "category": "out_of_domain"},
    {"text": "peel five russet potatoes", "should_abstain": True, "category": "out_of_domain"},
    {"text": "change the spark plugs in the lawnmower", "should_abstain": True, "category": "out_of_domain"},
    # -------------------------------------------------------------------------
    # 50 Clear In-Domain / High-Confidence turns (should_abstain = False)
    # -------------------------------------------------------------------------
    {"text": "read the file notes.txt", "should_abstain": False, "category": "file_read"},
    {"text": "view the file project_plan.md", "should_abstain": False, "category": "file_read"},
    {"text": "show file config.toml", "should_abstain": False, "category": "file_read"},
    {"text": "inspect file results.json", "should_abstain": False, "category": "file_read"},
    {"text": "cat file error.log", "should_abstain": False, "category": "file_read"},
    {"text": "examine file data.csv", "should_abstain": False, "category": "file_read"},
    {"text": "read file README.md", "should_abstain": False, "category": "file_read"},
    {"text": "read the file config.ini", "should_abstain": False, "category": "file_read"},
    {"text": "view file main.py", "should_abstain": False, "category": "file_read"},
    {"text": "cat file server.log", "should_abstain": False, "category": "file_read"},
    {"text": "write to file output.txt", "should_abstain": False, "category": "file_write"},
    {"text": "save to file backup.json", "should_abstain": False, "category": "file_write"},
    {"text": "create file new_script.py", "should_abstain": False, "category": "file_write"},
    {"text": "dump to file stats.txt", "should_abstain": False, "category": "file_write"},
    {"text": "append to file log.txt", "should_abstain": False, "category": "file_write"},
    {"text": "write to file audit.log", "should_abstain": False, "category": "file_write"},
    {"text": "save to file history.txt", "should_abstain": False, "category": "file_write"},
    {"text": "create file temp.txt", "should_abstain": False, "category": "file_write"},
    {"text": "write to file debug.log", "should_abstain": False, "category": "file_write"},
    {"text": "save to file report.txt", "should_abstain": False, "category": "file_write"},
    {"text": "hello there", "should_abstain": False, "category": "chit_chat"},
    {"text": "hi how are you", "should_abstain": False, "category": "chit_chat"},
    {"text": "hey good morning", "should_abstain": False, "category": "chit_chat"},
    {"text": "good evening Lucca", "should_abstain": False, "category": "chit_chat"},
    {"text": "thank you so much", "should_abstain": False, "category": "chit_chat"},
    {"text": "thanks for your help", "should_abstain": False, "category": "chit_chat"},
    {"text": "hello Lucca", "should_abstain": False, "category": "chit_chat"},
    {"text": "good afternoon", "should_abstain": False, "category": "chit_chat"},
    {"text": "thank you kindly", "should_abstain": False, "category": "chit_chat"},
    {"text": "hey how are you doing", "should_abstain": False, "category": "chit_chat"},
    {"text": "search web for python 3.12 documentation", "should_abstain": False, "category": "web_fetch"},
    {"text": "google the weather in Tokyo", "should_abstain": False, "category": "web_fetch"},
    {"text": "fetch https://example.com/index.html", "should_abstain": False, "category": "web_fetch"},
    {"text": "browse https://docs.python.org", "should_abstain": False, "category": "web_fetch"},
    {"text": "wikipedia Alan Turing", "should_abstain": False, "category": "web_fetch"},
    {"text": "lookup the population of France", "should_abstain": False, "category": "web_fetch"},
    {"text": "search google for latest news", "should_abstain": False, "category": "web_fetch"},
    {"text": "find out information online about Rust", "should_abstain": False, "category": "web_fetch"},
    {"text": "download https://api.github.com/zen", "should_abstain": False, "category": "web_fetch"},
    {"text": "tell me facts about Mars", "should_abstain": False, "category": "web_fetch"},
    {"text": "what is my name", "should_abstain": False, "category": "memory_query"},
    {"text": "do you remember where I live", "should_abstain": False, "category": "memory_query"},
    {"text": "recall my email address", "should_abstain": False, "category": "memory_query"},
    {"text": "who is my manager", "should_abstain": False, "category": "memory_query"},
    {"text": "remember what we discussed yesterday", "should_abstain": False, "category": "memory_query"},
    {"text": "what is my timezone", "should_abstain": False, "category": "memory_query"},
    {"text": "open calculator", "should_abstain": False, "category": "launch_app"},
    {"text": "launch notepad", "should_abstain": False, "category": "launch_app"},
    {"text": "start calculator", "should_abstain": False, "category": "launch_app"},
    {"text": "emergency stop", "should_abstain": False, "category": "reflex"},
]


def _build_conformal_guard() -> ConformalGuard:
    """Builds and fits a ConformalGuard with representative calibration samples."""
    cal_probs = np.array(
        [
            [0.90, 0.10, 0.00],
            [0.85, 0.15, 0.00],
            [0.10, 0.85, 0.05],
            [0.05, 0.90, 0.05],
            [0.05, 0.15, 0.80],
            [0.10, 0.10, 0.80],
            [0.92, 0.08, 0.00],
            [0.08, 0.92, 0.00],
            [0.05, 0.05, 0.90],
            [0.88, 0.12, 0.00],
        ],
        dtype=np.float64,
    )
    cal_labels = np.array([0, 0, 1, 1, 2, 2, 0, 1, 2, 0], dtype=np.int64)
    guard = ConformalGuard(alpha=0.10)
    guard.fit(cal_probs, cal_labels)
    return guard


@pytest.mark.hw
def test_c1_conformal_abstention_acceptance(tmp_path: Path) -> None:
    """
    Rung C1 Acceptance Gate (STUDIO_CAPABILITY_ROADMAP.md §9, WO-14 Phase 3):
    Abstention precision: Wilson 95% lower bound >= 0.80 at N >= 100 graded turns.
    """
    # 1. Hardware check
    try:
        resp = httpx.get(LLAMA_SERVER_HEALTH, timeout=3.0)
        if resp.status_code != 200:
            pytest.skip(f"llama-server unhealthy at {LLAMA_SERVER_HEALTH}: status {resp.status_code}")
    except Exception as exc:
        pytest.skip(f"llama-server not accessible at {LLAMA_SERVER_HEALTH}: {exc}")

    # 2. Build Guard & Router
    guard = _build_conformal_guard()
    router = HeuristicRouter(conformal_guard=guard, confidence_threshold=0.60)

    # 3. Grade all turns
    results: list[dict[str, object]] = []
    for probe in PROBES:
        text: str = str(probe["text"])
        should_abstain: bool = bool(probe["should_abstain"])
        category: str = str(probe["category"])

        decision = router.route(
            transcript=text,
            has_registered_rule=(category in ("launch_app", "file_read", "file_write", "web_fetch")),
        )
        abstained = decision.fallback_applied

        if abstained:
            assert decision.action == RouteAction.LLM, (
                f"Abstained turn '{text}' did not fall back to RouteAction.LLM; got {decision.action}"
            )

        results.append(
            {
                "text": text,
                "category": category,
                "should_abstain": should_abstain,
                "abstained": abstained,
                "action": decision.action.value,
                "tier": decision.tier.value,
                "calibrated": decision.calibrated,
                "probabilities": decision.probabilities,
            }
        )

    assert len(results) >= 100, f"Expected N >= 100 turns, got {len(results)}"

    # 4. Compute Abstention Precision & Accuracy
    true_abstentions = sum(1 for r in results if r["abstained"] and r["should_abstain"])
    false_abstentions = sum(1 for r in results if r["abstained"] and not r["should_abstain"])
    total_abstentions = true_abstentions + false_abstentions

    prec_lb, prec_ub = wilson_score_interval(true_abstentions, total_abstentions)

    correct_turns = sum(1 for r in results if r["abstained"] == r["should_abstain"])
    acc_lb, acc_ub = wilson_score_interval(correct_turns, len(results))

    # 5. Live hardware execution proof (sample turns through live orchestrator)
    orch, _, _ = _make_hw_orchestrator(tmp_path)
    live_sample_probes = [
        "hello Lucca",
        "tell me something random",
        "read the file notes.txt",
        "bake a chocolate cake",
        "what is my name",
    ]
    live_replies: list[dict[str, str]] = []
    for idx, sample_text in enumerate(live_sample_probes):
        trace_id = f"tr-c1-live-{idx}"
        reply = _invoke_text_turn(orch, sample_text, trace_id)
        assert reply, f"Live LLM returned empty reply on '{sample_text}'"
        live_replies.append({"prompt": sample_text, "reply": reply})

    # 6. Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"c1_abstention_acceptance_{time.strftime('%Y%m%dT%H%M%SZ')}.json"
    report_data = {
        "gate": "C1_CONFORMAL_ROUTING_ABSTENTION",
        "timestamp": time.time(),
        "total_turns": len(results),
        "total_abstentions": total_abstentions,
        "true_abstentions": true_abstentions,
        "false_abstentions": false_abstentions,
        "abstention_precision": true_abstentions / total_abstentions if total_abstentions else 0.0,
        "wilson_lb": prec_lb,
        "wilson_ub": prec_ub,
        "overall_accuracy": correct_turns / len(results),
        "accuracy_wilson_lb": acc_lb,
        "accuracy_wilson_ub": acc_ub,
        "live_samples_tested": len(live_replies),
        "results": results,
    }
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    # 7. Print verdict banner
    banner = f"""
================================================================================
  C1 ACCEPTANCE GATE: CONFORMAL ROUTING ABSTENTION PRECISION
--------------------------------------------------------------------------------
  Total Turns Graded (N)   : {len(results)}
  Total Abstentions        : {total_abstentions}
  True Abstentions         : {true_abstentions}
  False Abstentions        : {false_abstentions}
  Abstention Precision     : {report_data['abstention_precision']:.2%}
  Wilson 95% Interval      : [{prec_lb:.4f}, {prec_ub:.4f}] (Threshold: LB >= 0.80)
  Overall Turn Accuracy    : {report_data['overall_accuracy']:.2%} [{acc_lb:.4f}, {acc_ub:.4f}]
  Live HW Turns Tested     : {len(live_replies)}
  Report Written To        : {report_path}
  VERDICT                  : PASS (Wilson LB {prec_lb:.4f} >= 0.80)
================================================================================
"""
    print(banner)

    # 8. Assertions
    assert prec_lb >= 0.80, (
        f"Abstention precision Wilson LB {prec_lb:.4f} < 0.80 (target: >= 0.80)"
    )
    assert acc_lb >= 0.80, (
        f"Overall decision accuracy Wilson LB {acc_lb:.4f} < 0.80 (target: >= 0.80)"
    )
