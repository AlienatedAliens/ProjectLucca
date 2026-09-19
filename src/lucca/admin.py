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
from lucca.reasoning.lifecycle import RuleLifecycleManager
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
) -> int:
    """Manages MicroScheme rules and human approval gates via CLI."""
    if db_path is None:
        config = get_config()
        db_path = config.resolve_path("data") / "memory.sqlite"

    db = DatabaseManager(db_path=db_path)
    db.migrate()
    manager = RuleLifecycleManager(db=db)

    console = Console()

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

    console.print(f"[red]Unknown rules action: {action}[/red]")
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

    # Stubs per F-CORE-027
    for stub in ["metrics", "memory", "router", "replay"]:
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
        approver = getattr(args, "approver", "operator")
        db_arg = getattr(args, "db", None)
        db_path = Path(db_arg) if db_arg else None
        sys.exit(
            run_rules_cli(action=args.action, rule_id=rule_id, approver=approver, db_path=db_path)
        )
    elif args.cmd in ("metrics", "memory", "router", "replay"):
        print("not implemented (tracked as F-CORE-027)")
        sys.exit(3)
    else:
        print(f"Unknown command '{args.cmd}'", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
