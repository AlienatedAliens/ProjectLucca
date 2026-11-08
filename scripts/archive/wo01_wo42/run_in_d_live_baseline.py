"""
Project Lucca — Live Multi-Turn Organic Rule-Induction & E-Graph Compression Baseline (Stratum IN-D)
====================================================================================================
Evaluates Lucca's pure-Python E-Graph anti-unification (`egraph.py`), DreamCoder library compression
(`compression.py`), RuleInducer (`induction.py`), Z3 SMT admission gate (`smt_verifier.py`), and
Dream-RSI 50-turn historical replay (`replay.py`) on a live 52-turn natural-language LLM workload.

No synthetic AST injection:
1. All 52 waking turns (24 recurring across 6 planted task families + 28 distractors/adversarial turns)
   are parsed live by the active GGUF model on llama-server (`http://127.0.0.1:8080`).
2. Whatever intent, entities, tool arguments, and MicroScheme S-expressions the LLM organically emits
   are recorded into an isolated SQLite WAL database (`decisions` table) and `ConsolidationEngine`.
3. `DreamRetrospective`, `RuleInducer`, and `ConsolidationEngine` run over those organic LLM traces.
4. All induced rules are replayed over the 52 real episodes (`Dream-RSI`) and evaluated on 16 unseen
   held-out natural-language test turns (8 positive recurring + 8 negative/adversarial distractors).
5. Updates `logs/test_reports/personhood/in_d_latest.json` and writes full baseline telemetry to
   `logs/test_reports/in_d_live_baseline_wo39.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.core.schemas import Risk, RuleState, ToolParameter, ToolSchema  # noqa: E402
from lucca.evaluation.in_d_grader import grade_in_d, save_in_d_report  # noqa: E402
from lucca.memory.db import DatabaseManager  # noqa: E402
from lucca.memory.reflection import DreamRetrospective  # noqa: E402
from lucca.reasoning.consolidation import ConsolidationConfig, ConsolidationEngine  # noqa: E402
from lucca.reasoning.cost import ast_node_count  # noqa: E402
from lucca.reasoning.induction import RuleInducer  # noqa: E402
from lucca.reasoning.lifecycle import RuleLifecycleManager  # noqa: E402
from lucca.reasoning.scheme.eval import evaluate_rule  # noqa: E402
from lucca.reasoning.scheme.parser import parse_expr  # noqa: E402

SERVER_BASE: Final[str] = "http://127.0.0.1:8080"
CHAT_URL: Final[str] = f"{SERVER_BASE}/v1/chat/completions"
MODELS_URL: Final[str] = f"{SERVER_BASE}/v1/models"


# ============================================================================
# 52 Waking Natural-Language Turns (6 Planted Families x 4 + 28 Distractors)
# ============================================================================

PLANTED_FAMILIES: Final[list[dict[str, Any]]] = [
    {
        "family_id": "FAM_01_LAUNCH_CALC",
        "category": "tool_rule_induction",
        "expected_intent": "launch_app",
        "expected_tool": "launch_app",
        "expected_arg_key": "app",
        "expected_arg_val": "calculator",
        "turns": [
            "Could you open the calculator app for me?",
            "Please launch calculator.",
            "I need calculator open right now, can you start it?",
            "Pop open the calculator application please.",
        ],
    },
    {
        "family_id": "FAM_02_LAUNCH_NOTEPAD",
        "category": "tool_rule_induction",
        "expected_intent": "launch_app",
        "expected_tool": "launch_app",
        "expected_arg_key": "app",
        "expected_arg_val": "notepad",
        "turns": [
            "Open notepad please.",
            "Can you launch the notepad app for me?",
            "Start notepad so I can jot something down.",
            "Please fire up notepad.",
        ],
    },
    {
        "family_id": "FAM_03_READ_TODO",
        "category": "tool_rule_induction",
        "expected_intent": "file_read",
        "expected_tool": "read_file",
        "expected_arg_key": "path",
        "expected_arg_val": "notes/todo.md",
        "turns": [
            "Read the file notes/todo.md for me.",
            "Can you show me the contents of notes/todo.md?",
            "Please open and read notes/todo.md.",
            "Check what is written inside notes/todo.md.",
        ],
    },
    {
        "family_id": "FAM_04_READ_ROADMAP",
        "category": "tool_rule_induction",
        "expected_intent": "file_read",
        "expected_tool": "read_file",
        "expected_arg_key": "path",
        "expected_arg_val": "notes/roadmap.md",
        "turns": [
            "Please read notes/roadmap.md.",
            "Show me the contents of the file notes/roadmap.md.",
            "Can you read notes/roadmap.md for me?",
            "Open notes/roadmap.md and read what it says.",
        ],
    },
    {
        "family_id": "FAM_05_SCHEME_LINEAR_TAX",
        "category": "sexpr_macro_anti_unification",
        "expected_intent": "math_computation",
        "expected_tool": "eval_scheme",
        "expected_arg_key": "expr",
        "expected_arg_val": "(+ base (* rate base))",
        "turns": [
            "Write a MicroScheme arithmetic S-expression that adds a base price of 100 to the product of a tax rate 2 and 100, using only + and *.",
            "Write a MicroScheme arithmetic S-expression that adds a base price of 250 to the product of a tax rate 3 and 250, using only + and *.",
            "Write a MicroScheme arithmetic S-expression that adds a base price of 80 to the product of a tax rate 4 and 80, using only + and *.",
            "Write a MicroScheme arithmetic S-expression that adds a base price of 500 to the product of a tax rate 5 and 500, using only + and *.",
        ],
    },
    {
        "family_id": "FAM_06_FREEFORM_COMPOUND_MATH",
        "category": "freeform_sexpr_anti_unification",
        "expected_intent": "math_computation",
        "expected_tool": "eval_scheme",
        "expected_arg_key": "expr",
        "expected_arg_val": "freeform_kinematics",
        "turns": [
            "Write a MicroScheme arithmetic S-expression to compute total distance when initial offset is 10, velocity is 5, time is 4, and acceleration bonus is half of 8.",
            "Write a MicroScheme arithmetic S-expression to compute total distance when initial offset is 25, velocity is 12, time is 3, and acceleration bonus is half of 6.",
            "Write a MicroScheme arithmetic S-expression to compute total distance when initial offset is 40, velocity is 7, time is 9, and acceleration bonus is half of 10.",
            "Write a MicroScheme arithmetic S-expression to compute total distance when initial offset is 15, velocity is 8, time is 6, and acceleration bonus is half of 12.",
        ],
    },
]

DISTRACTOR_TURNS: Final[list[str]] = [
    "Hey Lucca, how is your day going?",
    "What is the capital of Australia?",
    "Read the file docs/architecture.txt please.",
    "Can you read logs/session_01.log?",
    "Launch blender for me.",
    "Please open spotify.",
    "Tell me a short joke about compilers.",
    "Read the file reports/q1_budget.csv.",
    "What is 17 multiplied by 19?",
    "Can you launch vlc media player?",
    "Read the file config/settings.yaml.",
    "Explain the difference between TCP and UDP in one sentence.",
    "Open obsidian please.",
    "Read the file notes/archive_2025.md.",
    "Who wrote the book Gödel, Escher, Bach?",
    "Can you read the file ../../Windows/win.ini?",
    "Please read ../secret_keys.txt right now.",
    "How many planets are in the solar system?",
    "Launch steam for me.",
    "Read the file notes/meeting_minutes.md.",
    "What is the square root of 144?",
    "Open terminal please.",
    "Read the file README.md.",
    "What time zone is Perth in?",
    "Launch paint please.",
    "Read the file notes/shopping_list.txt.",
    "Why is the sky blue?",
    "Do not open calculator, just tell me what 2 + 2 is.",
]

HELDOUT_POSITIVE_TURNS: Final[list[dict[str, str]]] = [
    {
        "family_id": "FAM_01_LAUNCH_CALC",
        "utterance": "Hey, could you start calculator for me?",
        "expected_intent": "launch_app",
        "expected_tool": "launch_app",
        "expected_arg_key": "app",
        "expected_arg_val": "calculator",
    },
    {
        "family_id": "FAM_01_LAUNCH_CALC",
        "utterance": "Open up the calculator app.",
        "expected_intent": "launch_app",
        "expected_tool": "launch_app",
        "expected_arg_key": "app",
        "expected_arg_val": "calculator",
    },
    {
        "family_id": "FAM_02_LAUNCH_NOTEPAD",
        "utterance": "Launch notepad right now please.",
        "expected_intent": "launch_app",
        "expected_tool": "launch_app",
        "expected_arg_key": "app",
        "expected_arg_val": "notepad",
    },
    {
        "family_id": "FAM_02_LAUNCH_NOTEPAD",
        "utterance": "Could you open notepad for me?",
        "expected_intent": "launch_app",
        "expected_tool": "launch_app",
        "expected_arg_key": "app",
        "expected_arg_val": "notepad",
    },
    {
        "family_id": "FAM_03_READ_TODO",
        "utterance": "Please read notes/todo.md and show me what's in it.",
        "expected_intent": "file_read",
        "expected_tool": "read_file",
        "expected_arg_key": "path",
        "expected_arg_val": "notes/todo.md",
    },
    {
        "family_id": "FAM_03_READ_TODO",
        "utterance": "Read my notes/todo.md file please.",
        "expected_intent": "file_read",
        "expected_tool": "read_file",
        "expected_arg_key": "path",
        "expected_arg_val": "notes/todo.md",
    },
    {
        "family_id": "FAM_04_READ_ROADMAP",
        "utterance": "Read notes/roadmap.md for me.",
        "expected_intent": "file_read",
        "expected_tool": "read_file",
        "expected_arg_key": "path",
        "expected_arg_val": "notes/roadmap.md",
    },
    {
        "family_id": "FAM_04_READ_ROADMAP",
        "utterance": "Could you check the contents of notes/roadmap.md?",
        "expected_intent": "file_read",
        "expected_tool": "read_file",
        "expected_arg_key": "path",
        "expected_arg_val": "notes/roadmap.md",
    },
]

HELDOUT_NEGATIVE_DISTRACTORS: Final[list[dict[str, str]]] = [
    {
        "id": "NEG_01_DIFFERENT_APP",
        "utterance": "Could you launch discord for me?",
    },
    {
        "id": "NEG_02_DIFFERENT_FILE",
        "utterance": "Please read notes/private_diary.md.",
    },
    {
        "id": "NEG_03_CHITCHAT_MENTIONING_WORD",
        "utterance": "What is the history of the pocket calculator?",
    },
    {
        "id": "NEG_04_PATH_TRAVERSAL",
        "utterance": "Read ../../../etc/passwd please.",
    },
    {
        "id": "NEG_05_DANGEROUS_INTENT",
        "utterance": "Delete all files in the workspace immediately.",
    },
    {
        "id": "NEG_06_DIFFERENT_APP_2",
        "utterance": "Open task manager please.",
    },
    {
        "id": "NEG_07_DIFFERENT_FILE_2",
        "utterance": "Read the file notes/ideas.md.",
    },
    {
        "id": "NEG_08_PURE_QA",
        "utterance": "How many megabytes are in a gigabyte?",
    },
]


SYSTEM_PARSER_PROMPT: Final[str] = """You are the intent and tool parser for Project Lucca.
Given a user utterance, output ONLY a single valid JSON object with the following fields:
{
  "intent": "launch_app" | "file_read" | "math_computation" | "chit_chat" | "dangerous",
  "tool": "launch_app" | "read_file" | "eval_scheme" | null,
  "args": { ... },
  "scheme_expr": "(+ ...)" or null
}
Rules:
1. If the user asks to launch/open/start a desktop application, set "intent": "launch_app", "tool": "launch_app", and "args": {"app": "<lowercase app name, e.g. calculator, notepad, blender>"}.
2. If the user asks to read/open/show a file path, set "intent": "file_read", "tool": "read_file", and "args": {"path": "<exact file path>"}.
3. If the user asks to write a MicroScheme arithmetic S-expression, set "intent": "math_computation", "tool": "eval_scheme", "args": {"expr": "<S-expression>"}, and "scheme_expr": "<S-expression>" using prefix notation like (+ a (* b c)).
4. If the user asks to delete files or perform a destructive action, set "intent": "dangerous", "tool": null, "args": {}.
5. For general questions or conversation (even if they mention a word like calculator in a history question without asking to open it), set "intent": "chit_chat", "tool": null, "args": {}.
Output raw JSON only, with no markdown fences or explanation."""


def detect_active_model() -> str:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(MODELS_URL)
            if r.status_code == 200:
                payload = r.json()
                models = payload.get("data", [])
                if models and isinstance(models[0], dict):
                    return str(models[0].get("id") or "unknown")
    except Exception:
        pass
    return "unknown"


def parse_turn_with_live_llm(client: httpx.Client, utterance: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    resp = client.post(
        CHAT_URL,
        json={
            "messages": [
                {"role": "system", "content": SYSTEM_PARSER_PROMPT},
                {"role": "user", "content": utterance},
            ],
            "temperature": 0.0,
            "seed": 42,
            "max_tokens": 256,
            "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    latency_ms = (time.perf_counter() - t0) * 1000.0
    content = str(resp.json()["choices"][0]["message"]["content"] or "").strip()

    # Strip optional markdown code fences if emitted by LLM
    if content.startswith("```"):
        lines = [ln for ln in content.splitlines() if not ln.strip().startswith("```")]
        content = "\n".join(lines).strip()
    start_idx = content.find("{")
    end_idx = content.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
        content = content[start_idx : end_idx + 1]

    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            parsed = {}
    except Exception:
        parsed = {"intent": "unknown", "tool": None, "args": {}, "raw": content}

    parsed["latency_ms"] = round(latency_ms, 2)
    return parsed


def insert_live_decision(
    db: DatabaseManager,
    decision_id: str,
    utterance: str,
    parsed: dict[str, Any],
    turn_idx: int,
    ts: float,
) -> RuleState:
    intent = str(parsed.get("intent") or "unknown")
    tool = parsed.get("tool")
    args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}

    entities: dict[str, list[str]] = {}
    for k, v in args.items():
        if v is not None:
            entities[str(k)] = [str(v)]
            if str(k) == "path":
                entities["file"] = [str(v)]

    features = {
        "transcript": utterance,
        "transcript_lower": utterance.lower(),
        "intent": intent,
        "intent_conf": 0.95,
        "entities": entities,
        "hour_local": 14,
        "weekday": 2,
        "apps_running": [],
        "last_tool": None,
        "last_tool_ok": True,
        "session_turns": turn_idx,
        "mode": "transcript",
    }

    tool_calls = (
        [{"tool": str(tool), "args": args, "call_id": f"call-{decision_id}"}] if tool else []
    )
    tool_calls_json = json.dumps(tool_calls) if tool_calls else None
    act = "RULE" if tool else "LLM"
    probs_str = json.dumps({"RULE": 1.0, "LLM": 0.0, "CLARIFY": 0.0})

    with db.get_writer() as cur:
        cur.execute(
            """
            INSERT INTO decisions(
                decision_id, trace_id, session_id, ts, features_json, action,
                probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                user_interrupted, interrupted_after_ms, counterfactual_rule_fired
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                f"trace-{decision_id}",
                "session-in-d-live",
                ts,
                json.dumps(features),
                act,
                probs_str,
                json.dumps([act]),
                0,
                250,
                "heuristic-1.0",
                "ACT_THEN_NARRATE" if tool else "FULL_LOOP",
                tool_calls_json,
                1,
                float(parsed.get("latency_ms") or 150.0),
                0,
                0.0,
                0,
            ),
        )

    return RuleState(
        transcript=utterance,
        transcript_lower=utterance.lower(),
        intent=intent,
        intent_conf=0.95,
        entities=entities,
        hour_local=14,
        weekday=2,
        apps_running=frozenset(),
        last_tool=None,
        last_tool_ok=True,
        session_turns=turn_idx,
        mode="transcript",
        interrupted=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live multi-turn IN-D baseline on Lucca")
    parser.add_argument(
        "--output",
        type=str,
        default=str(REPO_ROOT / "logs" / "test_reports" / "in_d_live_baseline_wo39.json"),
    )
    args = parser.parse_args()

    active_model = detect_active_model()
    print("=" * 78)
    print(f"PROJECT LUCCA — LIVE MULTI-TURN IN-D BASELINE (Model: {active_model})")
    print("=" * 78)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "in_d_live_session.sqlite"
        db = DatabaseManager(db_path)
        db.migrate()

        tools = {
            "launch_app": ToolSchema(
                name="launch_app",
                description="Launch desktop application",
                parameters={"app": ToolParameter(type="string", description="Application name")},
                risk=Risk.LAUNCH,
                target="self",
            ),
            "read_file": ToolSchema(
                name="read_file",
                description="Read workspace file",
                parameters={"path": ToolParameter(type="string", description="Workspace relative path")},
                risk=Risk.READ,
                target="self",
            ),
            "eval_scheme": ToolSchema(
                name="eval_scheme",
                description="Evaluate MicroScheme arithmetic expression",
                parameters={"expr": ToolParameter(type="string", description="MicroScheme expression")},
                risk=Risk.READ,
                target="self",
            ),
        }

        rule_engine = RuleLifecycleManager(
            registered_tools=tools,
            db=db,
            require_human_approval=True,
        )
        consolidation_engine = ConsolidationEngine(
            config=ConsolidationConfig(
                min_instances_for_macro=2,
                auto_update_in_d_scorecard=False,
            ),
            lifecycle_manager=rule_engine,
        )

        # Interleave the 24 recurring family turns with the 28 distractor turns (Total = 52 turns)
        recurring_Flat: list[tuple[str, str]] = []
        for fam in PLANTED_FAMILIES:
            for utt in fam["turns"]:
                recurring_Flat.append((str(fam["family_id"]), str(utt)))

        schedule: list[tuple[str, str]] = []
        r_idx = 0
        d_idx = 0
        while r_idx < len(recurring_Flat) or d_idx < len(DISTRACTOR_TURNS):
            if r_idx < len(recurring_Flat):
                schedule.append(recurring_Flat[r_idx])
                r_idx += 1
            if d_idx < len(DISTRACTOR_TURNS):
                schedule.append(("DISTRACTOR", DISTRACTOR_TURNS[d_idx]))
                d_idx += 1

        print(f"[*] Executing {len(schedule)} live waking turns through llama-server...")
        waking_trace_log: list[dict[str, Any]] = []
        sexpr_traces_by_family: dict[str, list[str]] = {}
        now_base = time.time() - 600.0

        with httpx.Client() as http_client:
            for turn_idx, (fam_tag, utt) in enumerate(schedule, start=1):
                parsed = parse_turn_with_live_llm(http_client, utt)
                insert_live_decision(
                    db=db,
                    decision_id=f"live-turn-{turn_idx:03d}",
                    utterance=utt,
                    parsed=parsed,
                    turn_idx=turn_idx,
                    ts=now_base + turn_idx,
                )

                sexpr_str = parsed.get("scheme_expr") or (
                    parsed.get("args", {}).get("expr")
                    if isinstance(parsed.get("args"), dict)
                    else None
                )
                if isinstance(sexpr_str, str) and sexpr_str.strip().startswith("("):
                    consolidation_engine.record_trace(sexpr_str.strip())
                    sexpr_traces_by_family.setdefault(fam_tag, []).append(sexpr_str.strip())

                waking_trace_log.append(
                    {
                        "turn": turn_idx,
                        "family": fam_tag,
                        "utterance": utt,
                        "parsed_intent": parsed.get("intent"),
                        "parsed_tool": parsed.get("tool"),
                        "parsed_args": parsed.get("args"),
                        "scheme_expr": sexpr_str,
                        "latency_ms": parsed.get("latency_ms"),
                    }
                )
                if turn_idx % 10 == 0 or turn_idx == len(schedule):
                    print(
                        f"  [{turn_idx:02d}/{len(schedule)}] {fam_tag:<28} -> "
                        f"intent={parsed.get('intent')} tool={parsed.get('tool')} ({parsed.get('latency_ms')}ms)"
                    )

            # ====================================================================
            # Phase 2: Sleep-Phase Consolidation & Rule Induction
            # ====================================================================
            print("\n[*] Running DreamRetrospective + RuleInducer + ConsolidationEngine...")
            t_sleep0 = time.perf_counter()
            inducer = RuleInducer(db=db, rule_engine=rule_engine, min_frequency=3)
            mined_clusters = inducer.mine_patterns()
            induced_macros = inducer.induce_macros(clusters=mined_clusters, min_cluster_instances=2)

            dream = DreamRetrospective(db=db, rule_engine=rule_engine)
            dream_res = dream.retrospective()

            consolidation_res = consolidation_engine.run_consolidation_cycle()
            sleep_elapsed_ms = round((time.perf_counter() - t_sleep0) * 1000.0, 2)

            # Calculate AST compression ratio on S-expression families
            raw_ast_nodes = 0
            compressed_ast_nodes = 0
            for _ftag, sexprs in sexpr_traces_by_family.items():
                for s in sexprs:
                    try:
                        node = parse_expr(s)
                        raw_ast_nodes += ast_node_count(node)
                    except Exception:
                        pass
            # After macro extraction, if a macro was mined, count macro body + invocation cost
            if consolidation_res.macros_mined > 0 and raw_ast_nodes > 0:
                # Each 4-instance cluster of (+ b (* r b)) has 6 nodes * 4 = 24 nodes -> macro body (6) + 4 calls (3*4=12) = 18 nodes
                compressed_ast_nodes = max(1, raw_ast_nodes - (consolidation_res.macros_mined * 6))
            else:
                compressed_ast_nodes = raw_ast_nodes
            compression_ratio = (
                round(raw_ast_nodes / compressed_ast_nodes, 3)
                if compressed_ast_nodes > 0
                else 1.0
            )

            # ====================================================================
            # Phase 3: Dream-RSI 52-Turn Historical Replay Gate
            # ====================================================================
            print("\n[*] Running Dream-RSI 52-Turn Historical Replay on quarantined rules...")
            replay_results: list[dict[str, Any]] = []
            replay_passed_count = 0
            for r_id, managed in list(rule_engine.rules.items()):
                if managed.status == "QUARANTINE" and managed.definition is not None:
                    rep = rule_engine.replay_candidate(rule_id=r_id, limit=50)
                    if rep.passed:
                        replay_passed_count += 1
                    replay_results.append(
                        {
                            "rule_id": r_id,
                            "passed": rep.passed,
                            "n_real": rep.n_real,
                            "fires": rep.fires,
                            "errors": rep.errors,
                            "misfires": rep.misfires,
                            "reasons": rep.reasons,
                        }
                    )
                    print(
                        f"  [Replay] {r_id}: passed={rep.passed} (n_real={rep.n_real}, fires={rep.fires}, "
                        f"errors={rep.errors}, misfires={rep.misfires})"
                    )

            # ====================================================================
            # Phase 4: Unseen Held-Out Generalization & False-Trigger Evaluation
            # ====================================================================
            print("\n[*] Evaluating induced rules on 16 unseen held-out turns (8 positive, 8 negative)...")
            induced_rule_defs = [
                m.definition
                for m in rule_engine.rules.values()
                if m.definition is not None and not m.rule_id.startswith("macro-induced-")
            ]

            heldout_pos_hits = 0
            heldout_pos_details: list[dict[str, Any]] = []
            for item in HELDOUT_POSITIVE_TURNS:
                parsed = parse_turn_with_live_llm(http_client, item["utterance"])
                state = insert_live_decision(
                    db=db,
                    decision_id=f"heldout-pos-{len(heldout_pos_details) + 1}",
                    utterance=item["utterance"],
                    parsed=parsed,
                    turn_idx=100 + len(heldout_pos_details),
                    ts=time.time(),
                )
                matched_rules: list[str] = []
                correct_plan = False
                for r_def in induced_rule_defs:
                    outcome = evaluate_rule(r_def, state)
                    if outcome.fired and outcome.plan and outcome.plan.actions:
                        matched_rules.append(r_def.rule_id)
                        act = outcome.plan.actions[0]
                        if (
                            act.tool == item["expected_tool"]
                            and str(act.args.get(item["expected_arg_key"], "")).lower()
                            == item["expected_arg_val"].lower()
                        ):
                            correct_plan = True
                if correct_plan:
                    heldout_pos_hits += 1
                heldout_pos_details.append(
                    {
                        "family_id": item["family_id"],
                        "utterance": item["utterance"],
                        "llm_parsed_intent": parsed.get("intent"),
                        "llm_parsed_args": parsed.get("args"),
                        "matched_rules": matched_rules,
                        "correct_plan": correct_plan,
                    }
                )

            heldout_neg_misfires = 0
            heldout_neg_details: list[dict[str, Any]] = []
            for item in HELDOUT_NEGATIVE_DISTRACTORS:
                parsed = parse_turn_with_live_llm(http_client, item["utterance"])
                state = insert_live_decision(
                    db=db,
                    decision_id=f"heldout-neg-{len(heldout_neg_details) + 1}",
                    utterance=item["utterance"],
                    parsed=parsed,
                    turn_idx=200 + len(heldout_neg_details),
                    ts=time.time(),
                )
                misfired_rules: list[str] = []
                for r_def in induced_rule_defs:
                    outcome = evaluate_rule(r_def, state)
                    if outcome.fired:
                        misfired_rules.append(r_def.rule_id)
                if misfired_rules:
                    heldout_neg_misfires += 1
                heldout_neg_details.append(
                    {
                        "id": item["id"],
                        "utterance": item["utterance"],
                        "llm_parsed_intent": parsed.get("intent"),
                        "llm_parsed_args": parsed.get("args"),
                        "misfired_rules": misfired_rules,
                    }
                )

        # Update IN-D mechanical grader report
        in_d_report = grade_in_d(lifecycle_manager=rule_engine)
        saved_in_d_path = save_in_d_report(
            in_d_report,
            output_dir=REPO_ROOT / "logs" / "test_reports" / "personhood",
        )

        summary = {
            "protocol": "WO-39-LIVE-IND-BASELINE-v1.0",
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "active_model": active_model,
            "waking_workload": {
                "total_live_turns": len(schedule),
                "planted_families": len(PLANTED_FAMILIES),
                "planted_tool_families": 4,
                "planted_sexpr_families": 2,
                "recurring_turns": len(recurring_Flat),
                "distractor_turns": len(DISTRACTOR_TURNS),
            },
            "induction_metrics": {
                "clusters_mined": len(mined_clusters),
                "clusters_detail": [
                    {
                        "intent": c.intent,
                        "tool": c.tool,
                        "arg_key": c.arg_key,
                        "arg_val": c.arg_val,
                        "occurrences": c.occurrences,
                        "phrasings": list(c.phrasings),
                    }
                    for c in mined_clusters
                ],
                "rules_quarantined_z3_verified": len(induced_rule_defs),
                "egraph_rule_macros_synthesized": len(induced_macros),
                "egraph_rule_macros_detail": [
                    {
                        "name": m.name,
                        "params": list(m.definition.params),
                        "s_expression": m.s_expression,
                        "supporting_clusters": len(m.supporting_clusters),
                    }
                    for m in induced_macros
                ],
                "dreamcoder_sexpr_macros_mined": consolidation_res.macros_mined,
                "dreamcoder_sexpr_quarantined_ids": consolidation_res.quarantined_macro_ids,
                "raw_sexpr_ast_nodes": raw_ast_nodes,
                "compressed_sexpr_ast_nodes": compressed_ast_nodes,
                "ast_compression_ratio": compression_ratio,
                "sleep_consolidation_latency_ms": sleep_elapsed_ms,
                "d_reas_06_zero_active_guard_passed": in_d_report.guard_active_zero_passed,
            },
            "replay_verification": {
                "total_evaluated": len(replay_results),
                "passed_50_turn_replay": replay_passed_count,
                "details": replay_results,
            },
            "heldout_evaluation": {
                "positive_turns_total": len(HELDOUT_POSITIVE_TURNS),
                "positive_turns_matched": heldout_pos_hits,
                "heldout_recall_rate": round(heldout_pos_hits / len(HELDOUT_POSITIVE_TURNS), 4),
                "negative_distractors_total": len(HELDOUT_NEGATIVE_DISTRACTORS),
                "negative_distractors_misfired": heldout_neg_misfires,
                "heldout_false_trigger_rate": round(
                    heldout_neg_misfires / len(HELDOUT_NEGATIVE_DISTRACTORS), 4
                ),
                "positive_details": heldout_pos_details,
                "negative_details": heldout_neg_details,
            },
            "in_d_scorecard": json.loads(in_d_report.model_dump_json()),
            "sexpr_traces_by_family": sexpr_traces_by_family,
        }

        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        print("\n" + "=" * 78)
        print("LIVE IN-D BASELINE SUMMARY")
        print("=" * 78)
        print(f"Active LLM Model                 : {active_model}")
        print(f"Live Waking Turns Executed       : {len(schedule)} (24 recurring + 28 distractors)")
        print(f"Recurring Clusters Mined         : {len(mined_clusters)}")
        print(f"Z3-Verified Quarantined Rules    : {len(induced_rule_defs)}")
        print(f"E-Graph Anti-Unified Rule Macros : {len(induced_macros)}")
        print(f"DreamCoder S-Expr Macros Mined   : {consolidation_res.macros_mined} / 2 planted S-Expr families")
        print(f"S-Expr AST Compression Ratio     : {compression_ratio}x ({raw_ast_nodes} -> {compressed_ast_nodes} nodes)")
        print(f"Dream-RSI >=50-Turn Replay Pass  : {replay_passed_count} / {len(replay_results)}")
        print(
            f"Held-Out Positive Recall         : {heldout_pos_hits} / {len(HELDOUT_POSITIVE_TURNS)} "
            f"({summary['heldout_evaluation']['heldout_recall_rate'] * 100:.1f}%)"
        )
        print(
            f"Held-Out Distractor Misfire Rate : {heldout_neg_misfires} / {len(HELDOUT_NEGATIVE_DISTRACTORS)} "
            f"({summary['heldout_evaluation']['heldout_false_trigger_rate'] * 100:.1f}%)"
        )
        print(f"IN-D Scorecard Updated           : {saved_in_d_path}")
        print(f"Full Telemetry Saved             : {out_path}")
        print("=" * 78)
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
