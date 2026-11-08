"""
Project Lucca — Brain Candidate Probe (Gate 2 + Gate 3)

Runs an identical tool-calling + latency battery against any OpenAI-compatible
llama-server on 127.0.0.1 and writes a JSON evidence report.

Mirrors the real request shape used by lucca.brain.llm_client (streaming,
tool_choice=auto, tools_in_user_message=False) and Lucca's actual sandbox tool
names so the result is representative of FULL_LOOP behaviour.

Usage:
    python scripts/probe_brain_candidate.py --name bonsai2-27b-pq2_0
    python scripts/probe_brain_candidate.py --name gemma4-12b-heretic-q6k --no-think
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

SYSTEM_PROMPT = (
    "You are Lucca, a concise desktop companion. When a user request requires an "
    "action, call the appropriate tool. Otherwise reply in one or two short sentences."
)

TOOLS: list[dict[str, object]] = [
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch a whitelisted desktop application by name.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string", "minLength": 1}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch the text content of a web page.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "minLength": 1}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for a query and return top results.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "minLength": 1}},
                "required": ["query"],
            },
        },
    },
]

# (case_id, user_text, expected_tool_names or [] for no-call)
CASES: list[tuple[str, str, list[str]]] = [
    ("single_launch", "Open the calculator for me.", ["launch_app"]),
    ("single_fetch", "What does the page at https://example.com say?", ["fetch_url"]),
    ("single_search", "Look up the current weather in Shanghai.", ["search_web"]),
    ("no_call_chat", "Hey Lucca, how are you feeling today?", []),
    ("no_call_knowledge", "What is the capital of France?", []),
    (
        "multi_call",
        "Open notepad and also search the web for today's top news.",
        ["launch_app", "search_web"],
    ),
]


INLINE_PREFIXES = ("[TOOL_CALLS]", "<|python_tag|>")


def parse_inline_tool_calls(content: str) -> list[str]:
    """
    Demux-equivalent (lucca.brain.toolcall_demux.ToolCallDemux) inline parse:
    returns tool names when the model emitted tool JSON as plain content.
    """
    s = content.strip()
    for p in INLINE_PREFIXES:
        s = s.replace(p, "")
    s = s.replace("[/TOOL_CALLS]", "").strip()
    if not s or s[0] not in "[{":
        return []
    try:
        obj: object = json.loads(s)
    except json.JSONDecodeError:
        return []
    items: list[object] = obj if isinstance(obj, list) else [obj]
    names: list[str] = []
    for it in items:
        if isinstance(it, dict) and "name" in it and ("arguments" in it or "parameters" in it):
            names.append(str(it["name"]))
    return names


@dataclass
class CaseResult:
    case_id: str
    expected_tools: list[str]
    got_tools: list[str]
    tool_args_valid_json: bool
    tool_match: bool
    inline_tools: list[str]
    tool_match_with_demux: bool
    finish_reason: str | None
    content_chars: int
    reasoning_chars: int
    content_has_think_tags: bool
    ttft_first_delta_ms: float | None
    ttft_speakable_ms: float | None
    total_ms: float
    completion_tokens: int | None
    http_status: int
    error: str | None = None
    content_preview: str = ""
    reasoning_preview: str = ""
    tool_calls_raw: list[dict[str, object]] = field(default_factory=list)


def run_case(
    client: httpx.Client,
    base_url: str,
    case_id: str,
    user_text: str,
    expected: list[str],
    *,
    no_think: bool,
    max_tokens: int,
    temperature: float,
) -> CaseResult:
    kwargs: dict[str, object] = {"tools_in_user_message": False}
    if no_think:
        kwargs["enable_thinking"] = False
    payload: dict[str, object] = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
        "chat_template_kwargs": kwargs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    t0 = time.perf_counter()
    ttft_first: float | None = None
    ttft_speak: float | None = None
    content = ""
    reasoning = ""
    finish: str | None = None
    completion_tokens: int | None = None
    tool_acc: dict[int, dict[str, str]] = {}
    status = 0
    err: str | None = None

    try:
        with client.stream("POST", f"{base_url}/v1/chat/completions", json=payload) as resp:
            status = resp.status_code
            if status != 200:
                err = resp.read().decode("utf-8", errors="replace")[:500]
            else:
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    usage = chunk.get("usage")
                    if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
                        completion_tokens = int(usage["completion_tokens"])
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    ch = choices[0]
                    delta = ch.get("delta") or {}
                    now = (time.perf_counter() - t0) * 1000.0
                    if ttft_first is None and (
                        delta.get("content")
                        or delta.get("reasoning_content")
                        or delta.get("tool_calls")
                    ):
                        ttft_first = now
                    rc = delta.get("reasoning_content")
                    if rc:
                        reasoning += rc
                    c = delta.get("content")
                    if c:
                        if ttft_speak is None:
                            ttft_speak = now
                        content += c
                    for tc in delta.get("tool_calls") or []:
                        idx = int(tc.get("index", 0))
                        slot = tool_acc.setdefault(idx, {"name": "", "arguments": ""})
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] += fn["name"]
                        if fn.get("arguments"):
                            slot["arguments"] += fn["arguments"]
                        if ttft_speak is None:
                            ttft_speak = now
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
    except httpx.HTTPError as e:
        err = f"{type(e).__name__}: {e}"

    total_ms = (time.perf_counter() - t0) * 1000.0
    got_tools = [tool_acc[i]["name"] for i in sorted(tool_acc)]
    args_ok = True
    raw_calls: list[dict[str, object]] = []
    for i in sorted(tool_acc):
        a = tool_acc[i]["arguments"]
        try:
            parsed: dict[str, object] = json.loads(a) if a else {}
            raw_calls.append({"name": tool_acc[i]["name"], "arguments": parsed})
        except json.JSONDecodeError:
            args_ok = False
            raw_calls.append({"name": tool_acc[i]["name"], "arguments_raw": a})

    think_tags = any(t in content for t in ("<think>", "<|channel>", "<channel|>", "thought"))
    inline: list[str] = parse_inline_tool_calls(content) if not got_tools else []
    effective = got_tools or inline
    return CaseResult(
        case_id=case_id,
        expected_tools=expected,
        got_tools=got_tools,
        tool_args_valid_json=args_ok,
        tool_match=sorted(got_tools) == sorted(expected),
        inline_tools=inline,
        tool_match_with_demux=sorted(effective) == sorted(expected),
        finish_reason=finish,
        content_chars=len(content),
        reasoning_chars=len(reasoning),
        content_has_think_tags=think_tags,
        ttft_first_delta_ms=ttft_first,
        ttft_speakable_ms=ttft_speak,
        total_ms=total_ms,
        completion_tokens=completion_tokens,
        http_status=status,
        error=err,
        content_preview=content[:300],
        reasoning_preview=reasoning[:300],
        tool_calls_raw=raw_calls,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="Candidate label for the report filename")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument(
        "--no-think", action="store_true", help="Send chat_template_kwargs.enable_thinking=false"
    )
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--out-dir", default=r"C:\ProjectLucca\logs\brain_eval")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=120.0)

    props: dict[str, object] = {}
    try:
        props = client.get(f"{args.base_url}/props").json()
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        print(f"WARN: /props failed: {e}", file=sys.stderr)

    results: list[CaseResult] = []
    for _ in range(args.repeats):
        for case_id, text, expected in CASES:
            r = run_case(
                client,
                args.base_url,
                case_id,
                text,
                expected,
                no_think=args.no_think,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
            results.append(r)
            # PASS  = structured tool_calls (or clean no-call) matched expectation
            # DMUX  = only matched after client-side inline JSON rescue (ToolCallDemux)
            # HALLU = no tool expected, but model emitted tool JSON (demux would execute it)
            # FAIL  = wrong/missing tools even after demux, or transport error
            if r.error is not None:
                flag = "FAIL"
            elif r.tool_match and r.tool_args_valid_json and not r.inline_tools:
                flag = "PASS"
            elif r.tool_match_with_demux:
                flag = "DMUX"
            elif not expected and r.inline_tools:
                flag = "HALLU"
            else:
                flag = "FAIL"
            ttft = f"{r.ttft_speakable_ms:.0f}" if r.ttft_speakable_ms is not None else "n/a"
            inl = f" inline={r.inline_tools}" if r.inline_tools else ""
            print(
                f"[{flag}] {case_id:<18} tools={r.got_tools}{inl} exp={expected} "
                f"reasoning={r.reasoning_chars}ch ttft_speak={ttft}ms total={r.total_ms:.0f}ms "
                f"tok={r.completion_tokens} finish={r.finish_reason}"
            )
            if r.error:
                print(f"       error: {r.error[:200]}")

    n = len(results)
    passes = sum(1 for r in results if r.tool_match and r.tool_args_valid_json and r.error is None)
    passes_demux = sum(1 for r in results if r.tool_match_with_demux and r.error is None)
    inline_count = sum(1 for r in results if r.inline_tools)
    ttfts = [r.ttft_speakable_ms for r in results if r.ttft_speakable_ms is not None]
    summary = {
        "candidate": args.name,
        "no_think": args.no_think,
        "cases": n,
        "tool_routing_pass_structured": passes,
        "tool_routing_pass_rate_structured": passes / n if n else 0.0,
        "tool_routing_pass_with_demux": passes_demux,
        "tool_routing_pass_rate_with_demux": passes_demux / n if n else 0.0,
        "inline_tool_json_in_content": inline_count,
        "ttft_speakable_median_ms": statistics.median(ttfts) if ttfts else None,
        "ttft_speakable_max_ms": max(ttfts) if ttfts else None,
        "total_median_ms": statistics.median(r.total_ms for r in results) if results else None,
        "reasoning_chars_median": statistics.median(r.reasoning_chars for r in results)
        if results
        else None,
        "any_think_tags_in_content": any(r.content_has_think_tags for r in results),
    }
    model_meta = {
        k: props.get(k)
        for k in (
            "model_path",
            "model_alias",
            "chat_template",
            "bos_token",
            "eos_token",
            "total_slots",
            "default_generation_settings",
        )
        if k in props
    }
    report = {"summary": summary, "model_meta": model_meta, "results": [asdict(r) for r in results]}
    suffix = "_nothink" if args.no_think else ""
    out = out_dir / f"{args.name}{suffix}_probe.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nSUMMARY:", json.dumps(summary, indent=2))
    print(f"report -> {out}")
    return 0 if passes_demux == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
