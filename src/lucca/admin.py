"""
Project Lucca — Admin & Diagnostic CLI
Spec 11 §7 (`lucca-admin`), F-CORE-026, F-CORE-027, F-DRIFT-003
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import JsonValue
from rich.console import Console
from rich.table import Table

from lucca.core.config import get_config
from lucca.core.env_check import check_models_manifest, run_env_check
from lucca.core.trace import (
    StageStat,
    compute_latency_statistics,
    format_latency_markdown,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.manager import MemoryManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.skills import SkillManager
from lucca.reasoning.stats import rule_of_three_ucl
from lucca.sandbox.egress import EgressVerifier


def load_trace_records(
    logs_dir: Path,
    last: int = 100,
    mode: str = "audio",
    origin: str = "ptt",
) -> list[dict[str, JsonValue]]:
    """Loads and filters trace entries from logs/traces.jsonl or dated files."""
    records: list[dict[str, JsonValue]] = []
    canonical = logs_dir / "traces.jsonl"
    files: list[Path] = []
    if canonical.exists():
        files.append(canonical)
    else:
        files = sorted(logs_dir.glob("traces-*.jsonl"), reverse=False)

    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                for raw_line in fp:
                    line = raw_line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            if mode != "all" and data.get("mode") != mode:
                                continue
                            if origin != "all" and data.get("origin", "ptt") != origin:
                                continue
                            records.append(data)
                    except Exception:  # noqa: BLE001, S110, S112
                        continue
        except Exception:  # noqa: BLE001, S110, S112
            continue

    if last > 0 and len(records) > last:
        records = records[-last:]
    return records


def run_latency_cli(
    last: int = 100,
    mode: str = "audio",
    origin: str = "ptt",
    fmt: str = "table",
    output: str | None = None,
) -> int:
    """Computes and displays Spec 10 latency statistics from real trace records."""
    config = get_config()
    logs_dir = config.resolve_path("logs")
    records = load_trace_records(logs_dir, last=last, mode=mode, origin=origin)

    if not records:
        print(f"No matching trace records found in '{logs_dir}' (mode={mode}, origin={origin}).")
        return 0

    mode_literal: Literal["audio", "transcript"] = "transcript" if mode == "transcript" else "audio"
    stats: list[StageStat] = compute_latency_statistics(records, mode=mode_literal)

    if fmt == "json":
        out_json = json.dumps([s.model_dump() for s in stats], indent=2)
        print(out_json)
        if output:
            p = Path(output)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(out_json, encoding="utf-8")
        return 0

    if fmt == "markdown":
        md = format_latency_markdown(stats, mode=mode, sample_count=len(records))
        print(md)
        if output:
            p = Path(output)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md, encoding="utf-8")
        return 0

    # Default table format
    console = Console()
    table = Table(
        title=f"Lucca Latency Report — {mode.capitalize()} Mode (Last {len(records)} Turns)",
        caption="Spec 10 §2 Latency Budgets & Gates",
    )
    table.add_column("Stage", style="cyan", no_wrap=True)
    table.add_column("From -> To", style="magenta")
    table.add_column("Budget (med / p95)", justify="right")
    table.add_column("Measured Median", justify="right")
    table.add_column("Measured p95", justify="right")
    table.add_column("Count", justify="right")
    table.add_column("Status", justify="center")

    for s in stats:
        med_str = f"{s.measured_med:.1f} ms" if s.measured_med is not None else "-"
        p95_str = f"{s.measured_p95:.1f} ms" if s.measured_p95 is not None else "-"
        status_style = (
            "[green]PASS[/green]"
            if s.status == "PASS"
            else (
                "[red]FAIL[/red]"
                if s.status in ("FAIL", "REGRESSION")
                else f"[yellow]{s.status}[/yellow]"
            )
        )
        table.add_row(
            s.stage,
            s.from_to,
            f"{s.budget_med:.0f} / {s.gate_p95:.0f} ms",
            med_str,
            p95_str,
            str(s.count),
            status_style,
        )

    console.print(table)

    if output:
        md = format_latency_markdown(stats, mode=mode, sample_count=len(records))
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(md, encoding="utf-8")
        print(f"Report written to {p}")

    return 0


def run_logs_tail(proc: str = "core", lines_count: int = 20) -> int:
    """Tails recent log entries for a given process."""
    config = get_config()
    logs_dir = config.resolve_path("logs")
    direct_target = logs_dir / f"{proc}.log"
    target: Path | None = direct_target
    if not direct_target.exists():
        matches = sorted(logs_dir.glob(f"{proc}*.jsonl"), reverse=True) + sorted(
            logs_dir.glob(f"{proc}*.log"), reverse=True
        )
        target = matches[0] if matches else None
    if target is None or not target.exists():
        print(f"No log file found for process '{proc}' in '{logs_dir}'", file=sys.stderr)
        return 1
    with open(target, encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines[-lines_count:]:
        print(line, end="")
    return 0


def run_rules_cli(
    action: str,
    rule_id: str | None = None,
    approver: str = "operator",
    db_path: Path | None = None,
    rule_source: str | None = None,
) -> int:
    """Manages MicroScheme rules and human approval gates via CLI."""
    if db_path is None:
        config = get_config()
        db_path = config.resolve_path("data") / "memory.sqlite"

    db = DatabaseManager(db_path=db_path)
    db.migrate()
    manager = RuleLifecycleManager(db=db)

    console = Console()

    if action == "register":
        if not rule_source:
            console.print("[red]Error: rule source or file path is required to register.[/red]")
            return 1
        src_path = Path(rule_source)
        if src_path.exists() and src_path.is_file():
            rule_text = src_path.read_text(encoding="utf-8")
        else:
            rule_text = rule_source
        try:
            managed = manager.register_rule(rule_text)
            console.print(
                f"[bold green]SUCCESS:[/bold green] Rule '{managed.rule_id}' registered in "
                "[blue]QUARANTINE[/blue] mode."
            )
            return 0
        except Exception as err:  # noqa: BLE001
            console.print(f"[bold red]FAILED:[/bold red] Failed to register rule: {err}")
            return 1

    if action == "list":
        if not manager.rules:
            console.print("[yellow]No rules currently registered in the database.[/yellow]")
            return 0

        table = Table(
            title="MicroScheme Rule Registry — Status & Lifecycle",
            caption="Spec 05 §8–§9 Rule Promotion & Human Gate",
        )
        table.add_column("Rule ID", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center", no_wrap=True)
        table.add_column("Priority", justify="right")
        table.add_column("Clusters", justify="right")
        table.add_column("Failures", justify="right")
        table.add_column("Demotions", justify="right")

        for r in sorted(manager.rules.values(), key=lambda x: x.rule_id):
            if r.status == "ACTIVE":
                status_style = "[green]ACTIVE[/green]"
            elif r.status == "PENDING_APPROVAL":
                status_style = "[bold yellow]PENDING_APPROVAL[/bold yellow]"
            elif r.status == "QUARANTINE":
                status_style = "[blue]QUARANTINE[/blue]"
            elif r.status == "DEMOTED":
                status_style = "[magenta]DEMOTED[/magenta]"
            else:
                status_style = "[red]RETIRED[/red]"

            table.add_row(
                r.rule_id,
                status_style,
                str(r.definition.priority),
                f"{len(r.success_clusters)} / 5",
                str(r.failure_count),
                str(r.demotion_count),
            )
        console.print(table)
        return 0

    if action == "approve":
        if not rule_id:
            console.print("[red]Error: rule_id is required for approval.[/red]")
            return 1
        result = manager.approve_rule(rule_id, approver=approver)
        if result.promoted:
            console.print(
                f"[bold green]SUCCESS:[/bold green] Rule '{rule_id}' approved by "
                f"'{approver}' and promoted to ACTIVE."
            )
            return 0
        console.print(
            f"[bold red]FAILED:[/bold red] Could not approve rule '{rule_id}': {result.reason}"
        )
        return 1

    if action == "retire":
        if not rule_id:
            console.print("[red]Error: rule_id is required to retire.[/red]")
            return 1
        if rule_id not in manager.rules:
            console.print(f"[red]Error: Rule '{rule_id}' not found in registry.[/red]")
            return 1
        manager.user_retire(rule_id)
        console.print(f"[bold yellow]RETIRED:[/bold yellow] Rule '{rule_id}' has been retired.")
        return 0

    if action == "replay":
        if not rule_id:
            console.print("[red]Error: rule_id is required for replay evaluation.[/red]")
            return 1
        if rule_id not in manager.rules:
            console.print(f"[red]Error: Rule '{rule_id}' not found in registry.[/red]")
            return 1
        report = manager.replay_candidate(rule_id)
        if report.passed:
            console.print(
                f"[bold green]SUCCESS: Replay Passed.[/bold green] Rule '{rule_id}' passed "
                f"Dream-RSI offline replay across {report.n_real} recorded episodes "
                f"(0 errors, 0 misfires, {report.fires} fires)."
            )
            return 0
        console.print(
            f"[bold red]FAILED: Replay Refused.[/bold red] Rule '{rule_id}' failed "
            "offline replay.\n"
            f"Episodes: {report.n_real} / {report.min_required} required\n"
            f"Errors: {report.errors}, Misfires: {report.misfires}\n"
            "Reasons:\n  - " + "\n  - ".join(report.reasons)
        )
        if report.error_details:
            console.print("[yellow]Error Details:[/yellow]")
            for d in report.error_details[:5]:
                console.print(f"  * {d}")
        return 1

    if action == "report":
        if not manager.rules:
            console.print("[yellow]No rules currently registered in the database.[/yellow]")
            return 0

        table = Table(
            title="MicroScheme Rule Capability Telemetry & Contrastive Evaluation Report",
            caption="Spec 1.1.2 §5 (S1 Contract), §6.2 (Rung L2)",
        )
        table.add_column("Rule ID", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center", no_wrap=True)
        table.add_column("Clusters (95% CI)", justify="right")
        table.add_column("Agreed Rate (95% CI)", justify="right")
        table.add_column("Rule Better (b)", justify="right")
        table.add_column("Core Better (c)", justify="right")
        table.add_column("McNemar p", justify="right")
        table.add_column("Execution-Reliability Rate (S1)", justify="right")

        for r in sorted(manager.rules.values(), key=lambda x: x.rule_id):
            summary = manager.get_contrastive_summary(r.rule_id)
            total_turns = int(summary.get("total_turns", 0))
            agreed_rate = float(summary.get("agreed_rate", 0.0))
            agreed_interval_raw = summary.get("agreed_interval", [0.0, 1.0])
            agreed_interval = (
                agreed_interval_raw
                if isinstance(agreed_interval_raw, list) and len(agreed_interval_raw) == 2
                else [0.0, 1.0]
            )
            b = int(summary.get("b_rule_better", 0))
            c = int(summary.get("c_core_better", 0))
            p_val = float(summary.get("mcnemar_p_value", 1.0))
            rel_rate = float(summary.get("rule_reliability_rate", 0.0))
            rel_interval_raw = summary.get("rule_reliability_interval", [0.0, 1.0])
            rel_interval = (
                rel_interval_raw
                if isinstance(rel_interval_raw, list) and len(rel_interval_raw) == 2
                else [0.0, 1.0]
            )

            # Spec §6.1 (Rule of Three): shadow clusters prove intent recurrence, never
            # safety. 0 failures in n clusters bounds the failure rate to <= 3/n (95%
            # one-sided UCL) — display that, not a Wilson CI on a non-Bernoulli count.
            n_clusters = len(r.success_clusters)
            fail_ucl = rule_of_three_ucl(n_clusters)
            cluster_str = f"{n_clusters}/5 (0 err -> fail <= {fail_ucl:.0%})"

            ag_lb_str = f"{float(agreed_interval[0]):.1%}"
            ag_ub_str = f"{float(agreed_interval[1]):.1%}"
            agreed_str = (
                f"{agreed_rate:.1%} [{ag_lb_str}, {ag_ub_str}]" if total_turns > 0 else "N/A"
            )
            p_str = f"{p_val:.3f}" if (b + c) > 0 else "N/A"
            rel_str = (
                f"{rel_rate:.1%} [{float(rel_interval[0]):.1%}, {float(rel_interval[1]):.1%}]"
                if total_turns > 0
                else "N/A"
            )

            status_style = (
                "[green]ACTIVE[/green]"
                if r.status == "ACTIVE"
                else "[bold yellow]PENDING_APPROVAL[/bold yellow]"
                if r.status == "PENDING_APPROVAL"
                else "[blue]QUARANTINE[/blue]"
                if r.status == "QUARANTINE"
                else "[red]RETIRED[/red]"
            )

            table.add_row(
                r.rule_id,
                status_style,
                cluster_str,
                agreed_str,
                str(b),
                str(c),
                p_str,
                rel_str,
            )
        console.print(table)
        return 0

    console.print(f"[red]Unknown rules action: {action}[/red]")
    return 1


def run_skills_cli(
    action: str,
    package_dir: str | None = None,
    skill_id: str | None = None,
    db_path: Path | None = None,
    skills_dir: Path | None = None,
) -> int:
    """Manages LISP Studio skill packages and lifecycle per Spec 1.1.2 §3 (L1a)."""
    if db_path is None:
        config = get_config()
        db_path = config.resolve_path("data") / "memory.sqlite"

    db = DatabaseManager(db_path=db_path)
    db.migrate()
    lifecycle_manager = RuleLifecycleManager(db=db, skills_dir=skills_dir)
    skill_manager = SkillManager(skills_dir=skills_dir, rule_engine=lifecycle_manager)

    console = Console()

    if action == "register":
        if not package_dir:
            console.print("[red]Error: package directory path is required to register.[/red]")
            return 1
        pkg_path = Path(package_dir)
        try:
            pkg = skill_manager.register_package(pkg_path)
            console.print(
                f"[bold green]SUCCESS:[/bold green] Skill '{pkg.meta.id}' registered in "
                "[green]ACTIVE[/green] status."
            )
            return 0
        except Exception as err:  # noqa: BLE001
            console.print(f"[bold red]FAILED:[/bold red] Could not register skill package: {err}")
            return 1

    if action == "list":
        records = skill_manager.list_skills()
        if not records:
            console.print("[yellow]No skill packages currently registered.[/yellow]")
            return 0

        table = Table(
            title="LISP Studio Skill Registry — Packages & Lifecycle",
            caption="Spec 1.1.2 §3 Skill Package Format & §13 Ladder (L1a)",
        )
        table.add_column("Skill ID", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center", no_wrap=True)
        table.add_column("Categories", justify="left")
        table.add_column("Expose As Tool", justify="center")
        table.add_column("Clusters", justify="right")
        table.add_column("Failures", justify="right")

        for r in records:
            status_val = str(r.get("status", "QUARANTINE"))
            if status_val == "ACTIVE":
                status_style = "[green]ACTIVE[/green]"
            elif status_val == "PENDING_APPROVAL":
                status_style = "[bold yellow]PENDING_APPROVAL[/bold yellow]"
            elif status_val == "QUARANTINE":
                status_style = "[blue]QUARANTINE[/blue]"
            elif status_val == "DEMOTED":
                status_style = "[magenta]DEMOTED[/magenta]"
            else:
                status_style = "[red]RETIRED[/red]"

            table.add_row(
                str(r.get("id", "")),
                status_style,
                str(r.get("categories", "-")),
                str(r.get("expose_as_tool", False)),
                str(r.get("clusters", "- / 5")),
                str(r.get("failures", 0)),
            )
        console.print(table)
        return 0

    if action == "retire":
        if not skill_id:
            console.print("[red]Error: skill_id is required to retire.[/red]")
            return 1
        try:
            skill_manager.retire_skill(skill_id)
            console.print(
                f"[bold yellow]RETIRED:[/bold yellow] Skill '{skill_id}' "
                "retired and moved to _retired/."
            )
            return 0
        except Exception as err:  # noqa: BLE001
            console.print(
                f"[bold red]FAILED:[/bold red] Could not retire skill '{skill_id}': {err}"
            )
            return 1

    console.print(f"[red]Unknown skills action: {action}[/red]")
    return 1


def run_memory_cli(
    action: str,
    db_path: Path | None = None,
    search: str = "",
    limit: int = 20,
    status: str = "PENDING",
    review_id: str | None = None,
    approver: str = "operator",
    topic: str | None = None,
) -> int:
    """Manages autobiographical memory, belief revisions, and review queue (D-MEM-04, Rung A1)."""
    if db_path is None:
        config = get_config()
        db_path = config.resolve_path("data") / "memory.sqlite"

    db = DatabaseManager(db_path=db_path)
    db.migrate()

    cfg = get_config()
    mk: bytes | None = None
    if cfg.master_key:
        mk = cfg.master_key.encode("utf-8")
    elif cfg.env.mode == "dev":
        mk = b"01234567890123456789012345678901"

    manager = MemoryManager(db=db, master_key=mk)
    console = Console()

    if action == "list":
        mems = manager.list_memories(search=search)
        if not mems:
            console.print("[yellow]No matching memories found.[/yellow]")
            return 0
        table = Table(
            title=f"Lucca Memory Store — Active Records (Showing up to {limit})",
            caption="Spec D-MEM-04 Autobiographical Memory & Provenance",
        )
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Kind", style="magenta")
        table.add_column("Content / Fact Statement", justify="left")
        table.add_column("Importance", justify="right")
        table.add_column("Provenance", style="blue")
        table.add_column("Confidence", justify="right")

        for m in mems[:limit]:
            table.add_row(
                str(m.get("memory_id", "")),
                str(m.get("kind", "")),
                str(m.get("content", "")),
                f"{float(m.get('importance', 0.8)):.2f}",
                str(m.get("provenance", "")),
                f"{float(m.get('confidence', 1.0)):.2f}",
            )
        console.print(table)
        return 0

    if action == "review-queue":
        items = manager.list_review_queue(status=status)
        if not items:
            console.print(f"[yellow]No review queue items with status '{status}'.[/yellow]")
            return 0
        table = Table(
            title=f"Belief Revision Review Queue — Status: {status}",
            caption="Spec D-MEM-04 §7 5-Flag Operator Review Gate",
        )
        table.add_column("Review ID", style="cyan", no_wrap=True)
        table.add_column("Belief ID", justify="right")
        table.add_column("Old Content", style="red")
        table.add_column("Proposed Content", style="green")
        table.add_column("Trigger Reason", style="yellow")
        table.add_column("Status", justify="center")

        for it in items:
            status_style = (
                "[bold yellow]PENDING[/bold yellow]"
                if it["status"] == "PENDING"
                else (
                    "[bold green]APPROVED[/bold green]"
                    if it["status"] == "APPROVED"
                    else "[bold red]REJECTED[/bold red]"
                )
            )
            table.add_row(
                str(it["review_id"]),
                str(it["belief_id"] or "-"),
                str(it["old_content"] or "-"),
                str(it["proposed_content"]),
                str(it["trigger_reason"]),
                status_style,
            )
        console.print(table)
        return 0

    if action == "review-approve":
        if not review_id:
            console.print("[red]Error: review_id is required to approve.[/red]")
            return 1
        if mk is None:
            console.print("[red]Error: master_key required to sign revised beliefs.[/red]")
            return 1
        store = MemoryStore(db=db, master_key=mk)
        reflection = ReflectionEngine(db=db, store=store, master_key=mk)
        try:
            new_mid = asyncio.run(reflection.approve_review(review_id, decided_by=approver))
            console.print(
                f"[bold green]SUCCESS: Review '{review_id}' approved by '{approver}'.[/bold green] "
                f"New memory ID: {new_mid}"
            )
            return 0
        except Exception as err:  # noqa: BLE001
            console.print(
                f"[bold red]FAILED: Could not approve review '{review_id}': {err}[/bold red]"
            )
            return 1

    if action == "review-reject":
        if not review_id:
            console.print("[red]Error: review_id is required to reject.[/red]")
            return 1
        if mk is None:
            console.print("[red]Error: master_key required.[/red]")
            return 1
        store = MemoryStore(db=db, master_key=mk)
        reflection = ReflectionEngine(db=db, store=store, master_key=mk)
        try:
            reflection.reject_review(review_id, decided_by=approver)
            console.print(
                f"[bold yellow]REJECTED: Review '{review_id}' rejected by "
                f"'{approver}'.[/bold yellow] Old belief preserved."
            )
            return 0
        except Exception as err:  # noqa: BLE001
            console.print(
                f"[bold red]FAILED: Could not reject review '{review_id}': {err}[/bold red]"
            )
            return 1

    if action == "mark-review":
        if not topic:
            console.print("[red]Error: topic name is required to mark review.[/red]")
            return 1
        manager.mark_topic_review_required(topic)
        console.print(
            f"[bold green]SUCCESS: Topic '{topic.strip().lower()}' "
            "marked as review-required.[/bold green]"
        )
        return 0

    if action == "unmark-review":
        if not topic:
            console.print("[red]Error: topic name is required to unmark review.[/red]")
            return 1
        manager.unmark_topic_review_required(topic)
        console.print(
            f"[bold green]SUCCESS: Topic '{topic.strip().lower()}' "
            "removed from review-required.[/bold green]"
        )
        return 0

    if action == "list-topics":
        topics = manager.list_review_required_topics()
        if not topics:
            console.print("[yellow]No topics currently marked as review-required.[/yellow]")
            return 0
        table = Table(
            title="Review-Required Topics — Human Operator Gating",
            caption="Spec D-MEM-04 §7 (Flag 5)",
        )
        table.add_column("Topic", style="cyan")
        for t in topics:
            table.add_row(t)
        console.print(table)
        return 0

    if action == "rollup":
        if mk is None:
            console.print("[red]Error: master_key required for roll-up.[/red]")
            return 1
        store = MemoryStore(db=db, master_key=mk)
        reflection = ReflectionEngine(db=db, store=store, master_key=mk)
        try:
            count = reflection.rollup_nightly()
            console.print(
                f"[bold green]SUCCESS: Nightly roll-up complete.[/bold green] "
                f"Compressed {count} low-importance autobiographical memories into "
                "session summaries."
            )
            return 0
        except Exception as err:  # noqa: BLE001
            console.print(f"[bold red]FAILED: Roll-up failed: {err}[/bold red]")
            return 1

    console.print(f"[red]Unknown memory action: {action}[/red]")
    return 1


def create_parser() -> argparse.ArgumentParser:
    """Builds the normative lucca-admin argument parser (Spec 11 §7)."""
    parser = argparse.ArgumentParser(
        prog="lucca-admin",
        description="Project Lucca — Admin & Telemetry CLI (Spec 11 §7)",
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # env-check
    subparsers.add_parser("env-check", help="Run system environment diagnostics")

    # latency
    p_latency = subparsers.add_parser(
        "latency", help="Latency trace analysis and budget verification"
    )
    p_latency.add_argument(
        "--last",
        "-n",
        type=int,
        default=100,
        help="Number of recent turns to analyze (default: 100)",
    )
    p_latency.add_argument(
        "--mode",
        choices=["audio", "transcript", "all"],
        default="audio",
        help="Filter turns by mode (audio, transcript, all)",
    )
    p_latency.add_argument(
        "--origin",
        choices=["ptt", "text", "all"],
        default="ptt",
        help="Filter turns by origin (ptt, text, all)",
    )
    p_latency.add_argument(
        "--format",
        choices=["table", "markdown", "json"],
        default="table",
        help="Output format (table, markdown, json)",
    )
    p_latency.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Optional file path to write the latency report",
    )

    # models
    p_models = subparsers.add_parser("models", help="Model weight integrity and verification")
    p_models.add_argument("action", choices=["verify"], help="Verification action")

    # sandbox
    p_sandbox = subparsers.add_parser("sandbox", help="Sandbox isolation and egress verification")
    p_sandbox.add_argument(
        "action",
        choices=["verify", "rebuild", "reset-workspace"],
        help="Sandbox action",
    )

    # logs
    p_logs = subparsers.add_parser("logs", help="Inspect and tail runtime logs")
    p_logs.add_argument("action", choices=["tail"], help="Logs action")
    p_logs.add_argument(
        "--proc",
        default="core",
        help="Process log to inspect (core, audio, npu, traces)",
    )
    p_logs.add_argument(
        "-n",
        "--lines",
        type=int,
        default=20,
        help="Number of lines to tail (default: 20)",
    )

    # rules
    p_rules = subparsers.add_parser(
        "rules", help="MicroScheme rule lifecycle management and approvals"
    )
    p_rules.add_argument("--db", type=str, default=None, help="Optional database path")
    rules_sub = p_rules.add_subparsers(dest="action", required=True)
    rules_sub.add_parser("list", help="List all rules and their lifecycle status")

    p_appr = rules_sub.add_parser(
        "approve", help="Approve a quarantined/pending rule into active service"
    )
    p_appr.add_argument("rule_id", help="Rule identifier to approve")
    p_appr.add_argument(
        "--approver", default="operator", help="Approver identity (default: operator)"
    )

    p_ret = rules_sub.add_parser("retire", help="Retire an active or quarantined rule")
    p_ret.add_argument("rule_id", help="Rule identifier to retire")

    p_reg = rules_sub.add_parser(
        "register", help="Register a new MicroScheme rule in QUARANTINE mode"
    )
    p_reg.add_argument("source", help="Rule S-expression string or path to .scm file")

    p_rep = rules_sub.add_parser(
        "replay", help="Run Dream-RSI offline replay evaluation on a candidate rule"
    )
    p_rep.add_argument("rule_id", help="Rule identifier to replay")

    rules_sub.add_parser(
        "report", help="Print Studio capability telemetry and contrastive evaluation report"
    )

    # skills
    p_skills = subparsers.add_parser(
        "skills", help="LISP Studio skill package management (Spec 1.1.2 §3, L1a)"
    )
    p_skills.add_argument("--db", type=str, default=None, help="Optional database path")
    p_skills.add_argument(
        "--skills-dir", type=str, default=None, help="Optional skills directory path"
    )
    skills_sub = p_skills.add_subparsers(dest="action", required=True)
    skills_sub.add_parser("list", help="List all skill packages and their lifecycle status")

    p_sreg = skills_sub.add_parser("register", help="Register a new skill package")
    p_sreg.add_argument("package_dir", help="Path to skill package directory")

    p_sret = skills_sub.add_parser("retire", help="Retire an active skill package")
    p_sret.add_argument("skill_id", help="Skill identifier to retire")

    # memory
    p_mem = subparsers.add_parser(
        "memory", help="Autobiographical memory, review queue & belief revision (D-MEM-04, Rung A1)"
    )
    p_mem.add_argument("--db", type=str, default=None, help="Optional database path")
    mem_sub = p_mem.add_subparsers(dest="action", required=True)

    p_mlist = mem_sub.add_parser("list", help="List active memories")
    p_mlist.add_argument("--search", "-s", type=str, default="", help="Search filter")
    p_mlist.add_argument("--limit", "-n", type=int, default=20, help="Max memories to show")

    p_rq = mem_sub.add_parser("review-queue", help="List items in belief review queue")
    p_rq.add_argument(
        "--status",
        choices=["PENDING", "APPROVED", "REJECTED", "ALL"],
        default="PENDING",
        help="Filter review items by status",
    )

    p_rappr = mem_sub.add_parser("review-approve", help="Approve a pending belief revision")
    p_rappr.add_argument("review_id", help="Review item ID to approve")
    p_rappr.add_argument("--approver", default="operator", help="Approver identity")

    p_rrej = mem_sub.add_parser("review-reject", help="Reject a pending belief revision")
    p_rrej.add_argument("review_id", help="Review item ID to reject")
    p_rrej.add_argument("--approver", default="operator", help="Approver identity")

    p_rmark = mem_sub.add_parser("mark-review", help="Mark a topic as requiring operator review")
    p_rmark.add_argument("topic", help="Topic name to mark")

    p_runmark = mem_sub.add_parser("unmark-review", help="Remove topic from review-required list")
    p_runmark.add_argument("topic", help="Topic name to unmark")

    mem_sub.add_parser("list-topics", help="List all review-required topics")

    mem_sub.add_parser("rollup", help="Run nightly roll-up of low-importance memories")

    # Stubs per F-CORE-027
    for stub in ["metrics", "router", "replay"]:
        sub = subparsers.add_parser(
            stub, help=f"{stub.capitalize()} management (not implemented, tracked as F-CORE-027)"
        )
        sub.add_argument("rest", nargs="*", help="Subcommand arguments")

    return parser


def main(argv: list[str] | None = None) -> None:
    args_list = argv if argv is not None else sys.argv[1:]
    if not args_list or (len(args_list) == 1 and args_list[0] == "help"):
        parser = create_parser()
        parser.print_help()
        sys.exit(0)

    parser = create_parser()
    args = parser.parse_args(args_list)

    if args.cmd == "env-check":
        sys.exit(run_env_check())
    elif args.cmd == "latency":
        sys.exit(
            run_latency_cli(
                last=args.last,
                mode=args.mode,
                origin=args.origin,
                fmt=args.format,
                output=args.output,
            )
        )
    elif args.cmd == "models":
        if args.action == "verify":
            ok, msg = check_models_manifest()
            status = "[PASS]" if ok else "[FAIL]"
            print(f"{status} {msg}")
            sys.exit(0 if ok else 1)
        else:
            print("not implemented (tracked as F-CORE-027)")
            sys.exit(3)
    elif args.cmd == "sandbox":
        if args.action == "verify":
            verifier = EgressVerifier()
            res = verifier.verify_all()

            all_passed = bool(res.get("all_passed", False))
            status = "[PASS]" if all_passed else "[FAIL]"
            print(f"{status} Sandbox verification: {res}")
            sys.exit(0 if all_passed else 1)
        else:
            print("not implemented (tracked as F-CORE-027)")
            sys.exit(3)
    elif args.cmd == "logs":
        if args.action == "tail":
            sys.exit(run_logs_tail(proc=args.proc, lines_count=args.lines))
        else:
            print("not implemented (tracked as F-CORE-027)")
            sys.exit(3)
    elif args.cmd == "rules":
        rule_id = getattr(args, "rule_id", None)
        rule_source = getattr(args, "source", None)
        approver = getattr(args, "approver", "operator")
        db_arg = getattr(args, "db", None)
        db_path = Path(db_arg) if db_arg else None
        sys.exit(
            run_rules_cli(
                action=args.action,
                rule_id=rule_id,
                approver=approver,
                db_path=db_path,
                rule_source=rule_source,
            )
        )
    elif args.cmd == "skills":
        package_dir = getattr(args, "package_dir", None)
        skill_id = getattr(args, "skill_id", None)
        db_arg = getattr(args, "db", None)
        db_path = Path(db_arg) if db_arg else None
        skills_dir_arg = getattr(args, "skills_dir", None)
        skills_dir = Path(skills_dir_arg) if skills_dir_arg else None
        sys.exit(
            run_skills_cli(
                action=args.action,
                package_dir=package_dir,
                skill_id=skill_id,
                db_path=db_path,
                skills_dir=skills_dir,
            )
        )
    elif args.cmd == "memory":
        search = getattr(args, "search", "")
        limit = getattr(args, "limit", 20)
        status = getattr(args, "status", "PENDING")
        review_id = getattr(args, "review_id", None)
        approver = getattr(args, "approver", "operator")
        topic = getattr(args, "topic", None)
        db_arg = getattr(args, "db", None)
        db_path = Path(db_arg) if db_arg else None
        sys.exit(
            run_memory_cli(
                action=args.action,
                db_path=db_path,
                search=search,
                limit=limit,
                status=status,
                review_id=review_id,
                approver=approver,
                topic=topic,
            )
        )
    elif args.cmd in ("metrics", "router", "replay"):
        print("not implemented (tracked as F-CORE-027)")
        sys.exit(3)
    else:
        print(f"Unknown command '{args.cmd}'", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
