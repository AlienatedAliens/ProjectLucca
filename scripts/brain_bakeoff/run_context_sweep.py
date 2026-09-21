"""
Brain Bake-Off — Test #2: Long-context VRAM & needle-retrieval sweep.

For each context size, (re)starts the candidate's server, records whether it loads
under the VRAM clamp, resident VRAM, then fills ~70% of the window with filler prose
containing one needle and asks for it. Records prompt-processing TTFT and accuracy.

Answers: "how much headroom does each brain really have beyond 16k?"

Usage:
    python scripts/brain_bakeoff/run_context_sweep.py --candidate gemma4
    python scripts/brain_bakeoff/run_context_sweep.py --candidate bonsai2 --ctx 16384 32768 65536 131072
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from bakeoff_common import (
    Candidate,
    Defaults,
    ServerHandle,
    gpu_mem_used_mib,
    gpu_temp_c,
    load_registry,
    stream_chat,
    write_json,
)

NEEDLE = "The secret passphrase for the workshop door is amber-falcon-27."
QUESTION = (
    "Based only on the notes above, what is the secret passphrase for the workshop door? "
    "Reply with the passphrase only."
)
NEEDLE_ANSWER = "amber-falcon-27"
CHARS_PER_TOKEN_EST = 3.6

_SUBJECTS = [
    "The maintenance log",
    "A field technician",
    "The calibration routine",
    "Our supplier",
    "The overnight build",
    "The thermal camera",
    "A visiting engineer",
    "The backup script",
    "The oscilloscope",
    "The inventory system",
    "The lab assistant",
    "The firmware team",
]
_VERBS = [
    "recorded",
    "flagged",
    "recommended",
    "postponed",
    "verified",
    "misplaced",
    "recalibrated",
    "documented",
    "questioned",
    "approved",
    "archived",
    "measured",
]
_OBJECTS = [
    "the impedance sweep at 915 megahertz",
    "three replacement inductors",
    "the coolant loop",
    "a discrepancy in the checksum manifest",
    "the antenna reference plane",
    "the spare VNA cable",
    "the quarterly power budget",
    "the WSL memory clamp",
    "a mislabeled capacitor reel",
    "the second-stage filter",
    "the soak test results",
    "the display driver update",
]
_TAILS = [
    "before lunch.",
    "without further comment.",
    "pending review.",
    "as expected.",
    "late on Tuesday.",
    "after a brief outage.",
    "for the third time this month.",
    "despite the noise floor.",
    "with a note to revisit.",
    "and moved on.",
]


def make_filler(target_chars: int, seed: int, needle_frac: float = 0.4) -> str:
    rng = random.Random(seed)
    parts: list[str] = []
    n = 0
    while n < target_chars:
        s = f"{rng.choice(_SUBJECTS)} {rng.choice(_VERBS)} {rng.choice(_OBJECTS)} {rng.choice(_TAILS)}"
        parts.append(s)
        n += len(s) + 1
    idx = max(1, int(len(parts) * needle_frac))
    parts.insert(idx, NEEDLE)
    return " ".join(parts)


@dataclass
class CtxResult:
    ctx: int
    loaded: bool
    kv_type_used: str
    kv_fallback_applied: bool
    load_seconds: float | None
    vram_after_load_mib: int | None
    vram_peak_during_request_mib: int | None
    within_clamp: bool | None
    prompt_tokens: int | None
    fill_fraction: float | None
    ttft_speakable_ms: float | None
    total_ms: float | None
    needle_found: bool | None
    answer_preview: str
    http_status: int | None
    error: str | None
    gpu_temp_c_after: int | None


def run_one(cand: Candidate, d: Defaults, ctx: int, out_dir: Path) -> CtxResult:
    log = out_dir / f"server_ctx{ctx}.log"
    srv = ServerHandle(candidate=cand, defaults=d, ctx=ctx, kv_type=d.kv_type, log_path=log)
    ok = srv.start_with_kv_fallback(timeout_s=300.0)
    if not ok:
        res = CtxResult(
            ctx=ctx,
            loaded=False,
            kv_type_used=srv.kv_type,
            kv_fallback_applied=srv.kv_fallback_applied,
            load_seconds=None,
            vram_after_load_mib=None,
            vram_peak_during_request_mib=None,
            within_clamp=False,
            prompt_tokens=None,
            fill_fraction=None,
            ttft_speakable_ms=None,
            total_ms=None,
            needle_found=None,
            answer_preview="",
            http_status=None,
            error=f"LOAD_FAIL: {srv.error_tail[-600:]}",
            gpu_temp_c_after=gpu_temp_c(),
        )
        srv.stop()
        return res

    try:
        target_tokens = int(ctx * 0.70)
        filler = make_filler(int(target_tokens * CHARS_PER_TOKEN_EST), seed=ctx)
        messages = [
            {
                "role": "system",
                "content": "You are Lucca. Answer strictly from the provided notes.",
            },
            {"role": "user", "content": f"Workshop notes:\n\n{filler}\n\n{QUESTION}"},
        ]
        peak = srv.vram_after_load_mib or 0
        r = stream_chat(
            d.base_url,
            messages,
            chat_template_kwargs=cand.chat_template_kwargs(),
            max_tokens=32,
            temperature=0.0,
            timeout_s=900.0,
        )
        sample = gpu_mem_used_mib()
        if sample is not None:
            peak = max(peak, sample)
        found = NEEDLE_ANSWER in r.content.lower().replace(" ", "")
        frac = (r.prompt_tokens / ctx) if r.prompt_tokens else None
        return CtxResult(
            ctx=ctx,
            loaded=True,
            kv_type_used=srv.kv_type,
            kv_fallback_applied=srv.kv_fallback_applied,
            load_seconds=srv.load_seconds,
            vram_after_load_mib=srv.vram_after_load_mib,
            vram_peak_during_request_mib=peak,
            within_clamp=(peak <= d.vram_clamp_mib),
            prompt_tokens=r.prompt_tokens,
            fill_fraction=frac,
            ttft_speakable_ms=r.ttft_speakable_ms,
            total_ms=r.total_ms,
            needle_found=found,
            answer_preview=r.content[:120],
            http_status=r.http_status,
            error=r.error,
            gpu_temp_c_after=gpu_temp_c(),
        )
    finally:
        srv.stop()
        time.sleep(2.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--ctx", type=int, nargs="+", default=[16384, 32768, 65536, 131072])
    args = ap.parse_args()

    d, cands = load_registry()
    cand = cands[args.candidate]
    out_dir = d.out_dir / cand.label / "context_sweep"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"== Context sweep: {cand.label}  clamp={d.vram_clamp_mib} MiB  ctx={args.ctx}")
    results: list[CtxResult] = []
    for ctx in args.ctx:
        r = run_one(cand, d, ctx, out_dir)
        results.append(r)
        if r.loaded:
            print(
                f"  ctx={ctx:>6}  LOADED kv={r.kv_type_used}{'(fallback)' if r.kv_fallback_applied else ''}"
                f"  vram_load={r.vram_after_load_mib} peak={r.vram_peak_during_request_mib}"
                f"  clamp_ok={r.within_clamp}  prompt_tok={r.prompt_tokens}"
                f"  ttft={r.ttft_speakable_ms and round(r.ttft_speakable_ms)}ms"
                f"  needle={'HIT' if r.needle_found else 'MISS'}  -> {r.answer_preview!r}"
            )
        else:
            print(f"  ctx={ctx:>6}  LOAD_FAIL  {r.error[:160] if r.error else ''}")
        if not r.loaded:
            # Larger contexts will not load either; stop early to save time.
            print("  (stopping sweep: larger contexts will not fit)")
            break

    max_ok = max((r.ctx for r in results if r.loaded and r.within_clamp), default=None)
    summary = {
        "candidate": cand.label,
        "clamp_mib": d.vram_clamp_mib,
        "max_ctx_within_clamp": max_ok,
        "needle_hits": sum(1 for r in results if r.needle_found),
        "needle_tested": sum(1 for r in results if r.needle_found is not None),
    }
    write_json(
        out_dir / "context_sweep.json",
        {"summary": summary, "results": [asdict(r) for r in results]},
    )
    print("SUMMARY:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
