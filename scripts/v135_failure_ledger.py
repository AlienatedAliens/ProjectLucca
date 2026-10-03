"""v1.35 close-out: build a failure ledger (and optional paired diff) from benchmark checkpoints.

Reads a MATH-500 checkpoint JSON produced by ``scripts/run_modern_2024_benchmarks.py``
(a top-level JSON list of per-item records) and writes a Markdown ledger listing every
STRICT failure with an automatic triage hint and empty LABEL / NOTES columns for a human
or agent to fill in.

Optionally takes a baseline checkpoint and prints paired gains/losses (same ``idx``).

Usage (PowerShell, from repo root):

    .venv\\Scripts\\python.exe scripts/v135_failure_ledger.py `
        --checkpoint logs/test_reports/checkpoint_math500_v1.35-dev-400-v2.json `
        --baseline  logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json `
        --out       logs/test_reports/v135_failure_ledger.md

This script is READ-ONLY with respect to checkpoints. It never modifies benchmark data.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

Record = dict[str, object]

TIMEOUT_WINDOW_S = (15.0, 16.5)  # suspicious uniform T1 latencies observed in v1.35 logs
ALLOWED_LABELS = ("infra", "extraction", "grader", "library-misuse", "reasoning")


def _load(path: Path) -> list[Record]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("results", "items", "records"):
            inner = data.get(key)
            if isinstance(inner, list):
                data = inner
                break
    if not isinstance(data, list):
        raise SystemExit(f"{path}: expected a JSON list of records")
    out: list[Record] = []
    for rec in data:
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _s(rec: Record, key: str) -> str:
    val = rec.get(key)
    return "" if val is None else str(val)


def _b(rec: Record, key: str) -> bool:
    return bool(rec.get(key))


def _f(rec: Record, key: str) -> float:
    val = rec.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val))
    except (TypeError, ValueError):
        return -1.0


def _i(rec: Record, key: str) -> int:
    val = rec.get(key)
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    try:
        return int(str(val))
    except (TypeError, ValueError):
        return -1


_EXC_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt|Exit))\b")


def _exception_type(stderr: str) -> str:
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        m = _EXC_RE.match(line)
        if m:
            return m.group(1)
    return ""


def _hint(rec: Record) -> str:
    """Automatic triage hint. The human/agent still assigns the final LABEL."""
    fc = _s(rec, "failure_class")
    finish = _s(rec, "finish_reason")
    t1 = _f(rec, "turn1_latency_s")
    pred = _s(rec, "predicted_ans").strip()
    stderr = _s(rec, "stderr")
    strict = _b(rec, "strict_pass")
    lenient = _b(rec, "lenient_pass")

    hints: list[str] = []
    if finish == "length":
        hints.append("TRUNCATION(finish_reason=length) -> infra/extraction")
    if TIMEOUT_WINDOW_S[0] <= t1 <= TIMEOUT_WINDOW_S[1]:
        hints.append(f"TIMEOUT-SUSPECT(T1={t1:.2f}s in uniform window)")
    if not pred and fc != "runtime_crash":
        hints.append("EMPTY-OUTPUT -> infra/extraction")
    if "unexpected EOF" in stderr or "EOF" in stderr:
        hints.append("EOF-in-stderr -> infra")
    if (not strict) and lenient:
        hints.append("STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence)")
    if fc == "runtime_crash":
        exc = _exception_type(stderr)
        hints.append(f"CRASH:{exc or 'unknown'} -> library-misuse or infra")
        if _b(rec, "feedback_triggered") and not _b(rec, "feedback_succeeded"):
            hints.append("TURN2-DID-NOT-RECOVER (check if identical exception)")
    if fc == "prose_slip":
        hints.append("PROSE-SLIP -> extraction")
    if fc == "equivalence_format_miss":
        hints.append("FORMAT-MISS -> grader or reasoning (inspect)")
    if fc == "genuine_derivation_miss":
        hints.append("DERIVATION-MISS -> reasoning (NOT v1.35 scope)")
    return "; ".join(hints) if hints else "(no auto hint)"


def _md_escape(text: str, width: int = 60) -> str:
    text = text.replace("\n", " ").replace("|", "\\|").strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def _strict(rec: Record) -> bool:
    """Strict pass with fallback for pre-v1.35 checkpoints that only have ``passed``."""
    if "strict_pass" in rec:
        return _b(rec, "strict_pass")
    return _b(rec, "passed")


def build_ledger(records: list[Record], baseline: list[Record] | None, src: Path) -> str:
    lines: list[str] = []
    n = len(records)
    strict_pass = sum(1 for r in records if _strict(r))
    lenient_pass = sum(1 for r in records if _b(r, "lenient_pass"))
    failures = [r for r in records if not _strict(r)]

    lines.append(f"# v1.35 Failure Ledger — `{src.name}`\n")
    lines.append(f"- Items: **{n}**  | Strict pass: **{strict_pass}**  | Lenient pass: **{lenient_pass}**  | Strict failures listed below: **{len(failures)}**")
    fc_counts = Counter(_s(r, "failure_class") or "(strict-only fail)" for r in failures)
    lines.append("- Failure classes (strict failures): " + ", ".join(f"`{k}`={v}" for k, v in sorted(fc_counts.items())))
    finish_counts = Counter(_s(r, "finish_reason") or "(none)" for r in records)
    lines.append("- finish_reason over ALL items: " + ", ".join(f"`{k}`={v}" for k, v in sorted(finish_counts.items())))
    trunc = [r for r in records if _s(r, "finish_reason") == "length"]
    trunc_fail = [r for r in trunc if not _strict(r)]
    lines.append(f"- **TOKEN-CAP TRUNCATION**: `finish_reason=length` on **{len(trunc)}** items, of which **{len(trunc_fail)}** are strict failures "
                 f"(idx: {[_i(r, 'idx') for r in trunc_fail]}). These are the primary v1.35 'bullshit' losses: the model ran out of tokens.")
    tok_hi = sum(1 for r in records if _i(r, "completion_tokens") >= 750)
    lines.append(f"- completion_tokens >= 750 (at/near cap): **{tok_hi}** items")
    timeout_suspects = [r for r in records if TIMEOUT_WINDOW_S[0] <= _f(r, "turn1_latency_s") <= TIMEOUT_WINDOW_S[1]]
    lines.append(f"- T1 latency in {TIMEOUT_WINDOW_S[0]}–{TIMEOUT_WINDOW_S[1]} s (timeout-suspect window), ALL items: **{len(timeout_suspects)}** "
                 f"(idx: {', '.join(str(_i(r, 'idx')) for r in timeout_suspects[:40])}{' …' if len(timeout_suspects) > 40 else ''})")
    exc_counts = Counter(_exception_type(_s(r, "stderr")) or "unknown" for r in failures if _s(r, "failure_class") == "runtime_crash")
    if exc_counts:
        lines.append("- runtime_crash exception types: " + ", ".join(f"`{k}`={v}" for k, v in exc_counts.most_common()))
    lines.append("")

    if baseline is not None:
        base_by_idx = {_i(r, "idx"): r for r in baseline}
        base_has_strict = any("strict_pass" in r for r in baseline)
        gains: list[int] = []
        losses: list[int] = []
        losses_invariant: list[int] = []  # baseline Turn 1 finished with `stop` -> should be bit-identical
        losses_expected: list[int] = []   # baseline Turn 1 hit `length` -> Turn-2 rescue path changed; expected noise
        for r in records:
            idx = _i(r, "idx")
            b = base_by_idx.get(idx)
            if b is None:
                continue
            cur, prev = _strict(r), _strict(b)
            if cur and not prev:
                gains.append(idx)
            elif prev and not cur:
                losses.append(idx)
                if _s(b, "finish_reason") == "length" or _b(b, "feedback_triggered"):
                    losses_expected.append(idx)
                else:
                    losses_invariant.append(idx)
        lines.append("## Paired comparison vs baseline (STRICT, same idx)\n")
        if not base_has_strict:
            lines.append("> NOTE: baseline checkpoint has no `strict_pass` field (pre-v1.35 grader); its `passed` field was used instead. "
                         "If `passed` followed the lenient grader, this comparison is lenient-vs-strict and understates gains. "
                         "Prefer a baseline regraded under v1.35-dual.\n")
        lines.append(f"- Gains (baseline FAIL → current PASS): **{len(gains)}**  idx: {gains}")
        lines.append(f"- Losses (baseline PASS → current FAIL): **{len(losses)}**  idx: {losses}")
        lines.append(f"  - **INVARIANT losses** (baseline finished `stop`, no Turn 2 — output should have been bit-identical): **{len(losses_invariant)}**  idx: {losses_invariant}")
        lines.append(f"  - Expected losses (baseline hit `length` or used Turn 2 — rescue path legitimately changed): **{len(losses_expected)}**  idx: {losses_expected}")
        lines.append(f"- Net: **{len(gains) - len(losses):+d}**  (churn = gains + losses = {len(gains) + len(losses)})")
        lines.append("")
        verdict = "ACCEPT" if not losses_invariant else "STOP"
        lines.append(f"> **Gate verdict: {verdict}.** Rule: a *budget/mechanism* change is accepted iff INVARIANT losses == 0. "
                     "Expected losses are labeled in the table below (usually `reasoning` loop or `grader`), not rationalised away. "
                     "For a *feedback-content* change (Fix B), apply the rule to total losses instead.\n")

    lines.append("## Strict failures — fill LABEL with exactly one of: " + " / ".join(f"`{l}`" for l in ALLOWED_LABELS) + "\n")
    lines.append("v1.35 scope = `infra`, `extraction`, `grader`, and `library-misuse` fixed ONLY via feedback-governor traceback content. `reasoning` is out of scope — leave it.\n")
    header = "| idx | class | S/L | exit | finish | tok | T1 s | T2 s | fb trig/ok | stage | exception / stderr head | pred | expected | AUTO HINT | LABEL | NOTES |"
    sep = "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)
    for r in sorted(failures, key=lambda x: _i(x, "idx")):
        stderr = _s(r, "stderr").strip()
        exc = _exception_type(stderr)
        stderr_head = exc or (stderr.splitlines()[-1] if stderr else "")
        row = [
            str(_i(r, "idx")),
            _s(r, "failure_class") or "(strict-only)",
            f"{'Y' if _b(r, 'strict_pass') else 'N'}/{'Y' if _b(r, 'lenient_pass') else 'N'}",
            str(_i(r, "exit_code")),
            _s(r, "finish_reason") or "-",
            str(_i(r, "completion_tokens")),
            f"{_f(r, 'turn1_latency_s'):.1f}",
            f"{_f(r, 'turn2_latency_s'):.1f}" if _f(r, "turn2_latency_s") >= 0 else "-",
            f"{'Y' if _b(r, 'feedback_triggered') else 'N'}/{'Y' if _b(r, 'feedback_succeeded') else 'N'}",
            _s(r, "extraction_stage") or "-",
            _md_escape(stderr_head, 50),
            _md_escape(_s(r, "predicted_ans"), 24),
            _md_escape(_s(r, "expected_ans"), 24),
            _md_escape(_hint(r), 90),
            "",
            "",
        ]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Label counts (fill after labeling)\n")
    for lab in ALLOWED_LABELS:
        lines.append(f"- `{lab}`: ")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", required=True, type=Path, help="Current checkpoint JSON (list of records)")
    ap.add_argument("--baseline", type=Path, default=None, help="Optional baseline checkpoint for paired gains/losses")
    ap.add_argument("--out", type=Path, default=Path("logs/test_reports/v135_failure_ledger.md"))
    args = ap.parse_args(argv)

    records = _load(args.checkpoint)
    baseline = _load(args.baseline) if args.baseline else None
    md = build_ledger(records, baseline, args.checkpoint)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    # Print summary (everything above the table) to stdout for quick inspection.
    # Windows consoles often default to cp1252; keep stdout ASCII-safe.
    summary = md.split("## Strict failures")[0]
    print(summary.encode("ascii", "replace").decode("ascii"))
    print(f"\nLedger written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
