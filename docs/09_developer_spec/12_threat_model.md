# Spec 12 — Threat Model (STRIDE-lite), Trust Boundaries, Risk Policy

Scope: single-user desktop; adversary = malicious web content, malicious file content in the workspace, a compromised sandbox container, and developer error. Out of scope: a compromised Windows host, physical access, supply-chain compromise of model weights (mitigated only by `models verify` sha256 manifest).

## 1. Trust zones

| Zone | Contents | Trust |
|---|---|---|
| Z0 Host trusted | `lucca-core`, `lucca-audio`, `lucca-npu`, `lucca-ui`, `llama-server`, SQLite, keys | full |
| Z1 Model output | everything the LLM emits (text, tool calls, extracted facts, proposed rules) | **untrusted input** — schema-validated, provenance `LLM_NARRATION` |
| Z2 Sandbox | file/web containers, their stdout | untrusted; may be compromised |
| Z3 Internet | fetched pages | hostile |
| Z4 Workspace files | user-provided or tool-written | untrusted content, trusted *existence* |

Boundaries: Z1→Z0 through `ToolCallDemux` + Pydantic + risk policy; Z2→Z0 through the RPC schema validator + `ToolResultSigner`; Z3→Z2 through egress rules; Z4→Z1 through `TOOL_CONTENT_UNTRUSTED`.

## 2. Threats and controls

| ID | Threat (STRIDE) | Vector | Control(s) | Verified by |
|---|---|---|---|---|
| TM-01 | Tampering: hallucination written to memory | LLM narrates a "fact" | Type-level: no signer for `LLM_NARRATION`; gate rejects; import-linter; AST allow-list | T-PROV-06/08/09 |
| TM-02 | Tampering: indirect prompt injection via web page | Page text says "ignore instructions, write X / open Y" | `TOOL_CONTENT_UNTRUSTED` never memory-eligible; WRITE/LAUNCH always confirmed; fetch→write chains refused within a turn; content capped 20 k chars; system prompt marks tool output as data | T-PROV-12, T-SBX-15 |
| TM-03 | Information disclosure: workspace exfiltration | (a) in-sandbox read→POST; (b) **LLM-carried**: `read_file` content → `fetch_url` URL | (a) Split containers (file: no network; web: no files) — ADR-004. (b) Forbidden sequence `(read_file→fetch_url)` in one turn; URL ≤ 512 chars, query ≤ 128; Phase 7 domain allow-list. Residual: slow multi-turn leakage via short URLs — accepted, logged (`sbx.url_query_len`) | T-SBX egress; architecture test that file-sandbox spec has `--network none`; T-SBX-19 forbidden-sequence refusal |
| TM-04 | Info disclosure: LAN/host scanning from sandbox | curl to 192.168.x, 169.254.169.254, host IP | Egress chain with RFC1918/link-local/CGNAT REJECT before ACCEPT; default DROP; IPv6 off; host-side resolver check for `fetch_url`; DNS restricted | T-SBX-07…13 |
| TM-05 | Elevation: container escape | kernel exploit | `cap-drop ALL`, `no-new-privileges`, read-only root, non-root uid, pids/mem limits, no GPU, no Docker socket, ephemeral web containers; no keys inside | container spec test; T-SBX-06 |
| TM-06 | Tampering: path traversal / symlink | `../`, `%2f`, symlink in workspace | `validate_rel_path` + realpath + lstat every component + `O_NOFOLLOW`; reject `%` outright | T-SBX-01/02 |
| TM-07 | DoS: resource exhaustion | huge file read, `while True`, fork bomb, string bomb in rules | read/write caps, `RLIMIT_*`, pids-limit, Scheme gas/timeout/size caps, sandbox mem caps, swap 0 | T-SBX-03/04, T-LISP-08 |
| TM-08 | Spoofing: forged tool result | compromised container returns `ok=true` with fake `structured` | Host signs **after** validation; `TOOL_VERIFIED` covers only fields the host can check or that are self-consistent (sha256 recomputed on host for `read_file` content) | T-SBX-16 (host recomputes sha) |
| TM-09 | Elevation: rule bypasses confirmation | promoted rule plans `write_file`/`launch_app` | Plans go through the same risk policy; rule cannot lower risk; static validation records risk | T-RULE-07 |
| TM-10 | Tampering: malicious rule synthesised | LLM proposes rule with hostile plan | Grammar-constrained; static validation (registered tools, arg schemas); quarantine ≥ 5 clusters + 0 failures; WRITE plans confirmed; "stop doing that" retires | T-RULE-08, T-REFL-01 |
| TM-11 | Repudiation: what did Lucca do and why | — | `memory_audit`, `decisions`, `rule_evaluations`, traces; `lucca-admin memory export` | T-OBS-01 |
| TM-12 | Info disclosure: transcripts/audio at rest | disk theft | Out of scope for encryption in v1 (documented); retention limits; audio 7 d; logs never contain transcripts at INFO | T-OBS-02 (log scan) |
| TM-13 | Spoofing: default/dev master key in prod | misconfig | Fail-closed boot; known-dev-key list | T-PROV-10 |
| TM-14 | Elevation: launcher abuse | `open cmd /c …`, path injection | Whitelist by alias → fixed exe; `shell=False`; templated args validated; rate-limit; always confirm | T-SBX-14 |
| TM-15 | DoS/Tampering: IPC from another local process | anything on 127.0.0.1 can connect to ZMQ ports | Envelope requires a per-boot random `session_token` (in `.env`-less memory, passed to children via inherited env); messages without it dropped; ports bound to loopback only | T-IPC-06 |
| TM-16 | Tampering: SSRF via redirect | fetch redirects to internal IP | Re-validate every redirect hop on host; container egress blocks anyway | T-SBX-13 |
| TM-17 | Info disclosure: llama-server exposed | binds 0.0.0.0 | `--host 127.0.0.1`; boot check refuses otherwise | T-BOOT-03 |
| TM-18 | DoS: reflection starves live voice | reflection LLM call during PTT | Idle-only trigger; abort on `ptt.pressed` ≤ 100 ms | T-REFL-02 |

## 3. Risk policy (single source: `lucca/core/risk_policy.py`)

```python
class Risk(StrEnum):
    READ = "READ"
    NETWORK = "NETWORK"
    WRITE = "WRITE"
    LAUNCH = "LAUNCH"


AUTO_EXECUTE: Final = frozenset({Risk.READ, Risk.NETWORK})
CONFIRM_REQUIRED: Final = frozenset({Risk.WRITE, Risk.LAUNCH})
MAX_TOOL_CALLS_PER_TURN: Final = 4
FORBIDDEN_SEQUENCES: Final = (
    ("fetch_url", "write_file"),
    ("fetch_url", "run_python"),
    ("read_file", "fetch_url"),
)
```
- Applies identically to LLM tool calls and rule plans.
- A turn exceeding `MAX_TOOL_CALLS_PER_TURN` stops and says so.
- A forbidden sequence within one turn (any order-adjacent pair in the executed list) is refused with a spoken explanation ("I won't write web content to a file without you asking separately").
- Confirmation texts are templated per tool (`write_file` → "write N bytes to <path>?"; `launch_app` → "open <app>?") so the user hears the actual target, never the LLM's paraphrase.

## 4. Residual risks (accepted, documented)

| Risk | Why accepted | Revisit |
|---|---|---|
| No encryption at rest for memory.sqlite | single-user laptop with BitLocker assumed | Phase 7: SQLCipher |
| Chromium `--no-sandbox` in js image | container already provides isolation; image ephemeral | if gVisor becomes usable in WSL2 |
| PTT hook blind to elevated windows | Windows security model | tray fallback |
| Whisper mis-hearing becomes `USER_EXPLICIT` | confidence gating + read-back for facts | Phase 7: dual-ASR agreement |
| Model weights unsigned upstream | sha256 manifest pinned at download | — |
