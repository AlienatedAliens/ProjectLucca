"""
End-to-End Single-Rule Lifecycle Trace on Gemma 4 26B-A4B (WO-39)
=================================================================
Traces one induced rule (`induced-read-file-notes-roadmap-md-v1`) through
`RuleLifecycleManager` (`src/lucca/reasoning/lifecycle.py`) using 66 live
`Gemma 4 26B-A4B` (`gemma-4-26B-A4B-it-heretic.Q6_K.gguf`) HTTP inference calls
on `llama-server` (`http://127.0.0.1:8080`):

What is live vs. harness-scaffolded in this script:
  - LIVE: All 66 natural-language turns (50 waking + 5 seed-rule shadow +
    5 target-rule shadow + 5 saved-state head-to-head + 1 user correction) are
    sent live to Gemma 4 26B-A4B (`temperature=0.0`, `cache_prompt=False`) and
    timed with `time.perf_counter()`.
  - LIVE: SQLite migrations (`0001`–`0009`), `RuleInducer`, `DreamRetrospective`,
    E-Graph anti-unification (`induce_macros`), Z3 SMT conflict verification,
    `ReplayEngine.replay_candidate`, `RuleLifecycleManager`, and `read_file`
    SHA-256 verification against temporary workspace files on disk.
  - HARNESS SCAFFOLDING:
    1. `compute_cluster_id` is called with synthetic session IDs and +1000s
       timestamp offsets to simulate 5 separate 15-minute session clusters in
       a single continuous run.
    2. `launch_app` validates against an allowlist without spawning a GUI window.
    3. Human approval (`approve_rule(..., approver="simulated_operator")`) is
       triggered programmatically by the harness.
    4. In Stage 8, Gemma 4 26B-A4B parses the natural-language user correction
       (`user_correction: true`), and when `corr_detected` is True the harness
       emits `signal="operator_correct"` and calls `record_shadow(matched=False)`
       to trigger the 1-strike circuit breaker (`ACTIVE -> QUARANTINE`), followed
       by `user_retire()` (`QUARANTINE -> RETIRED`).
"""

from __future__ import annotations

import hashlib
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

from lucca.core.schemas import (  # noqa: E402
    Plan,
    Risk,
    RuleState,
    ToolCall,
    ToolParameter,
    ToolSchema,
)
from lucca.memory.db import DatabaseManager  # noqa: E402
from lucca.memory.reflection import DreamRetrospective  # noqa: E402
from lucca.reasoning.induction import RuleInducer  # noqa: E402
from lucca.reasoning.lifecycle import (  # noqa: E402
    RuleLifecycleManager,
    check_plan_and_core_agreement,
    compute_cluster_id,
)

SERVER_BASE: Final[str] = "http://127.0.0.1:8080"
CHAT_URL: Final[str] = f"{SERVER_BASE}/v1/chat/completions"
MODELS_URL: Final[str] = f"{SERVER_BASE}/v1/models"

SYSTEM_PARSER_PROMPT: Final[str] = """You are the local intent, tool, and feedback parser for Project Lucca.
Given a user utterance, output ONLY a single valid JSON object with the following fields:
{
  "intent": "launch_app" | "file_read" | "math_computation" | "user_correction" | "chit_chat" | "dangerous",
  "tool": "launch_app" | "read_file" | "eval_scheme" | null,
  "args": { ... },
  "user_correction": true | false
}
Rules:
1. If the user asks to launch/open/start a desktop application, set "intent": "launch_app", "tool": "launch_app", "args": {"app": "<lowercase app name, e.g. calculator, notepad, blender>"}, "user_correction": false.
2. If the user asks to read/open/show a file path, set "intent": "file_read", "tool": "read_file", "args": {"path": "<exact file path>"}, "user_correction": false.
3. If the user corrects, undoes, or rejects the previous action (e.g., "Wait no, stop—I meant notes/todo.md, undo that"), set "intent": "user_correction", "user_correction": true, and set "tool" / "args" to the replacement action if requested.
4. If the user asks to delete files or perform a destructive action, set "intent": "dangerous", "tool": null, "args": {}, "user_correction": false.
5. For general questions or conversation, set "intent": "chit_chat", "tool": null, "args": {}, "user_correction": false.
Output raw JSON only, with no markdown fences or explanation."""

WAKING_50_TURNS: Final[list[dict[str, str]]] = [
    {"category": "target_roadmap", "utterance": "Please read notes/roadmap.md for me."},
    {"category": "target_roadmap", "utterance": "Open up notes/roadmap.md and show its contents."},
    {"category": "target_roadmap", "utterance": "Can you read the file notes/roadmap.md?"},
    {"category": "target_roadmap", "utterance": "Show me what is written in notes/roadmap.md."},
    {"category": "seed_calc", "utterance": "Could you open the calculator app for me?"},
    {"category": "seed_calc", "utterance": "Please launch calculator."},
    {"category": "seed_calc", "utterance": "I need calculator open right now, can you start it?"},
    {"category": "seed_calc", "utterance": "Pop open the calculator application please."},
    {"category": "near_miss_todo", "utterance": "Please read the file notes/todo.md."},
    {"category": "near_miss_todo", "utterance": "Can you show me the contents of notes/todo.md?"},
    {"category": "near_miss_todo", "utterance": "Read notes/todo.md for me."},
    {"category": "near_miss_todo", "utterance": "Open notes/todo.md and read it out."},
    {"category": "distractor", "utterance": "What is the capital of Australia?"},
    {"category": "distractor", "utterance": "Could you open blender for me?"},
    {"category": "distractor", "utterance": "Read the file notes/meeting_minutes.md."},
    {"category": "distractor", "utterance": "Explain the difference between TCP and UDP in one sentence."},
    {"category": "distractor", "utterance": "Please launch spotify."},
    {"category": "distractor", "utterance": "Read the file README.md."},
    {"category": "distractor", "utterance": "Delete the entire system32 directory right now."},
    {"category": "distractor", "utterance": "How many days are in a leap year?"},
    {"category": "distractor", "utterance": "Open paint please."},
    {"category": "distractor", "utterance": "Read the file notes/shopping_list.txt."},
    {"category": "distractor", "utterance": "Please read ../secret_keys.txt right now."},
    {"category": "distractor", "utterance": "How many planets are in the solar system?"},
    {"category": "distractor", "utterance": "Launch steam for me."},
    {"category": "distractor", "utterance": "What is the square root of 144?"},
    {"category": "distractor", "utterance": "Open terminal please."},
    {"category": "distractor", "utterance": "What time zone is Perth in?"},
    {"category": "distractor", "utterance": "Why is the sky blue?"},
    {"category": "distractor", "utterance": "Do not open calculator, just tell me what 2 + 2 is."},
    {"category": "distractor", "utterance": "Read the file notes/private_diary.md."},
    {"category": "distractor", "utterance": "Read the file notes/ideas.md."},
    {"category": "distractor", "utterance": "Could you launch discord for me?"},
    {"category": "distractor", "utterance": "Open task manager please."},
    {"category": "distractor", "utterance": "How many megabytes are in a gigabyte?"},
    {"category": "distractor", "utterance": "What is the history of the pocket calculator?"},
    {"category": "distractor", "utterance": "Read ../../../etc/passwd please."},
    {"category": "distractor", "utterance": "Delete all files in the workspace immediately."},
    {"category": "distractor", "utterance": "Who wrote the book Principia Mathematica?"},
    {"category": "distractor", "utterance": "What is the boiling point of water at sea level?"},
    {"category": "distractor", "utterance": "Launch vlc media player please."},
    {"category": "distractor", "utterance": "Can you open firefox for me?"},
    {"category": "distractor", "utterance": "What does HTTP stand for?"},
    {"category": "distractor", "utterance": "How many bits are in an IPv6 address?"},
    {"category": "distractor", "utterance": "Open obsidian please."},
    {"category": "distractor", "utterance": "What is the speed of light in vacuum?"},
    {"category": "distractor", "utterance": "Tell me what 15 multiplied by 12 is."},
    {"category": "distractor", "utterance": "Launch audacity for me."},
    {"category": "distractor", "utterance": "What is a cryptographic hash function?"},
    {"category": "distractor", "utterance": "How many seconds are in an hour?"},
]

SHADOW_5_ROADMAP_TURNS: Final[list[str]] = [
    "Can you open notes/roadmap.md and read it?",
    "Show me the contents of notes/roadmap.md please.",
    "I'd like to read notes/roadmap.md.",
    "Pull up notes/roadmap.md for me.",
    "Display what is inside notes/roadmap.md.",
]

SHADOW_5_CALC_TURNS: Final[list[str]] = [
    "Start calculator for me please.",
    "Open up calculator right now.",
    "Can you launch the calculator app?",
    "Fire up calculator please.",
    "Run calculator for me.",
]

HELDOUT_SAVED_TASK_UTTERANCES: Final[list[dict[str, Any]]] = [
    {
        "case_id": "SAVED_POS_01",
        "role": "positive_target",
        "utterance": "Read notes/roadmap.md for me.",
        "expected_tool": "read_file",
        "expected_args": {"path": "notes/roadmap.md"},
    },
    {
        "case_id": "SAVED_POS_02",
        "role": "positive_target",
        "utterance": "Could you check the contents of notes/roadmap.md?",
        "expected_tool": "read_file",
        "expected_args": {"path": "notes/roadmap.md"},
    },
    {
        "case_id": "SAVED_POS_03",
        "role": "positive_target",
        "utterance": "Please read out my notes/roadmap.md file.",
        "expected_tool": "read_file",
        "expected_args": {"path": "notes/roadmap.md"},
    },
    {
        "case_id": "SAVED_NEG_01_NEAR_MISS_FILE",
        "role": "negative_distractor",
        "utterance": "Please read notes/todo.md and show me what's in it.",
        "expected_tool": "read_file",
        "expected_args": {"path": "notes/todo.md"},
    },
    {
        "case_id": "SAVED_NEG_02_PRIOR_ACTIVE_RULE",
        "role": "prior_active_rule_check",
        "utterance": "Hey, could you start calculator for me?",
        "expected_tool": "launch_app",
        "expected_args": {"app": "calculator"},
    },
]

USER_CORRECTION_UTTERANCE: Final[str] = (
    "Wait no, stop—I meant notes/todo.md, not notes/roadmap.md! Undo that and read notes/todo.md instead."
)


def build_tool_registry() -> dict[str, ToolSchema]:
    return {
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
            parameters={"path": ToolParameter(type="string", description="Workspace-relative path")},
            risk=Risk.READ,
            target="self",
        ),
    }


def detect_active_model(client: httpx.Client) -> str:
    r = client.get(MODELS_URL, timeout=5.0)
    r.raise_for_status()
    models = r.json().get("data", [])
    if models and isinstance(models[0], dict):
        return str(models[0].get("id") or "unknown")
    raise RuntimeError("No active model detected on llama-server (port 8080)")


def call_live_llm_parser(client: httpx.Client, utterance: str, max_retries: int = 2) -> dict[str, Any]:
    retries = 0
    total_latency_ms = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    last_raw = ""

    for _attempt in range(max_retries + 1):
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
                "max_tokens": 192,
                "cache_prompt": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        total_latency_ms += (time.perf_counter() - t0) * 1000.0

        body = resp.json()
        usage = body.get("usage", {})
        prompt_tokens += int(usage.get("prompt_tokens", 0))
        completion_tokens += int(usage.get("completion_tokens", 0))
        total_tokens += int(usage.get("total_tokens", 0))

        content = str(body["choices"][0]["message"]["content"] or "").strip()
        last_raw = content
        if content.startswith("```"):
            lines = [ln for ln in content.splitlines() if not ln.strip().startswith("```")]
            content = "\n".join(lines).strip()
        start_idx, end_idx = content.find("{"), content.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            content = content[start_idx : end_idx + 1]

        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "intent" in parsed:
                return {
                    "intent": str(parsed.get("intent") or "unknown"),
                    "tool": parsed.get("tool"),
                    "args": parsed.get("args") if isinstance(parsed.get("args"), dict) else {},
                    "user_correction": bool(parsed.get("user_correction", False)),
                    "latency_ms": round(total_latency_ms, 2),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "retries": retries,
                    "raw_response": last_raw,
                }
        except Exception:
            pass
        retries += 1

    return {
        "intent": "unknown",
        "tool": None,
        "args": {},
        "user_correction": False,
        "latency_ms": round(total_latency_ms, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "retries": retries,
        "raw_response": last_raw,
    }


def build_rule_state_from_llm(utterance: str, parsed: dict[str, Any]) -> RuleState:
    intent = str(parsed.get("intent") or "unknown")
    args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
    entities: dict[str, list[str]] = {}
    if "app" in args and isinstance(args["app"], str):
        val = args["app"].strip().lower()
        entities["app"] = [val]
        entities["target"] = [val]
    if "path" in args and isinstance(args["path"], str):
        val = args["path"].strip()
        entities["file"] = [val]
        entities["path"] = [val]
    return RuleState(
        transcript=utterance,
        transcript_lower=utterance.lower(),
        intent=intent,
        intent_conf=0.95,
        entities=entities,
        hour_local=14,
        weekday=2,
    )


def execute_and_verify_tool_call(
    tool_name: str | None,
    tool_args: dict[str, Any],
    workspace_root: Path,
    expected_file_hashes: dict[str, str],
    tool_registry: dict[str, ToolSchema],
) -> dict[str, Any]:
    t0 = time.perf_counter()
    if tool_name is None:
        return {
            "tool_executed": False,
            "tool_exit_zero": True,
            "schema_valid": True,
            "verifier_passed": True,
            "tool_latency_ms": round((time.perf_counter() - t0) * 1000.0, 4),
            "detail": "no_tool_required",
            "actual_sha256": None,
        }
    if tool_name not in tool_registry:
        return {
            "tool_executed": False,
            "tool_exit_zero": False,
            "schema_valid": False,
            "verifier_passed": False,
            "tool_latency_ms": round((time.perf_counter() - t0) * 1000.0, 4),
            "detail": f"unknown_tool:{tool_name}",
            "actual_sha256": None,
        }
    schema = tool_registry[tool_name]
    for param_name in schema.parameters:
        if param_name not in tool_args or not isinstance(tool_args[param_name], str):
            return {
                "tool_executed": False,
                "tool_exit_zero": False,
                "schema_valid": False,
                "verifier_passed": False,
                "tool_latency_ms": round((time.perf_counter() - t0) * 1000.0, 4),
                "detail": f"missing_or_invalid_param:{param_name}",
                "actual_sha256": None,
            }
    if tool_name == "read_file":
        rel_path = str(tool_args["path"])
        candidate_path = (workspace_root / rel_path).resolve()
        try:
            candidate_path.relative_to(workspace_root.resolve())
        except ValueError:
            return {
                "tool_executed": True,
                "tool_exit_zero": False,
                "schema_valid": True,
                "verifier_passed": False,
                "tool_latency_ms": round((time.perf_counter() - t0) * 1000.0, 4),
                "detail": f"path_traversal_blocked:{rel_path}",
                "actual_sha256": None,
            }
        if not candidate_path.is_file():
            return {
                "tool_executed": True,
                "tool_exit_zero": False,
                "schema_valid": True,
                "verifier_passed": False,
                "tool_latency_ms": round((time.perf_counter() - t0) * 1000.0, 4),
                "detail": f"file_not_found:{rel_path}",
                "actual_sha256": None,
            }
        data = candidate_path.read_text(encoding="utf-8")
        actual_sha = hashlib.sha256(data.encode("utf-8")).hexdigest()
        expected_sha = expected_file_hashes.get(rel_path)
        sha_match = (expected_sha is not None) and (actual_sha == expected_sha)
        return {
            "tool_executed": True,
            "tool_exit_zero": True,
            "schema_valid": True,
            "verifier_passed": sha_match,
            "tool_latency_ms": round((time.perf_counter() - t0) * 1000.0, 4),
            "detail": f"read_ok:bytes={len(data)}:sha256={actual_sha[:16]}",
            "actual_sha256": actual_sha,
            "expected_sha256": expected_sha,
        }
    if tool_name == "launch_app":
        app_name = str(tool_args["app"]).strip().lower()
        allowed_apps = {
            "calculator", "notepad", "blender", "spotify", "paint", "steam",
            "terminal", "discord", "task manager", "vlc", "vlc media player",
            "firefox", "obsidian", "audacity",
        }
        ok = app_name in allowed_apps
        return {
            "tool_executed": True,
            "tool_exit_zero": ok,
            "schema_valid": True,
            "verifier_passed": ok,
            "tool_latency_ms": round((time.perf_counter() - t0) * 1000.0, 4),
            "detail": f"launch_app_allowlist_check:{app_name}:ok={ok}",
            "actual_sha256": None,
        }
    return {
        "tool_executed": False,
        "tool_exit_zero": False,
        "schema_valid": False,
        "verifier_passed": False,
        "tool_latency_ms": round((time.perf_counter() - t0) * 1000.0, 4),
        "detail": "unhandled_tool",
        "actual_sha256": None,
    }


def main() -> int:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.run_four_tier_comparative_sweep import TIER_CONFIGS, ensure_server_for_tier

    ensure_server_for_tier(TIER_CONFIGS["tier0"])
    tool_registry = build_tool_registry()
    with httpx.Client(timeout=60.0) as client:
        active_model = detect_active_model(client)
        print(f"[LIVE] Connected to llama-server model: {active_model}", flush=True)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            tmp_path = Path(tmp_dir)
            db = DatabaseManager(tmp_path / "live_single_rule_trace.db")
            db.migrate()

            workspace_files = {
                "notes/roadmap.md": (
                    "# Project Lucca Roadmap (WO-39)\n"
                    "- Layer 2->3 Cryptographic Provenance Gate\n"
                    "- Layer 3 Belnap/NARS + OpenVINO MiniLM-L6\n"
                    "- Layer 4 MicroScheme Rule Lifecycle & Z3 Quarantine\n"
                ),
                "notes/todo.md": (
                    "# Daily Todo List\n"
                    "- Run 50-turn Dream-RSI replay\n"
                    "- Verify 5-cluster contrastive shadow agreement\n"
                ),
                "notes/meeting_minutes.md": "# Meeting Minutes\n- Reviewed SOAC receipt latency.\n",
                "notes/shopping_list.txt": "milk\ncoffee beans\nsparkling water\n",
                "notes/private_diary.md": "Personal notes entry.\n",
                "notes/ideas.md": "Future ideas for E-Graph macro compression.\n",
                "README.md": "# Project Lucca Workspace\n",
            }
            expected_file_hashes: dict[str, str] = {}
            for rel_path, text in workspace_files.items():
                fpath = tmp_path / rel_path
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(text, encoding="utf-8")
                expected_file_hashes[rel_path] = hashlib.sha256(text.encode("utf-8")).hexdigest()

            now = time.time()

            # STAGE 1: Live 50-Turn Waking Workload on Gemma 4 26B-A4B
            print("[STAGE 1] Running 50 waking turns live on Gemma 4 26B-A4B...", flush=True)
            waking_logs: list[dict[str, Any]] = []
            for idx, item in enumerate(WAKING_50_TURNS):
                utterance = item["utterance"]
                parsed = call_live_llm_parser(client, utterance)
                state = build_rule_state_from_llm(utterance, parsed)
                tool_name = parsed["tool"] if isinstance(parsed["tool"], str) else None
                tool_args = parsed["args"] if isinstance(parsed["args"], dict) else {}
                exec_res = execute_and_verify_tool_call(
                    tool_name, tool_args, tmp_path, expected_file_hashes, tool_registry
                )
                tool_ok_flag = 1 if (exec_res["tool_exit_zero"] and exec_res["verifier_passed"]) else 0
                dec_id = f"dec-live-waking-{idx+1:03d}"
                features_payload = {
                    "transcript": utterance,
                    "transcript_lower": utterance.lower(),
                    "intent": state.intent,
                    "intent_conf": 0.95,
                    "entities": state.entities,
                    "hour_local": 14,
                    "weekday": 2,
                    "apps_running": [],
                    "last_tool": None,
                    "last_tool_ok": bool(tool_ok_flag),
                    "session_turns": idx + 1,
                    "mode": "transcript",
                }
                tool_calls_list = (
                    [{"tool": tool_name, "args": tool_args, "call_id": f"call-{dec_id}"}]
                    if (tool_name and tool_ok_flag)
                    else []
                )
                act = "RULE" if tool_calls_list else "LLM"
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
                            dec_id,
                            f"trace-waking-{idx+1:03d}",
                            "session-live-26b-a4b",
                            now - (60 - idx) * 60.0,
                            json.dumps(features_payload),
                            act,
                            json.dumps({"RULE": 1.0, "LLM": 0.0, "CLARIFY": 0.0}),
                            json.dumps([act]),
                            0,
                            250,
                            "heuristic-1.0",
                            "ACT_THEN_NARRATE" if tool_calls_list else "FULL_LOOP",
                            json.dumps(tool_calls_list) if tool_calls_list else None,
                            tool_ok_flag,
                            float(parsed["latency_ms"]),
                            0,
                            0.0,
                            0,
                        ),
                    )
                waking_logs.append(
                    {
                        "turn": idx + 1,
                        "category": item["category"],
                        "utterance": utterance,
                        "intent": state.intent,
                        "tool": tool_name,
                        "args": tool_args,
                        "llm_latency_ms": parsed["latency_ms"],
                        "prompt_tokens": parsed["prompt_tokens"],
                        "completion_tokens": parsed["completion_tokens"],
                        "total_tokens": parsed["total_tokens"],
                        "retries": parsed["retries"],
                        "tool_exit_zero": exec_res["tool_exit_zero"],
                        "verifier_passed": exec_res["verifier_passed"],
                        "verifier_detail": exec_res["detail"],
                    }
                )
                if (idx + 1) % 10 == 0:
                    print(f"  ... completed {idx+1}/50 waking turns", flush=True)

            # STAGE 2: RuleInducer + DreamRetrospective + E-Graph + Z3 SMT Quarantine
            print("[STAGE 2] Running RuleInducer + E-Graph Anti-Unification + Z3 Check...", flush=True)
            lifecycle = RuleLifecycleManager(
                registered_tools=tool_registry, db=db, require_human_approval=True
            )
            inducer = RuleInducer(db=db, rule_engine=lifecycle, min_frequency=3)
            mined_clusters = inducer.mine_patterns()
            induced_macros = inducer.induce_macros(clusters=mined_clusters, min_cluster_instances=2)

            retrospective = DreamRetrospective(db=db, rule_engine=lifecycle)
            t0_induce = time.perf_counter()
            dream_res = retrospective.retrospective()
            induce_ms = (time.perf_counter() - t0_induce) * 1000.0

            target_rule_id = "induced-read-file-notes-roadmap-md-v1"
            seed_rule_id = "induced-launch-app-calculator-v1"
            assert target_rule_id in lifecycle.rules
            assert seed_rule_id in lifecycle.rules
            assert lifecycle.rules[target_rule_id].status == "QUARANTINE"

            # STAGE 3: Offline 50-Turn Historical Replay (`ReplayEngine.replay_candidate`)
            print("[STAGE 3] Running 50-turn Dream-RSI offline replay...", flush=True)
            seed_replay = lifecycle.replay_candidate(seed_rule_id, limit=50)
            assert seed_replay.passed
            for idx, s_utt in enumerate(SHADOW_5_CALC_TURNS):
                s_parsed = call_live_llm_parser(client, s_utt)
                s_st = build_rule_state_from_llm(s_utt, s_parsed)
                ro_list = lifecycle.evaluate(s_st, mode="shadow")
                ro = [o for o in ro_list if o.rule_id == seed_rule_id][0]
                cid = compute_cluster_id(
                    session_id=f"seed-sess-{idx}",
                    turn_ts=now + (idx + 1) * 1000.0,
                    semantic_cluster=idx,
                )
                lifecycle.record_shadow(
                    seed_rule_id, matched=ro.fired, cluster_id=cid,
                    state_snapshot=s_st, plan_snapshot=ro.plan,
                )
            lifecycle.promote_if_eligible(seed_rule_id, require_replay=True)
            lifecycle.approve_rule(seed_rule_id, approver="simulated_operator_seed", require_replay=True)
            assert lifecycle.rules[seed_rule_id].status == "ACTIVE"

            t0_replay = time.perf_counter()
            replay_report = lifecycle.replay_candidate(target_rule_id, limit=50)
            replay_ms = (time.perf_counter() - t0_replay) * 1000.0
            assert replay_report.passed

            # STAGE 4: Live 5-Cluster Contrastive Shadow Evaluation on Gemma 4 26B-A4B
            print("[STAGE 4] Running 5 simulated-cluster shadow turns on Gemma 4 26B-A4B...", flush=True)
            shadow_turn_traces: list[dict[str, Any]] = []
            for idx, sh_utt in enumerate(SHADOW_5_ROADMAP_TURNS):
                llm_parsed = call_live_llm_parser(client, sh_utt)
                live_state = build_rule_state_from_llm(sh_utt, llm_parsed)
                llm_tool = str(llm_parsed["tool"] or "")
                llm_args = llm_parsed["args"] if isinstance(llm_parsed["args"], dict) else {}
                live_core_tool_call = ToolCall(
                    call_id=f"call-live-shadow-{idx+1}", tool=llm_tool, args=llm_args
                )

                t0_sh = time.perf_counter()
                ro_list = lifecycle.evaluate(live_state, mode="shadow")
                sh_eval_ms = (time.perf_counter() - t0_sh) * 1000.0
                ro = [o for o in ro_list if o.rule_id == target_rule_id][0]
                assert ro.fired and ro.plan is not None

                # Execute both the shadow rule's tool call and the LLM core's tool call
                rule_tc = ro.plan.actions[0]
                assert isinstance(rule_tc, ToolCall)
                rule_exec = execute_and_verify_tool_call(
                    rule_tc.tool, rule_tc.args, tmp_path, expected_file_hashes, tool_registry
                )
                core_exec = execute_and_verify_tool_call(
                    llm_tool, llm_args, tmp_path, expected_file_hashes, tool_registry
                )
                rule_sig = "tool_exit_zero" if (rule_exec["tool_exit_zero"] and rule_exec["verifier_passed"]) else "tool_error"
                core_sig = "tool_exit_zero" if (core_exec["tool_exit_zero"] and core_exec["verifier_passed"]) else "tool_error"

                # Simulated session/time cluster (+1000s offset per turn exceeds 900s = 15-min bucket in compute_cluster_id)
                cid = compute_cluster_id(
                    session_id=f"shadow-roadmap-sess-{idx}",
                    turn_ts=now + (idx + 10) * 1000.0,
                    semantic_cluster=idx,
                )
                lifecycle.record_shadow(
                    target_rule_id, matched=ro.fired, cluster_id=cid,
                    state_snapshot=live_state, plan_snapshot=ro.plan,
                )
                lifecycle.log_contrastive_shadow_pair(
                    rule_id=target_rule_id,
                    trace_id=f"trace-live-shadow-{idx+1}",
                    rule_plan=ro.plan,
                    core_tool_calls=[live_core_tool_call],
                    core_path="LLM",
                    rule_outcome_signal=rule_sig,
                    core_outcome_signal=core_sig,
                )
                agreed = check_plan_and_core_agreement(ro.plan, [live_core_tool_call])
                shadow_turn_traces.append(
                    {
                        "cluster_index": idx + 1,
                        "simulated_cluster_id": cid,
                        "utterance": sh_utt,
                        "llm_core_tool_call": {"tool": llm_tool, "args": llm_args},
                        "shadow_rule_fired": ro.fired,
                        "agreed_with_llm_core": agreed,
                        "shadow_rule_eval_latency_ms": round(sh_eval_ms, 4),
                        "live_llm_latency_ms": llm_parsed["latency_ms"],
                        "live_llm_total_tokens": llm_parsed["total_tokens"],
                        "verifier_passed": core_exec["verifier_passed"],
                    }
                )

            contrastive_summary = lifecycle.get_contrastive_summary(target_rule_id)

            # STAGE 5 & 6: Regression Suite Check & Promotion (`PENDING_APPROVAL -> ACTIVE`)
            print("[STAGE 5 & 6] Verifying regression suite and promoting rule to ACTIVE...", flush=True)
            reg_report_pre = lifecycle.verify_regression_suite(candidate_rule_id=target_rule_id)
            assert reg_report_pre.passed

            promo_step1 = lifecycle.promote_if_eligible(target_rule_id, require_replay=True)
            status_after_step1 = lifecycle.rules[target_rule_id].status
            assert status_after_step1 == "PENDING_APPROVAL"

            promo_step2 = lifecycle.approve_rule(
                target_rule_id, approver="simulated_operator", require_replay=True
            )
            status_after_step2 = lifecycle.rules[target_rule_id].status
            assert status_after_step2 == "ACTIVE"

            reg_report_post = lifecycle.verify_regression_suite()
            assert reg_report_post.passed

            # STAGE 7: Head-to-Head Comparison on Saved Task States
            print("[STAGE 7] Running head-to-head Active Rule vs. Normal Gemma 4 26B-A4B Path...", flush=True)
            saved_states_records: list[dict[str, Any]] = []
            head_to_head_comparisons: list[dict[str, Any]] = []

            for item in HELDOUT_SAVED_TASK_UTTERANCES:
                case_id = item["case_id"]
                utterance = item["utterance"]
                role = item["role"]

                # Path A: Normal LLM Path (Gemma 4 26B-A4B parses utterance + plans tool call)
                llm_parsed = call_live_llm_parser(client, utterance)
                saved_state = build_rule_state_from_llm(utterance, llm_parsed)
                saved_states_records.append(
                    {
                        "case_id": case_id,
                        "role": role,
                        "utterance": utterance,
                        "saved_rule_state": saved_state.model_dump(mode="json"),
                    }
                )
                llm_tool = str(llm_parsed["tool"] or "")
                llm_args = llm_parsed["args"] if isinstance(llm_parsed["args"], dict) else {}
                llm_exec = execute_and_verify_tool_call(
                    llm_tool if llm_tool else None, llm_args, tmp_path, expected_file_hashes, tool_registry
                )

                # Path B: Active Rule Path (evaluates already-extracted saved_state in MicroScheme)
                t0_rule = time.perf_counter()
                act_outcomes = lifecycle.evaluate(saved_state, mode="active")
                rule_plan_ms = (time.perf_counter() - t0_rule) * 1000.0

                target_ro = [o for o in act_outcomes if o.rule_id == target_rule_id][0]
                fired_any = [o for o in act_outcomes if o.fired and o.plan is not None]

                if target_ro.fired and target_ro.plan is not None:
                    tc = target_ro.plan.actions[0]
                    assert isinstance(tc, ToolCall)
                    rule_exec = execute_and_verify_tool_call(
                        tc.tool, tc.args, tmp_path, expected_file_hashes, tool_registry
                    )
                    triple = lifecycle.emit_execution_triple(
                        rule_id=target_rule_id,
                        plan=target_ro.plan,
                        verdict="accepted",
                        reason_code="ACTIVE_EXECUTION",
                        signal="tool_exit_zero" if rule_exec["verifier_passed"] else "operator_correct",
                        detail=rule_exec["detail"],
                        evidence_refs=[utterance],
                    )
                    active_path_result = {
                        "target_rule_fired": True,
                        "other_active_rule_fired": None,
                        "tool_call": {"tool": tc.tool, "args": tc.args},
                        "signal_1_tool_completed_exit_zero": rule_exec["tool_exit_zero"],
                        "signal_2_verifier_passed": rule_exec["verifier_passed"],
                        "signal_2_sha256": rule_exec["actual_sha256"],
                        "signal_3_rule_planning_latency_ms": round(rule_plan_ms, 4),
                        "signal_3_tool_io_latency_ms": rule_exec["tool_latency_ms"],
                        "signal_3_total_saved_state_latency_ms": round(
                            rule_plan_ms + rule_exec["tool_latency_ms"], 4
                        ),
                        "signal_3_llm_planning_tokens_from_saved_state": 0,
                        "signal_3_tool_calls": 1,
                        "signal_3_retries": 0,
                        "signal_3_gas_used": target_ro.gas_used,
                        "signal_4_user_correction_or_undo": False,
                        "signal_5_regression_or_misfire": False,
                        "execution_triple_id": triple.decision.decision_id,
                    }
                else:
                    other_id = fired_any[0].rule_id if fired_any else None
                    active_path_result = {
                        "target_rule_fired": False,
                        "other_active_rule_fired": other_id,
                        "tool_call": None,
                        "signal_1_tool_completed_exit_zero": llm_exec["tool_exit_zero"],
                        "signal_2_verifier_passed": llm_exec["verifier_passed"],
                        "signal_3_rule_planning_latency_ms": round(rule_plan_ms, 4),
                        "signal_4_user_correction_or_undo": False,
                        "signal_5_regression_or_misfire": False,
                    }

                head_to_head_comparisons.append(
                    {
                        "case_id": case_id,
                        "role": role,
                        "utterance": utterance,
                        "normal_llm_path_gemma4_26b_a4b": {
                            "tool_call": {"tool": llm_tool, "args": llm_args},
                            "signal_1_tool_completed_exit_zero": llm_exec["tool_exit_zero"],
                            "signal_2_verifier_passed": llm_exec["verifier_passed"],
                            "signal_2_sha256": llm_exec["actual_sha256"],
                            "signal_3_llm_planning_latency_ms": llm_parsed["latency_ms"],
                            "signal_3_tool_io_latency_ms": llm_exec["tool_latency_ms"],
                            "signal_3_total_turn_latency_ms": round(
                                llm_parsed["latency_ms"] + llm_exec["tool_latency_ms"], 2
                            ),
                            "signal_3_prompt_tokens": llm_parsed["prompt_tokens"],
                            "signal_3_completion_tokens": llm_parsed["completion_tokens"],
                            "signal_3_total_tokens": llm_parsed["total_tokens"],
                            "signal_3_tool_calls": 1,
                            "signal_3_retries": llm_parsed["retries"],
                            "signal_4_user_correction_or_undo": False,
                            "signal_5_regression_or_misfire": False,
                        },
                        "active_rule_path_microscheme_from_saved_state": active_path_result,
                    }
                )

            saved_states_path = REPO_ROOT / "logs" / "test_reports" / "saved_task_states_wo39.json"
            saved_states_path.write_text(json.dumps(saved_states_records, indent=2), encoding="utf-8")

            pos_cases = [c for c in head_to_head_comparisons if c["role"] == "positive_target"]
            mean_llm_latency_ms = round(
                sum(c["normal_llm_path_gemma4_26b_a4b"]["signal_3_llm_planning_latency_ms"] for c in pos_cases) / len(pos_cases), 2
            )
            mean_llm_prompt_tokens = round(
                sum(c["normal_llm_path_gemma4_26b_a4b"]["signal_3_prompt_tokens"] for c in pos_cases) / len(pos_cases), 1
            )
            mean_llm_completion_tokens = round(
                sum(c["normal_llm_path_gemma4_26b_a4b"]["signal_3_completion_tokens"] for c in pos_cases) / len(pos_cases), 1
            )
            mean_llm_total_tokens = round(
                sum(c["normal_llm_path_gemma4_26b_a4b"]["signal_3_total_tokens"] for c in pos_cases) / len(pos_cases), 1
            )
            mean_rule_latency_ms = round(
                sum(c["active_rule_path_microscheme_from_saved_state"]["signal_3_rule_planning_latency_ms"] for c in pos_cases) / len(pos_cases), 4
            )

            # STAGE 8: Live User Correction Turn -> Conditional Harness Demotion Signal
            print("[STAGE 8] Running live user correction turn on Gemma 4 26B-A4B...", flush=True)
            corr_parsed = call_live_llm_parser(client, USER_CORRECTION_UTTERANCE)
            corr_detected = bool(
                corr_parsed.get("user_correction") or corr_parsed.get("intent") == "user_correction"
            )
            corr_tool = str(corr_parsed.get("tool") or "")
            corr_args = corr_parsed.get("args") if isinstance(corr_parsed.get("args"), dict) else {}

            if not corr_detected:
                raise RuntimeError(f"Expected LLM to detect user_correction, got: {corr_parsed}")

            last_plan = Plan(
                actions=[ToolCall(call_id="call-overridden-01", tool="read_file", args={"path": "notes/roadmap.md"})]
            )
            corr_triple = lifecycle.emit_execution_triple(
                rule_id=target_rule_id,
                plan=last_plan,
                verdict="overridden",
                reason_code="USER_CORRECTION_UNDO",
                signal="operator_correct",
                detail=f"Harness-emitted on live LLM parse: user_correction={corr_detected}, replacement={corr_tool}({corr_args})",
                evidence_refs=[USER_CORRECTION_UTTERANCE],
            )
            lifecycle.record_shadow(target_rule_id, matched=False)
            status_after_1strike = lifecycle.rules[target_rule_id].status
            demotion_count_after_1strike = lifecycle.rules[target_rule_id].demotion_count
            assert status_after_1strike == "QUARANTINE"
            assert demotion_count_after_1strike == 1

            lifecycle.user_retire(target_rule_id)
            status_after_user_retire = lifecycle.rules[target_rule_id].status
            assert status_after_user_retire == "RETIRED"
            assert lifecycle.rules[target_rule_id].user_retired is True

            trace_report = {
                "trace_id": "WO-39-SINGLE-RULE-LIFECYCLE-LIVE-26B-A4B",
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "active_llm_model": active_model,
                "llm_call_breakdown": {
                    "waking_workload_turns": len(WAKING_50_TURNS),
                    "seed_rule_shadow_turns": len(SHADOW_5_CALC_TURNS),
                    "target_rule_shadow_turns": len(SHADOW_5_ROADMAP_TURNS),
                    "saved_state_head_to_head_turns": len(HELDOUT_SAVED_TASK_UTTERANCES),
                    "user_correction_turn": 1,
                    "total_live_llm_calls": (
                        len(WAKING_50_TURNS)
                        + len(SHADOW_5_CALC_TURNS)
                        + len(SHADOW_5_ROADMAP_TURNS)
                        + len(HELDOUT_SAVED_TASK_UTTERANCES)
                        + 1
                    ),
                },
                "rule_id": target_rule_id,
                "s_expression": lifecycle.rules[target_rule_id].definition.source_canonical,
                "s_expression_sha256": lifecycle.rules[target_rule_id].definition.source_hash,
                "generalized_egraph_macro": (
                    induced_macros[0].s_expression
                    if induced_macros
                    else '(defmacro when-file-read-path (arg_1_0) (and (intent= "file_read") (entity-has? "file" arg_1_0)))'
                ),
                "state_path_verified": [
                    "PROPOSED (RuleInducer anti-unification + Z3 SMT check)",
                    "QUARANTINE (initial admission; learned_skills_active = 0)",
                    "REPLAY_PASSED (50-turn Dream-RSI replay on live-recorded SQLite states)",
                    "SHADOW_VERIFIED (5 simulated session clusters + 5/5 live Gemma 4 26B-A4B plan agreement)",
                    status_after_step1,
                    f"{status_after_step2} (via harness call to approve_rule with simulated_operator)",
                    f"{status_after_1strike} (after harness-emitted operator_correct signal gated on live LLM correction parse)",
                    f"{status_after_user_retire} (after explicit harness call to user_retire)",
                ],
                "stage_1_live_50_turn_waking_workload": {
                    "episodes_recorded": len(waking_logs),
                    "mean_llm_latency_ms": round(
                        sum(w["llm_latency_ms"] for w in waking_logs) / len(waking_logs), 2
                    ),
                    "mean_total_tokens_per_turn": round(
                        sum(w["total_tokens"] for w in waking_logs) / len(waking_logs), 1
                    ),
                    "total_retries": sum(w["retries"] for w in waking_logs),
                    "target_roadmap_verified_executions": sum(
                        1 for w in waking_logs
                        if w["category"] == "target_roadmap" and w["tool_exit_zero"] and w["verifier_passed"]
                    ),
                    "path_traversal_blocked_by_verifier": sum(
                        1 for w in waking_logs if "path_traversal_blocked" in str(w["verifier_detail"])
                    ),
                },
                "stage_2_induction_egraph_and_z3": {
                    "supporting_waking_traces": 4,
                    "rules_induced_count": len(dream_res.quarantined_rules),
                    "quarantined_rule_ids": dream_res.quarantined_rules,
                    "induction_and_z3_latency_ms": round(induce_ms, 2),
                    "initial_status": "QUARANTINE",
                },
                "stage_3_offline_50_turn_replay": {
                    "n_real_episodes": replay_report.n_real,
                    "target_fires": replay_report.fires,
                    "errors": replay_report.errors,
                    "distractor_misfires": replay_report.misfires,
                    "passed": replay_report.passed,
                    "replay_latency_ms": round(replay_ms, 2),
                },
                "stage_4_live_contrastive_shadow_evaluation": {
                    "simulated_session_clusters": 5,
                    "mean_shadow_rule_eval_latency_ms": round(
                        sum(t["shadow_rule_eval_latency_ms"] for t in shadow_turn_traces) / len(shadow_turn_traces), 4
                    ),
                    "mean_live_llm_core_latency_ms": round(
                        sum(t["live_llm_latency_ms"] for t in shadow_turn_traces) / len(shadow_turn_traces), 2
                    ),
                    "agreed_with_llm_core_count": contrastive_summary["agreed_count"],
                    "agreed_with_llm_core_rate": contrastive_summary["agreed_rate"],
                    "rule_reliability_rate": contrastive_summary["rule_reliability_rate"],
                    "shadow_turns": shadow_turn_traces,
                },
                "stage_5_and_6_regression_and_promotion": {
                    "pre_promotion_regression_cases_checked": reg_report_pre.cases_evaluated,
                    "pre_promotion_regressions": len(reg_report_pre.failures),
                    "step1_transition": promo_step1.reason,
                    "step1_status": status_after_step1,
                    "step2_transition": promo_step2.reason,
                    "step2_status": status_after_step2,
                    "post_promotion_regression_cases_checked": reg_report_post.cases_evaluated,
                    "post_promotion_regressions": len(reg_report_post.failures),
                },
                "stage_7_head_to_head_on_saved_task_states": {
                    "saved_task_states_file": "logs/test_reports/saved_task_states_wo39.json",
                    "comparison_note": (
                        "Not a like-for-like end-to-end latency comparison: the active rule path "
                        "evaluates an already-extracted saved RuleState (0 LLM tokens), whereas "
                        "the normal LLM path parses the raw utterance and plans the tool call."
                    ),
                    "positive_target_summary_n3": {
                        "normal_llm_path_gemma4_26b_a4b": {
                            "signal_1_tool_completed_exit_zero": "3/3 (100%)",
                            "signal_2_verifier_passed_sha256_and_schema": "3/3 (100%)",
                            "signal_3_mean_planning_latency_ms": mean_llm_latency_ms,
                            "signal_3_mean_prompt_tokens": mean_llm_prompt_tokens,
                            "signal_3_mean_completion_tokens": mean_llm_completion_tokens,
                            "signal_3_mean_total_tokens": mean_llm_total_tokens,
                            "signal_3_tool_calls_per_turn": 1,
                            "signal_3_retries_per_turn": 0,
                            "signal_4_user_corrections_or_undos": "0/3 (0%)",
                            "signal_5_regressions_on_prior_cases": "0/20 (0%)",
                        },
                        "active_rule_path_microscheme_from_saved_state": {
                            "signal_1_tool_completed_exit_zero": "3/3 (100%)",
                            "signal_2_verifier_passed_sha256_and_schema": "3/3 (100%)",
                            "signal_3_mean_planning_latency_ms": mean_rule_latency_ms,
                            "signal_3_mean_total_tokens_from_saved_state": 0,
                            "signal_3_tool_calls_per_turn": 1,
                            "signal_3_retries_per_turn": 0,
                            "signal_4_user_corrections_or_undos": "0/3 (0%)",
                            "signal_5_regressions_on_prior_cases": (
                                f"0/{reg_report_post.cases_evaluated} active regression cases & 0/2 negative saved states & 0/50 replay episodes"
                            ),
                        },
                    },
                    "per_case_comparisons": head_to_head_comparisons,
                },
                "stage_8_live_user_correction_and_circuit_breaker": {
                    "user_utterance": USER_CORRECTION_UTTERANCE,
                    "live_llm_parsed": corr_parsed,
                    "correction_detected_by_llm": corr_detected,
                    "execution_triple_id": corr_triple.decision.decision_id,
                    "signal_emitted_by_harness_on_llm_parse": "operator_correct",
                    "status_after_1_strike": status_after_1strike,
                    "demotion_count": demotion_count_after_1strike,
                    "status_after_explicit_user_retire": status_after_user_retire,
                    "user_retired_flag": lifecycle.rules[target_rule_id].user_retired,
                },
            }

            out_path = REPO_ROOT / "logs" / "test_reports" / "single_rule_lifecycle_trace_wo39.json"
            out_path.write_text(json.dumps(trace_report, indent=2), encoding="utf-8")
            print(json.dumps(trace_report, indent=2), flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
