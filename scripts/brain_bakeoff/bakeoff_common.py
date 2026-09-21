"""
Project Lucca — Brain Bake-Off shared harness.

Loads config/brain_candidates.toml, manages exactly one llama-server at a time
(start / health-wait / VRAM sample / stop, with a single KV-quant fallback), and
provides a streaming chat helper that mirrors lucca.brain.llm_client's payload.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "brain_candidates.toml"


@dataclass(frozen=True)
class Defaults:
    host: str
    port: int
    ctx: int
    kv_type: str
    vram_clamp_mib: int
    out_dir: Path
    stock_server: Path
    prism_server: Path

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    gguf: Path
    server_bin: Path
    extra_args: list[str]
    thinking: str  # "off" | "on" | "n/a"
    abliterated: bool
    vendor_markers: list[str]

    def chat_template_kwargs(self) -> dict[str, bool]:
        kw: dict[str, bool] = {"tools_in_user_message": False}
        if self.thinking == "off":
            kw["enable_thinking"] = False
        elif self.thinking == "on":
            kw["enable_thinking"] = True
        return kw

    def runtime_env(self) -> dict[str, str]:
        """Env overrides so lucca.brain.llm_client behaves like this candidate."""
        env = dict(os.environ)
        if self.thinking == "off":
            env["LUCCA_LLM__ENABLE_THINKING"] = "false"
        elif self.thinking == "on":
            env["LUCCA_LLM__ENABLE_THINKING"] = "true"
        else:
            env.pop("LUCCA_LLM__ENABLE_THINKING", None)
        return env


def load_registry(path: Path = REGISTRY_PATH) -> tuple[Defaults, dict[str, Candidate]]:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    d = raw["defaults"]
    defaults = Defaults(
        host=str(d["host"]),
        port=int(d["port"]),
        ctx=int(d["ctx"]),
        kv_type=str(d["kv_type"]),
        vram_clamp_mib=int(d["vram_clamp_mib"]),
        out_dir=Path(str(d["out_dir"])),
        stock_server=Path(str(d["stock_server"])),
        prism_server=Path(str(d["prism_server"])),
    )
    cands: dict[str, Candidate] = {}
    for key, c in raw["candidates"].items():
        server_sel = str(c["server"])
        server_bin = defaults.stock_server if server_sel == "stock" else defaults.prism_server
        cands[key] = Candidate(
            key=key,
            label=str(c["label"]),
            gguf=Path(str(c["gguf"])),
            server_bin=server_bin,
            extra_args=[str(a) for a in c.get("extra_args", [])],
            thinking=str(c.get("thinking", "n/a")),
            abliterated=bool(c.get("abliterated", False)),
            vendor_markers=[str(m) for m in c.get("vendor_markers", [])],
        )
    return defaults, cands


# --------------------------------------------------------------------------- GPU


def gpu_mem_used_mib() -> int | None:
    try:
        out = subprocess.run(  # noqa: S603
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return int(out.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def gpu_temp_c() -> int | None:
    try:
        out = subprocess.run(  # noqa: S603
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return int(out.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def kill_all_llama_servers() -> None:
    subprocess.run(  # noqa: S603
        ["taskkill", "/F", "/IM", "llama-server.exe", "/T"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    time.sleep(2.0)


# ------------------------------------------------------------------------ Server


@dataclass
class ServerHandle:
    candidate: Candidate
    defaults: Defaults
    ctx: int
    kv_type: str
    log_path: Path
    proc: subprocess.Popen[bytes] | None = None
    loaded: bool = False
    load_seconds: float | None = None
    vram_after_load_mib: int | None = None
    kv_fallback_applied: bool = False
    error_tail: str = ""
    cmd: list[str] = field(default_factory=list)

    def _build_cmd(self) -> list[str]:
        c, d = self.candidate, self.defaults
        cmd = [
            str(c.server_bin),
            "--model",
            str(c.gguf),
            "--n-gpu-layers",
            "99",
            "--ctx-size",
            str(self.ctx),
            "--flash-attn",
            "on",
            "--jinja",
            "--host",
            d.host,
            "--port",
            str(d.port),
            "--no-webui",
        ]
        if self.kv_type != "f16":
            cmd += ["--cache-type-k", self.kv_type, "--cache-type-v", self.kv_type]
        cmd += c.extra_args
        return cmd

    def start(self, timeout_s: float = 240.0) -> bool:
        kill_all_llama_servers()
        self.cmd = self._build_cmd()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        with open(self.log_path, "wb") as log:
            self.proc = subprocess.Popen(self.cmd, stdout=log, stderr=subprocess.STDOUT)  # noqa: S603
        url = f"{self.defaults.base_url}/health"
        deadline = t0 + timeout_s
        while time.perf_counter() < deadline:
            if self.proc.poll() is not None:
                self.error_tail = self._tail()
                return False
            try:
                r = httpx.get(url, timeout=2.0)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    self.loaded = True
                    self.load_seconds = time.perf_counter() - t0
                    time.sleep(1.5)
                    self.vram_after_load_mib = gpu_mem_used_mib()
                    return True
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(1.0)
        self.error_tail = self._tail()
        self.stop()
        return False

    def start_with_kv_fallback(self, timeout_s: float = 240.0) -> bool:
        if self.start(timeout_s):
            return True
        if self.kv_type != "f16":
            first_err = self.error_tail
            self.kv_type = "f16"
            self.kv_fallback_applied = True
            if self.start(timeout_s):
                self.error_tail = f"[q8_0 attempt failed]\n{first_err}"
                return True
        return False

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        kill_all_llama_servers()
        self.loaded = False

    def _tail(self, n: int = 12) -> str:
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-n:])
        except OSError:
            return ""

    def props(self) -> dict[str, object]:
        try:
            r = httpx.get(f"{self.defaults.base_url}/props", timeout=5.0)
            data: dict[str, object] = r.json()
            return data
        except (httpx.HTTPError, ValueError):
            return {}


# ---------------------------------------------------------------------- Streaming


@dataclass
class StreamResult:
    content: str
    reasoning: str
    tool_calls: list[dict[str, object]]
    finish_reason: str | None
    ttft_first_ms: float | None
    ttft_speakable_ms: float | None
    total_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    http_status: int
    error: str | None


def stream_chat(
    base_url: str,
    messages: list[dict[str, str]],
    *,
    chat_template_kwargs: dict[str, bool],
    tools: list[dict[str, object]] | None = None,
    max_tokens: int = 512,
    temperature: float = 0.6,
    timeout_s: float = 600.0,
) -> StreamResult:
    payload: dict[str, object] = {
        "messages": messages,
        "chat_template_kwargs": chat_template_kwargs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    t0 = time.perf_counter()
    content, reasoning = "", ""
    ttft_first: float | None = None
    ttft_speak: float | None = None
    finish: str | None = None
    p_tok: int | None = None
    c_tok: int | None = None
    acc: dict[int, dict[str, str]] = {}
    status = 0
    err: str | None = None

    try:
        with (
            httpx.Client(timeout=timeout_s) as client,
            client.stream("POST", f"{base_url}/v1/chat/completions", json=payload) as resp,
        ):
            status = resp.status_code
            if status != 200:
                err = resp.read().decode("utf-8", errors="replace")[:600]
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
                    if isinstance(usage, dict):
                        if usage.get("prompt_tokens") is not None:
                            p_tok = int(usage["prompt_tokens"])
                        if usage.get("completion_tokens") is not None:
                            c_tok = int(usage["completion_tokens"])
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
                        slot = acc.setdefault(idx, {"name": "", "arguments": ""})
                        fn = tc.get("function") or {}
                        slot["name"] += fn.get("name") or ""
                        slot["arguments"] += fn.get("arguments") or ""
                        if ttft_speak is None:
                            ttft_speak = now
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
    except httpx.HTTPError as e:
        err = f"{type(e).__name__}: {e}"

    calls: list[dict[str, object]] = []
    for i in sorted(acc):
        a = acc[i]["arguments"]
        try:
            parsed: object = json.loads(a) if a else {}
        except json.JSONDecodeError:
            parsed = {"__raw__": a}
        calls.append({"name": acc[i]["name"], "arguments": parsed})

    return StreamResult(
        content=content,
        reasoning=reasoning,
        tool_calls=calls,
        finish_reason=finish,
        ttft_first_ms=ttft_first,
        ttft_speakable_ms=ttft_speak,
        total_ms=(time.perf_counter() - t0) * 1000.0,
        prompt_tokens=p_tok,
        completion_tokens=c_tok,
        http_status=status,
        error=err,
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
