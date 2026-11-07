#!/usr/bin/env python3
"""Phase 2.3: regenerate the RESULTS.md ledger from artifacts.

Parses the ledger table in RESULTS.md, loads each row's artifact, recomputes
passed/total and a single Wilson variant from per-item data where available
(else the artifact's own summary block), and diffs stated vs recomputed.
Writes logs/test_reports/regenerated_ledger.md. Does NOT edit RESULTS.md
(Phase 4 does document repair)."""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "RESULTS.md"
OUT = ROOT / "logs" / "test_reports" / "regenerated_ledger.md"


def wilson(p: float, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    phat = p / 100.0
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (100 * (center - half), 100 * (center + half))


def load_summary(artifact: str) -> dict[str, object]:
    """Extract (total, passed_strict, passed_lenient, git_commit) from an
    artifact, handling the known shapes."""
    p = ROOT / artifact
    if not p.exists():
        return {"error": "artifact missing"}
    d = json.load(open(p, encoding="utf-8"))
    out: dict[str, object] = {}

    def commit_from(dd: dict) -> object:
        return dd.get("git_commit")

    # Shape B: top-level list of items
    if isinstance(d, list) and d and isinstance(d[0], dict):
        n = len(d)
        has_strict = any("strict_pass" in it for it in d)
        strict = sum(1 for it in d if it.get("strict_pass") is True) if has_strict else sum(
            1 for it in d if it.get("passed") is True)
        lenient = sum(1 for it in d if it.get("lenient_pass") is True) if any(
            "lenient_pass" in it for it in d) else strict
        out.update(total=n, passed_strict=strict, passed_lenient=lenient,
                   source="per-item strict_pass" if has_strict else "per-item passed (pre-v1.35 grader; no strict_pass field)")
        return out

    # Shape A: nested benchmarks.{name}
    benches = d.get("benchmarks") if isinstance(d, dict) else None
    if isinstance(benches, dict):
        for name, v in benches.items():
            if isinstance(v, dict) and "passed" in v and "total" in v:
                out.update(total=v["total"], passed_strict=v["passed"],
                           source=f"benchmarks.{name} summary",
                           git_commit=commit_from(d))
                return out

    # Shape C: top-level passed/total
    if isinstance(d, dict) and "passed" in d and "total" in d:
        out.update(total=d["total"], passed_strict=d["passed"],
                   source="top-level summary", git_commit=commit_from(d))
        return out

    # Shape D: pal_off summary dict with strict_passed/lenient_passed
    if isinstance(d, dict) and "strict_passed" in d:
        tot = d.get("samples") or len(d.get("results", []))
        out.update(total=tot, passed_strict=d.get("strict_passed"),
                   passed_lenient=d.get("lenient_passed"),
                   source="pal_off summary block", git_commit=commit_from(d))
        return out

    return {"error": "unrecognized artifact shape", "keys": sorted(d)[:12] if isinstance(d, dict) else type(d).__name__}


def main() -> int:
    rows = []
    for line in RESULTS.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 11:
            continue
        rows.append(cells)

    report = ["# Regenerated ledger (Phase 2.3) — stated vs recomputed", "",
              "Wilson variant: plain (no continuity correction), 95%. Single function for all rows.", ""]
    mismatches = 0
    for cells in rows:
        cells = [c.strip("`") for c in cells]
        label, commit, protocol, dataset, dshash, n_s, passed_s, strict_s, lenient_s, ci_s, artifact = cells[:11]
        summ = load_summary(artifact)
        line_out = [f"## {label}", f"- artifact: `{artifact}`"]
        if "error" in summ:
            line_out.append(f"- **ERROR: {summ['error']}**")
            mismatches += 1
        else:
            recom_total = summ.get("total")
            recom_strict = summ.get("passed_strict")
            src = summ.get("source")
            lo, hi = wilson(100.0 * recom_strict / recom_total, recom_total) if recom_total else (0, 0)
            # stated: parse passed_s "94.00% (94/100)" or bare "94" (total from n_s)
            m = re.search(r"\((\d+)/(\d+)\)", passed_s)
            if m:
                stated_passed, stated_total = int(m.group(1)), int(m.group(2))
            else:
                try:
                    stated_passed, stated_total = int(passed_s), int(n_s)
                except ValueError:
                    stated_passed, stated_total = None, None
            ok = (stated_passed == recom_strict and stated_total == recom_total)
            if not ok:
                mismatches += 1
            art_commit = str(summ.get("git_commit", ""))[:8]
            commit_ok = (not commit or not art_commit or commit.startswith(art_commit) or art_commit.startswith(commit))
            if not commit_ok:
                mismatches += 1
            line_out += [
                f"- stated: passed={passed_s} | strict%={strict_s} | lenient%={lenient_s} | CI={ci_s} | commit=`{commit}`",
                f"- recomputed: passed={recom_strict}/{recom_total} | Wilson plain CI=[{lo:.2f}%, {hi:.2f}%] | source={src} | artifact commit=`{art_commit}`",
                f"- match: {'YES' if ok else '**NO**'} | commit match: {'YES' if commit_ok else '**NO**'}",
            ]
        report.append("\n".join(line_out))
        report.append("")

    report.insert(2, f"**Rows: {len(rows)} | mismatches: {mismatches}**")
    report.insert(3, "")
    OUT.write_text("\n".join(report), encoding="utf-8")
    print(f"rows: {len(rows)} | mismatches: {mismatches}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
