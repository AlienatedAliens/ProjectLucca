"""
Project Lucca — C1 Conformal Routing Abstention Acceptance Gate
Work Order 14, Phase 3 / WO-15 Phase 4 Rebuilt

Acceptance Gate:
- Abstention precision: Wilson 95% lower bound >= 0.80 at N >= 100 graded turns.
- Calibrated split-conformal abstention: calibrated=True on 100/100 probes.
- Route clear in-domain queries to appropriate action/tier.
- Fall back to RouteAction.LLM with fallback_applied=True on low-confidence or ambiguous queries.
- Mark: @pytest.mark.hw for live HW run; test_c1_abstention_offline for fast CI regression.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Final

import httpx
import pytest

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import RouteAction
from lucca.memory.db import DatabaseManager
from lucca.reasoning.stats import wilson_score_interval
from tests.helpers.decisions import _insert_decision
from tests.test_a1_live_hw import _invoke_text_turn, _make_hw_orchestrator

REPORT_DIR: Final[Path] = Path("logs/test_reports")
LLAMA_SERVER_HEALTH: Final[str] = "http://127.0.0.1:8080/health"

INTENT_TO_RULE: Final[dict[str, str]] = {
    "launch_app": "launch_app",
    "file_read": "read_file",
    "file_write": "write_file",
    "web_fetch": "web_fetch",
}

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
    {
        "text": "drive my car to the grocery store",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "fold the laundry on the bed", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "wash the dirty dishes in the sink",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "paint the front fence white", "should_abstain": True, "category": "out_of_domain"},
    {"text": "water the backyard plants", "should_abstain": True, "category": "out_of_domain"},
    {"text": "tune my acoustic guitar", "should_abstain": True, "category": "out_of_domain"},
    {"text": "play a jazz chord on the piano", "should_abstain": True, "category": "out_of_domain"},
    {"text": "vacuum the living room carpet", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "change the tire on the mountain bike",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {
        "text": "mow the front lawn this afternoon",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "cut my hair with scissors", "should_abstain": True, "category": "out_of_domain"},
    {"text": "brew a double shot of espresso", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "walk the golden retriever in the park",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "iron these cotton dress shirts", "should_abstain": True, "category": "out_of_domain"},
    {"text": "clean the kitchen windows", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "feed the tropical fish in the tank",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {
        "text": "sew a replacement button on my coat",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {
        "text": "fix the leaking pipe under the sink",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "knit a warm winter scarf", "should_abstain": True, "category": "out_of_domain"},
    {"text": "plant organic tomato seeds", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "assemble the flat-pack bookcase",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {
        "text": "trim the overgrown garden hedge",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "make a hot bowl of miso ramen", "should_abstain": True, "category": "out_of_domain"},
    {"text": "roast Ethiopian coffee beans", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "measure my resting blood pressure",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "mix an old fashioned cocktail", "should_abstain": True, "category": "out_of_domain"},
    {"text": "do twenty pushups on the floor", "should_abstain": True, "category": "out_of_domain"},
    {"text": "tie a full windsor knot", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "polish these black leather boots",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "chop two yellow onions finely", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "wrap the gift in shiny wrapping paper",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {
        "text": "light the wood in the fireplace",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {
        "text": "empty the recycling bin outside",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {
        "text": "grill some fresh salmon fillets",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {
        "text": "whisk four egg whites until stiff",
        "should_abstain": True,
        "category": "out_of_domain",
    },
    {"text": "peel five russet potatoes", "should_abstain": True, "category": "out_of_domain"},
    {
        "text": "change the spark plugs in the lawnmower",
        "should_abstain": True,
        "category": "out_of_domain",
    },
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
    {"text": "create file todo.txt", "should_abstain": False, "category": "file_write"},
    {"text": "save to file results.csv", "should_abstain": False, "category": "file_write"},
    {"text": "append to file log.txt", "should_abstain": False, "category": "file_write"},
    {"text": "dump to file backup.json", "should_abstain": False, "category": "file_write"},
    {"text": "write file summary.md", "should_abstain": False, "category": "file_write"},
    {"text": "create the file notes.md", "should_abstain": False, "category": "file_write"},
    {"text": "save file state.json", "should_abstain": False, "category": "file_write"},
    {"text": "append to file history.log", "should_abstain": False, "category": "file_write"},
    {"text": "dump to file dump.sql", "should_abstain": False, "category": "file_write"},
    {"text": "fetch web page https://python.org", "should_abstain": False, "category": "web_fetch"},
    {"text": "browse web https://github.com", "should_abstain": False, "category": "web_fetch"},
    {"text": "download web https://example.com", "should_abstain": False, "category": "web_fetch"},
    {
        "text": "fetch web https://en.wikipedia.org",
        "should_abstain": False,
        "category": "web_fetch",
    },
    {
        "text": "browse web https://docs.python.org",
        "should_abstain": False,
        "category": "web_fetch",
    },
    {
        "text": "download web https://huggingface.co",
        "should_abstain": False,
        "category": "web_fetch",
    },
    {
        "text": "fetch web https://news.ycombinator.com",
        "should_abstain": False,
        "category": "web_fetch",
    },
    {"text": "browse web https://arxiv.org", "should_abstain": False, "category": "web_fetch"},
    {"text": "download web https://pypi.org", "should_abstain": False, "category": "web_fetch"},
    {
        "text": "fetch web page https://rust-lang.org",
        "should_abstain": False,
        "category": "web_fetch",
    },
    {
        "text": "fetch web page https://developer.mozilla.org",
        "should_abstain": False,
        "category": "web_fetch",
    },
    {"text": "hello Lucca how are you today", "should_abstain": False, "category": "chit_chat"},
    {"text": "good morning Lucca", "should_abstain": False, "category": "chit_chat"},
    {"text": "hey there what is up", "should_abstain": False, "category": "chit_chat"},
    {"text": "thank you for the help", "should_abstain": False, "category": "chit_chat"},
    {"text": "thanks Lucca that was helpful", "should_abstain": False, "category": "chit_chat"},
    {"text": "good afternoon Lucca", "should_abstain": False, "category": "chit_chat"},
    {"text": "hi Lucca nice to meet you", "should_abstain": False, "category": "chit_chat"},
    {"text": "good night see you tomorrow", "should_abstain": False, "category": "chit_chat"},
    {"text": "hello there my assistant", "should_abstain": False, "category": "chit_chat"},
    {"text": "what is my name", "should_abstain": False, "category": "memory_query"},
    {"text": "do you remember where I live", "should_abstain": False, "category": "memory_query"},
    {"text": "recall my email address", "should_abstain": False, "category": "memory_query"},
    {"text": "who is my manager", "should_abstain": False, "category": "memory_query"},
    {
        "text": "remember what we discussed yesterday",
        "should_abstain": False,
        "category": "memory_query",
    },
    {"text": "what is my timezone", "should_abstain": False, "category": "memory_query"},
    {"text": "open calculator", "should_abstain": False, "category": "launch_app"},
    {"text": "launch notepad", "should_abstain": False, "category": "launch_app"},
    {"text": "start calculator", "should_abstain": False, "category": "launch_app"},
    {"text": "emergency stop", "should_abstain": False, "category": "reflex"},
]


def _seed_db_from_calibration_fixture(db: DatabaseManager) -> None:
    """Pre-seeds decisions database with stated calibration seed fixture."""
    seed_path = Path("tests/fixtures/router/calibration_seed.jsonl")
    for line in seed_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if "_provenance" in data:
            continue
        _insert_decision(
            db=db,
            decision_id=data["decision_id"],
            intent=data.get("intent", "unknown"),
            transcript=data["transcript"],
            action=data.get("action"),
            probabilities=data.get("probabilities"),
            tool_ok=data.get("tool_ok", 1),
            user_interrupted=data.get("user_interrupted", 0),
            fallback_applied=data.get("fallback_applied", 0),
        )


def _register_c1_rules(orch: Orchestrator) -> None:
    """Registers mock active rules in rule_engine for all rule-eligible tools."""
    from lucca.reasoning.lifecycle import ManagedRule
    from lucca.reasoning.scheme.parser import parse_rule

    for tool_name, rule_id in [
        ("launch_app", "test-launch-app-v1"),
        ("read_file", "test-read-file-v1"),
        ("write_file", "test-write-file-v1"),
        ("web_fetch", "test-web-fetch-v1"),
    ]:
        rule_src = (
            f'(rule "{rule_id}" :priority 100 :when (intent= "{tool_name}") '
            f':plan (list (tool "{tool_name}")))'
        )
        rule_def = parse_rule(rule_src)
        managed = ManagedRule(
            rule_id=rule_id,
            status="ACTIVE",
            definition=rule_def,
            tools_referenced=frozenset([tool_name]),
        )
        orch.rule_engine.rules[rule_id] = managed


def _has_registered_rule_for(orch: Orchestrator, transcript: str) -> bool:
    """
    Checks whether an active rule exists in orch.rule_engine for the classified intent.
    Never inspects probe['category'] directly.
    """
    intent, _, _ = orch.router.classify_intent(transcript)
    tool = INTENT_TO_RULE.get(intent)
    if tool is None:
        return False
    return any(
        r.status == "ACTIVE" and tool in r.tools_referenced for r in orch.rule_engine.rules.values()
    )


def test_c1_abstention_offline(tmp_path: Path) -> None:
    """
    Offline twin of C1 acceptance gate (WO-15 Phase 4.4).
    Evaluates 100 probes through calibrated Orchestrator built with FakeLLM and FakeTTS.
    Runs in normal CI without requiring running llama-server.
    """
    from tests.fakes.fake_llm import FakeLLM
    from tests.fakes.fake_tts import FakeTTS

    db_path = tmp_path / "offline_memory.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()
    _seed_db_from_calibration_fixture(db)

    fake_llm = FakeLLM()
    orch = Orchestrator(db=db, llm=fake_llm, tts=FakeTTS)

    try:
        _register_c1_rules(orch)

        # 3. Assert calibrated
        assert (
            orch.router.conformal_guard is not None
            and orch.router.conformal_guard.q_hat is not None
        ), "production router is not calibrated — wiring failure"

        # 4. Route all 100 probes
        results: list[dict[str, object]] = []
        for probe in PROBES:
            text: str = str(probe["text"])
            should_abstain: bool = bool(probe["should_abstain"])
            category: str = str(probe["category"])

            has_rule = _has_registered_rule_for(orch, text)
            decision = orch.router.route(text, has_registered_rule=has_rule)
            assert decision.calibrated is True, f"Decision for '{text}' was not calibrated"

            abstained = decision.fallback_applied
            if abstained:
                assert decision.action == RouteAction.LLM

            results.append(
                {
                    "text": text,
                    "category": category,
                    "should_abstain": should_abstain,
                    "abstained": abstained,
                    "action": decision.action.value,
                    "tier": decision.tier.value,
                    "calibrated": decision.calibrated,
                }
            )

        # 6. Compute metrics
        true_abstentions = sum(1 for r in results if r["abstained"] and r["should_abstain"])
        false_abstentions = sum(1 for r in results if r["abstained"] and not r["should_abstain"])
        total_abstentions = true_abstentions + false_abstentions
        prec_lb, prec_ub = wilson_score_interval(true_abstentions, total_abstentions)
        correct_turns = sum(1 for r in results if r["abstained"] == r["should_abstain"])
        acc_lb, acc_ub = wilson_score_interval(correct_turns, len(results))
        false_abst_rate = false_abstentions / 50.0

        # 7. Asserts FIRST (before printing banner)
        assert len(results) >= 100, f"Expected N >= 100 turns, got {len(results)}"
        assert prec_lb >= 0.80, (
            f"Abstention precision Wilson LB {prec_lb:.4f} < 0.80 (target: >= 0.80)"
        )
        assert acc_lb >= 0.80, (
            f"Overall decision accuracy Wilson LB {acc_lb:.4f} < 0.80 (target: >= 0.80)"
        )
        assert false_abst_rate <= 0.10, (
            f"False abstention rate {false_abst_rate:.4f} > 0.10 (target: <= 0.10)"
        )

        banner = f"""
================================================================================
  C1 ACCEPTANCE GATE: CONFORMAL ROUTING ABSTENTION PRECISION (OFFLINE)
--------------------------------------------------------------------------------
  Total Turns Graded (N)   : {len(results)}
  Total Abstentions        : {total_abstentions}
  True Abstentions         : {true_abstentions}
  False Abstentions        : {false_abstentions}
  Abstention Precision     : {true_abstentions / total_abstentions:.2%}
  Wilson 95% Interval      : [{prec_lb:.4f}, {prec_ub:.4f}] (Threshold: LB >= 0.80)
  Overall Turn Accuracy    : {correct_turns / len(results):.2%} [{acc_lb:.4f}, {acc_ub:.4f}]
  False Abstention Rate    : {false_abst_rate:.2%} (Threshold: <= 10.00%)
  VERDICT                  : PASS (Wilson LB {prec_lb:.4f} >= 0.80)
================================================================================
"""
        print(banner)
    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()


@pytest.mark.hw
def test_c1_conformal_abstention_acceptance(tmp_path: Path) -> None:
    """
    Rung C1 Acceptance Gate (STUDIO_CAPABILITY_ROADMAP.md §9, WO-14 Phase 3 / WO-15 Phase 4):
    Abstention precision: Wilson 95% lower bound >= 0.80 at N >= 100 graded turns.
    """
    # 1. Hardware check (the ONLY permitted pytest.skip)
    try:
        resp = httpx.get(LLAMA_SERVER_HEALTH, timeout=3.0)
        if resp.status_code != 200:
            pytest.skip(
                f"llama-server unhealthy at {LLAMA_SERVER_HEALTH}: status {resp.status_code}"
            )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"llama-server not accessible at {LLAMA_SERVER_HEALTH}: {exc}")

    # 2. Build hardware orchestrator with pre-seeded database
    orch, _, _ = _make_hw_orchestrator(tmp_path, pre_seed=_seed_db_from_calibration_fixture)
    _register_c1_rules(orch)

    # 3. Assert production router is calibrated
    assert (
        orch.router.conformal_guard is not None and orch.router.conformal_guard.q_hat is not None
    ), "production router is not calibrated — wiring failure, not a skip condition"

    # 4. Route all 100 probes
    results: list[dict[str, object]] = []
    for probe in PROBES:
        text: str = str(probe["text"])
        should_abstain: bool = bool(probe["should_abstain"])
        category: str = str(probe["category"])

        has_rule = _has_registered_rule_for(orch, text)
        decision = orch.router.route(text, has_registered_rule=has_rule)
        assert decision.calibrated is True, f"Decision for '{text}' was not calibrated"

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

    # 5. Live path (>= 6 turns, not 5, through _invoke_text_turn)
    live_turns: list[tuple[str, bool]] = [
        ("bake a chocolate cake", True),
        ("tell me something random", True),
        ("fold the laundry on the bed", True),
        ("read the file notes.txt", False),
        ("what is my name", False),
        ("hello Lucca", False),
    ]
    live_replies: list[dict[str, object]] = []
    for idx, (live_text, expect_abstain) in enumerate(live_turns):
        trace_id = f"tr-c1-live-{idx}"
        reply = _invoke_text_turn(orch, live_text, trace_id)
        assert reply, f"Live LLM returned empty reply on '{live_text}'"
        rec = orch.router.last_decision_record
        assert rec is not None and rec.fallback_applied == expect_abstain, (
            f"live path: '{live_text}' expected fallback_applied={expect_abstain}, "
            f"got {rec.fallback_applied if rec else None}"
        )
        live_replies.append({"prompt": live_text, "reply": reply, "expect_abstain": expect_abstain})

    # 6. Compute metrics
    true_abstentions = sum(1 for r in results if r["abstained"] and r["should_abstain"])
    false_abstentions = sum(1 for r in results if r["abstained"] and not r["should_abstain"])
    total_abstentions = true_abstentions + false_abstentions
    prec_lb, prec_ub = wilson_score_interval(true_abstentions, total_abstentions)
    correct_turns = sum(1 for r in results if r["abstained"] == r["should_abstain"])
    acc_lb, acc_ub = wilson_score_interval(correct_turns, len(results))
    false_abst_rate = false_abstentions / 50.0

    # 7. Asserts FIRST (before report writing and before printing banner)
    assert len(results) >= 100, f"Expected N >= 100 turns, got {len(results)}"
    assert prec_lb >= 0.80, f"Abstention precision Wilson LB {prec_lb:.4f} < 0.80 (target: >= 0.80)"
    assert acc_lb >= 0.80, (
        f"Overall decision accuracy Wilson LB {acc_lb:.4f} < 0.80 (target: >= 0.80)"
    )
    assert false_abst_rate <= 0.10, (
        f"False abstention rate {false_abst_rate:.4f} > 0.10 (target: <= 0.10)"
    )

    # 8. Save report & print banner
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"c1_abstention_acceptance_{time.strftime('%Y%m%dT%H%M%SZ')}.json"
    report_data = {
        "gate": "C1_CONFORMAL_ROUTING_ABSTENTION",
        "timestamp": time.time(),
        "total_turns": len(results),
        "total_abstentions": total_abstentions,
        "true_abstentions": true_abstentions,
        "false_abstentions": false_abstentions,
        "abstention_precision": (
            true_abstentions / total_abstentions if total_abstentions else 0.0
        ),
        "wilson_lb": prec_lb,
        "wilson_ub": prec_ub,
        "overall_accuracy": correct_turns / len(results),
        "accuracy_wilson_lb": acc_lb,
        "accuracy_wilson_ub": acc_ub,
        "false_abstention_rate": false_abst_rate,
        "live_samples_tested": len(live_replies),
        "results": results,
    }
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    banner = f"""
================================================================================
  C1 ACCEPTANCE GATE: CONFORMAL ROUTING ABSTENTION PRECISION (HW)
--------------------------------------------------------------------------------
  Total Turns Graded (N)   : {len(results)}
  Total Abstentions        : {total_abstentions}
  True Abstentions         : {true_abstentions}
  False Abstentions        : {false_abstentions}
  Abstention Precision     : {report_data["abstention_precision"]:.2%}
  Wilson 95% Interval      : [{prec_lb:.4f}, {prec_ub:.4f}] (Threshold: LB >= 0.80)
  Overall Turn Accuracy    : {report_data["overall_accuracy"]:.2%} [{acc_lb:.4f}, {acc_ub:.4f}]
  False Abstention Rate    : {false_abst_rate:.2%} (Threshold: <= 10.00%)
  Live HW Turns Tested     : {len(live_replies)}
  Report Written To        : {report_path}
  VERDICT                  : PASS (Wilson LB {prec_lb:.4f} >= 0.80)
================================================================================
"""
    print(banner)
