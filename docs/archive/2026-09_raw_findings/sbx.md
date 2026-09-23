# Findings — SBX (`src/lucca/sandbox/**`, `docker/**`, `scripts/wsl/**`)

**Subtask:** S2f · **Method:** static line-by-line + S1 dynamic evidence · **Baseline:** HEAD `ed14f6b` + working tree per `03_BASELINE.md`, delta in [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) (sandbox modules: **unchanged since S0**) · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; every finding cites `file:line` in the current tree or an artefact under `docs/audit/evidence/`. Cross-area findings cross-referenced by ID.

**Severity totals: S0 = 0 · S1 = 1 · S2 = 4 · S3 = 9 · S4 = 1 · total = 15.**

---

## 1. Module map

Coverage from `docs/audit/evidence/S1_14_coverage.txt` rows 53–62. LOC = non-blank lines (S0 metric, verified unchanged by `03b_BASELINE_DELTA.md`).

| File | LOC | Public symbols | Responsibilities (as-built) | Live callers in product path? | Outbound dependencies | Cov % | Tests |
|---|---:|---|---|---|---|---:|---|
| `sandbox/file_tool.py` | 315 | `validate_rel_path`, `SafeFileTool` (`list_dir`, `read_file`, `write_file`, `delete_file`, `search_text`, `run_python`, `read_codebase_file`) | Path validation (traversal/symlink/reserved/`%`/`\`), capped file ops, binary sniff, host `run_python` with POSIX-only rlimits | **yes** — direct fallback (`rpc.py:199`) and container side (`toolsrv`) | `subprocess`, `core.exceptions` | 68 % | `tests/test_sandbox.py` |
| `sandbox/web_tool.py` | 166 | `validate_url_ssrf`, `extract_readable_text`, `fetch_url` | SSRF URL validation (resolve + private-range reject, IPv6 reject), redirect re-validation, content-type allow-list, trafilatura/regex extraction | **yes** — `service.py:124` runs it **host-side** (F-SBX-002) | `httpx`, `socket`, `ipaddress` | 44 % | `tests/test_sandbox.py` (partial) |
| `sandbox/rpc.py` | 289 | `DockerRPCTransport` (`is_docker_available`, `execute`, `_execute_direct`) | `wsl docker exec -i lucca-file-sandbox lucca-toolsrv` JSON-over-stdio; sha256 audit on `read_file` (T-SBX-16); **direct host fallback** | **yes** — `service.py:42-46` with `use_direct_fallback=True` default | `subprocess`, `hashlib` | 56 % | `tests/test_sandbox.py` |
| `sandbox/service.py` | 200 | `SandboxService` (`reset_turn`, `execute_tool`, `check_confirmation_needed`, `get_tool_risk`) | Unified entry: SequenceGuard → confirmation gate → host launcher / host web fetch / RPC file tools / `query_capabilities` | **yes** — `orchestrator.py:650,664` | `rpc`, `web_tool`, `launcher`, `policy`, `workspace` | 76 % | `tests/test_sandbox.py`, `test_confirmation.py` |
| `sandbox/policy.py` | 77 | `TOOL_RISK_MAP`, `classify_risk`, `requires_confirmation`, `parse_confirmation_response`, `SequenceGuard` | Risk classification (unknown → WRITE), confirmation matcher, forbidden-sequence guard | **yes** — `service.py:16,76,88` | `core.schemas` | **100 %** | `tests/test_sandbox.py` |
| `sandbox/launcher.py` | 206 | `AppLauncher` (`find_app_entry`, `check_rate_limit`, `launch`) | Whitelist (TOML or defaults), rate limit (3/min, 5 s spacing), `shell=False` Popen with templated args, single-instance focus | **yes** — `service.py:104` | `psutil`, `ctypes`, `file_tool`, `web_tool` | 58 % | `tests/test_sandbox.py` |
| `sandbox/workspace.py` | 102 | `WorkspaceManager` (`reset_workspace`, `import_from_inbox`, `get_total_size`, `check_size_limit`) | Workspace lifecycle under `LUCCA_HOME/workspace`; inbox import; 1 GiB cap (declared) | **yes** — `service.py:40` | `core.config` | 66 % | `tests/test_sandbox.py` |
| `sandbox/container_spec.py` | 101 | `win_to_wsl_path`, `get_file_sandbox_run_args`, `get_web_sandbox_run_args` | Normative `docker run` arg rendering (network none / lucca-net, read-only, cap-drop, limits) | **NO — zero call sites in `src/`** (F-SBX-002) | — | 93 % | `tests/test_sandbox.py` (arg-shape only) |
| `sandbox/egress.py` | 172 | `get_local_lan_ip`, `EgressVerifier` (`apply_rules`, `verify_all`) | Applies `lucca-egress.sh` as WSL root; 4-check verification matrix (docstring claims 6) | **no** — no caller in `src/` (`lucca-admin sandbox verify` is not implemented, S1_32) | `subprocess`, `http.server` | 23 % | none live |
| `sandbox/system_tools.py` | 224 | `query_nvidia_gpu_metrics`, `get_lucca_process_footprint`, `get_system_metrics`, `list_running_processes`, `SessionTelemetryLogger` | Read-only host telemetry; hard-coded NPU/iGPU status strings; JSONL session logger | **yes** — `ui/telemetry_hud.py:37,53`, `ui/settings_dialog.py:70,2103` | `psutil`, `subprocess` | **18 %** | none |
| `docker/toolsrv/server.py` | 177 | `run_server` | Single-shot JSON RPC over stdin/stdout inside the container; dispatches 6 file tools via `SafeFileTool("/workspace")` | runs inside `lucca-file-sandbox` image only (never started by code, F-SBX-002) | `file_tool` | 0 % (container) | via rpc tests |
| `docker/*/Dockerfile` | 19 | — | file-sandbox / web-sandbox images | built manually | — | n/a | — |
| `scripts/wsl/lucca-egress.sh` | 36 | — | iptables LUCCA-EGRESS chain on DOCKER-USER; private-range REJECT; 80/443 + pinned-DNS ACCEPT; default DROP | applied by `egress.apply_rules` (root) / manually | `iptables` | n/a | `EgressVerifier` checks |

**Wiring verdict:** the *policy*, *launcher*, *workspace*, *file tools* and *web fetch* are live (orchestrator → `service.execute_tool`). The *container architecture* is not: `container_spec` has zero call sites, no code ever runs `docker run`, and `SandboxService` defaults `use_direct_fallback=True` — so on the observed S1 session (Docker up, **zero containers**, `S1_22b`) every file tool and `run_python` executed **on the host** through the fallback. Web fetch has always been host-side.

## 2. As-built security posture (Spec 09 / ADR-003 / ADR-004 verification)

| Threat-model control | Claimed | As-built | Verdict |
|---|---|---|---|
| TM-06 path traversal | `validate_rel_path` + realpath + lstat every component + `O_NOFOLLOW` | `validate_rel_path` (`file_tool.py:57-123`): type/len/UTF-8/`%`/`\`/`.`/`..`/`~`/reserved-name checks, `commonpath` boundary, per-component symlink walk. `O_NOFOLLOW` **absent** (open after check — TOCTOU window) | implemented (weaker than claimed) |
| TM-03b fetch→write chains | forbidden sequence `(read_file→fetch_url)`, capped 20 k chars | `SequenceGuard` (`policy.py:74-94`) covers read→fetch and fetch→write/run_python; content capped 20 000 chars (`web_tool.py:25,191-193`) | implemented |
| TM-04 SSRF/egress | resolver check + egress chain + pinned DNS | `validate_url_ssrf` (`web_tool.py:39-110`) + `lucca-egress.sh` chain — **but fetch runs host-side** where the iptables chain (container-only, `DOCKER-USER -s 172.28.0.0/24`) does not apply, and validation has a DNS-rebinding TOCTOU (F-SBX-003) | guard present, egress N/A on the path that runs |
| TM-05 container escape | cap-drop ALL, no-new-privileges, read-only, non-root, limits | Arg rendering exists and is correct (`container_spec.py:34-108`) — **no code ever starts these containers** (F-SBX-002) | specified, unimplemented |
| TM-07 resource exhaustion | `RLIMIT_*`, pids/mem caps, swap 0 | Container args render the limits; the host fallback that actually runs has **none on Windows** (`resource` is None, `file_tool.py:14-17,291-303`) — F-SBX-001 | container-only; host path unconfined |
| TM-08 forged tool results | host recomputes sha256 for `read_file` | Implemented twice (`rpc.py:110-132` container path, `rpc.py:219-233` fallback) — observed `sha256_audit_mismatch` in T1 logs | implemented |
| TM-14 launcher abuse | whitelist → fixed exe, `shell=False`, templated args, rate limit, confirm | Implemented (`launcher.py:104-215`); `_focus_window` is a no-op that reports success (`:229-238`, F-SBX-010) | implemented (focus fake) |
| ADR-004 split containers | file container `--network none`; web container ephemeral, no files | Arg renderers correct; neither container ever created by code; web fetch runs in-process on the host (F-SBX-002) | specified, unimplemented |

---

## 3. Findings

Ordered by severity, then by ID. Every finding re-reviewed per Charter §3.5 (log in §7); `Status: OPEN`.

### F-SBX-001 — The direct host fallback is the production default: file tools and arbitrary `run_python` execute unconfined on the host, and Windows has no resource limits

| Field | Value |
|---|---|
| **ID** | F-SBX-001 |
| **Title** | The direct host fallback is the production default: file tools and arbitrary `run_python` execute unconfined on the host, and Windows has no resource limits |
| **Severity** | S1 — High |
| **Category** | SECURITY |
| **Location** | `src/lucca/sandbox/service.py:36-37`; `src/lucca/sandbox/rpc.py:34,67-68,191-310`; `src/lucca/sandbox/file_tool.py:14-17,289-314`; `docs/audit/evidence/S1_22b_container_ports_mounts_app_running.txt` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/service.py:34-37`
```python
    def __init__(
        self,
        workspace_root: Path | str | None = None,
        use_direct_fallback: bool = True,
        execute_apps: bool = True,
    ) -> None:
```
`src/lucca/sandbox/rpc.py:67-68`
```python
        if self.use_direct_fallback or not self.is_docker_available():
            return self._execute_direct(call_id, tool, args, t0)
```
`src/lucca/sandbox/file_tool.py:289-314` — `run_python` executes `[sys.executable, "-I", "-S", "-c", code]` with `cwd=workspace_root`; rlimits apply only when `resource` imports (`:14-17` — **`ImportError` on Windows**), and `preexec_fn` is POSIX-only regardless.
Artefact: `S1_22b` — with the app running, **zero containers existed**; every tool call in the session therefore took `_execute_direct`.

**What is wrong / assumed / missing**

The rpc docstring calls the fallback "for fast headless test runs" (`rpc.py:198`), but the only production constructor defaults it **on** — and it also triggers whenever `docker exec` would fail. On that path: `list_dir`/`read_file`/`write_file`/`delete_file`/`search_text` run against the host filesystem (path validation is the only boundary), and `run_python` is **arbitrary code execution with the user's full privileges** — no container, no seccomp, no memory/CPU limits on Windows (`resource` is unavailable; `preexec_fn` is POSIX-only), only a 10 s wall-clock timeout. Spec 09/ADR-004 mandate that `run_python` executes inside the file-sandbox container; TM-07's `RLIMIT_*` control is POSIX-only by construction. The confirmation gate (WRITE risk) applies to `run_python`, but a single user "yes" yields host code execution.

**Why it matters**

The sandbox is the substrate of TM-03…TM-08; on the default path it does not exist — the "file-sandbox" is path validation and the "web-sandbox" is irrelevant (fetch is host-side anyway, F-SBX-002). This is the audit's clearest case of a specified security architecture that is scaffolding on the shipped path.

**Questions this raises**

1. Was `use_direct_fallback=True` chosen deliberately for the no-Docker dev experience, or is it a test convenience that leaked into the production default? (Decision recorded: production default must be `False` with a spoken "sandbox unavailable" refusal.)

**Proposed remediation**

1. In `src/lucca/sandbox/service.py:37`: change the default to `use_direct_fallback: bool = False`; allow opting in explicitly for tests only.
2. In `src/lucca/sandbox/rpc.py:67-68`: when Docker is unavailable and fallback is disabled, return `ToolResult(ok=False, exit_code=-2, stderr="sandbox unavailable: Docker/WSL not reachable")` instead of executing locally. Before: silent host execution. After: explicit refusal.
3. In `src/lucca/core/orchestrator.py` (CORE-area): on that refusal, speak/caption "My file sandbox isn't available — Docker isn't reachable." per the ADR-001 O-4 honesty pattern.
4. Add `tests/test_sandbox.py::test_fallback_disabled_refuses_host_execution`: Docker unavailable + `use_direct_fallback=False` → no local execution, refusal result; and a companion test asserting `SandboxService()` (no args) refuses when the container is absent.

**Verification test**

- **Tier:** T1
- **Input:** the tests above
- **Expected output:** refusal result; `run_python` never invoked locally
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_fallback_disabled_refuses_host_execution -q`

**Cross-references:** F-SBX-002, F-SBX-011, F-CORE-003, TM-07

---

### F-SBX-002 — The ADR-004 container architecture is unimplemented: no code ever creates the sandboxes, and web fetch runs host-side

| Field | Value |
|---|---|
| **ID** | F-SBX-002 |
| **Title** | The ADR-004 container architecture is unimplemented: no code ever creates the sandboxes, and web fetch runs host-side |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/sandbox/container_spec.py:20-108`; `src/lucca/sandbox/egress.py:35-55`; `src/lucca/sandbox/service.py:118-141`; `docs/audit/evidence/S1_22_container_ports_mounts.txt` |
| **Status** | OPEN |

**Evidence**

A repo-wide search finds `get_file_sandbox_run_args`, `get_web_sandbox_run_args`, and `EgressVerifier` referenced **nowhere** in `src/` outside their definitions — no `docker run` for `lucca-file-sandbox` or the ephemeral web-sandbox exists in any code path. `service.py:118-141` dispatches `fetch_url` directly (`web_tool.fetch_url`, in-process, host network stack). Artefact `S1_22`/`S1_22b`: no containers existed before, during, or after the app run.

**What is wrong / assumed / missing**

ADR-004's split-sandbox design — file container with `--network none`, ephemeral web container with network but no files — is rendered as correct argument lists that nothing consumes. The enforcement consequence: the file/web isolation property ("in-sandbox read→POST impossible", TM-03a) holds today only because the *product* never offers fetch from the file path — while the *tool layer* can: `fetch_url` on the host can read nothing, but the host itself has full file access, so the isolation guarantee is provided by the LLM not chaining tools, not by architecture. `lucca-admin sandbox verify` (the operator's check) is also unimplemented (S1_32, row 63).

**Why it matters**

The threat model's container-escape analysis (TM-05), egress matrix (TM-04), and split-container exfiltration controls (TM-03a) all assume the containers run. Auditing their hardening (which is correctly specified in `container_spec.py`) audits a system that is never instantiated.

**Questions this raises**

1. Should the containers be started by `main.py` boot (supervisor) or manually per session? (→ §5 Q-B-04; decision needed before F-SBX-001's fix disables the fallback.)

**Proposed remediation**

1. In `src/lucca/main.py` (CORE-area change, joint with F-SBX-001): at boot, if Docker is reachable, ensure `lucca-file-sandbox` exists — `docker inspect` then `wsl docker <get_file_sandbox_run_args()>` — and `docker start` it if stopped; log `file_sandbox_ready`/`file_sandbox_unavailable` honestly.
2. Implement `lucca-admin sandbox verify` by calling `EgressVerifier().verify_all()` and printing the check matrix (also closes the S1_32 gap).
3. Add `tests/test_sandbox.py::test_boot_starts_file_sandbox` (T2, Docker-gated): boot path with Docker stubbed → inspect/create called with exactly the rendered args.

**Verification test**

- **Tier:** T2
- **Input:** the test above
- **Expected output:** container lifecycle invoked with normative args
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_boot_starts_file_sandbox -q`

**Cross-references:** F-SBX-001, F-SBX-004, F-SBX-005, F-CORE-003

---

### F-SBX-003 — SSRF validation has a DNS-rebinding TOCTOU: the resolved IP is checked then discarded, and the fetch re-resolves

| Field | Value |
|---|---|
| **ID** | F-SBX-003 |
| **Title** | SSRF validation has a DNS-rebinding TOCTOU: the resolved IP is checked then discarded, and the fetch re-resolves |
| **Severity** | S2 — Medium |
| **Category** | SECURITY |
| **Location** | `src/lucca/sandbox/web_tool.py:73-110,149-172` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/web_tool.py:149-151,160-162`
```python
    valid_url, _ = validate_url_ssrf(url)
    ...
    with httpx.Client(timeout=httpx.Timeout(15.0, connect=10.0), follow_redirects=False) as client:
        while True:
            resp = client.get(current_url, headers=headers)
```
(`validate_url_ssrf` resolves the hostname and rejects private IPs (`:73-108`), but returns the **URL**, not a pinned IP — `resolved_ip` is discarded at `:149`; `httpx` then performs its own DNS resolution at request time.)

**What is wrong / assumed / missing**

Classic DNS-rebinding TOCTOU: an attacker-controlled DNS name with a short TTL returns a public IP during validation and a private/RFC1918 IP (e.g. `192.168.x.x`, the WSL host, `169.254.169.254` metadata) during the actual `client.get` — the guard validated a different answer than the connection used. Redirect hops are re-validated (`:170`), but each hop's fetch has the same gap. The egress chain (TM-04) would block the container's private egress — but `fetch_url` runs **host-side** (F-SBX-002), where `DOCKER-USER` rules do not apply, so the TOCTOU is exploitable end-to-end on the shipped path. Expected: pin the connection to the validated IP (custom transport/`extensions` SNI host header) or re-resolve and compare at connect time.

**Why it matters**

TM-03b/TM-04 name host-side resolver checks as a control; this finding shows the check exists but does not bind the connection — the control's guarantee is VOID on the host-side path where it matters.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/web_tool.py`, `fetch_url()`: after validation, dial the validated IP directly — e.g. `httpx.HTTPTransport(local_address=…)`, or simplest: rewrite the URL host to the resolved IP with `Host: <hostname>` header and `server_hostname` SNI via an ssl context — and verify the response certificate against the original hostname. Before: resolve-check then independent connect. After: connect only to the validated address.
2. Add `tests/test_sandbox.py::test_dns_rebind_blocked`: stub `socket.getaddrinfo` returning public IP first, private second; assert the fetch connects to the public IP or fails — never the private one.

**Verification test**

- **Tier:** T1
- **Input:** the rebinding simulation above
- **Expected output:** private IP never dialed
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_dns_rebind_blocked -q`

**Cross-references:** F-SBX-001, F-SBX-002, TM-03b/TM-04/TM-16

---

### F-SBX-004 — `EgressVerifier` serves the process working directory over the LAN during verification

| Field | Value |
|---|---|
| **ID** | F-SBX-004 |
| **Title** | `EgressVerifier` serves the process working directory over the LAN during verification |
| **Severity** | S2 — Medium |
| **Category** | SECURITY |
| **Location** | `src/lucca/sandbox/egress.py:76-82` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/egress.py:76-80`
```python
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                pass

        server = http.server.HTTPServer((lan_ip, self.test_port), QuietHandler)
```

**What is wrong / assumed / missing**

`SimpleHTTPRequestHandler` serves files from the **current working directory** of the process. The verifier binds the host's LAN IP (reachable from the WSL host per step 2's positive control — and from anything else on the LAN) and serves for the full verification duration (~10–20 s including container pulls/timeout waits). Run from the repo root (the normal case), it exposes `src/**`, `config/**`, `docs/**` — the entire source tree including `config/persona.toml` and any local uncommitted files — to every LAN peer for the window. Expected: a handler returning a fixed string (`do_GET` → 200 "lucca-egress-probe"), serving nothing from disk.

**Why it matters**

The verification tool itself creates the disclosure window it exists to prevent tools from creating; LAN peers observed in S1 (`S1_28`: non-Lucca listeners on 172.20.96.1/192.168.1.5) make the exposure concrete.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/egress.py:76-82`: replace `SimpleHTTPRequestHandler` with a minimal handler whose `do_GET` writes `b"lucca-egress-probe"` and nothing else. Before: CWD file server. After: fixed-content probe.
2. Add `tests/test_sandbox.py::test_egress_probe_serves_no_files`: start the verifier's server handler against a temp CWD containing a secret file; GET any path → 200 fixed body, never file content.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** fixed probe body; no filesystem reads
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_egress_probe_serves_no_files -q`

**Cross-references:** F-SBX-002

---

### F-SBX-005 — Exec timeout kills the entire file-sandbox container, leaving it stopped with no restart logic

| Field | Value |
|---|---|
| **ID** | F-SBX-005 |
| **Title** | Exec timeout kills the entire file-sandbox container, leaving it stopped with no restart logic |
| **Severity** | S2 — Medium |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/sandbox/rpc.py:153-179` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/rpc.py:156-166`
```python
            kill_cmd = [
                "wsl",
                "-d", self.wsl_distro, "--",
                "docker", "kill", "-s", "KILL",
                self.container_name,
            ]
```

**What is wrong / assumed / missing**

On `communicate(timeout=…)` expiry the transport runs `docker kill -s KILL lucca-file-sandbox` — killing the **whole container**, not the one hung exec (the correct primitive is `docker exec` with a `timeout` inside the container, or killing the exec'd PID). Consequences: any other in-flight exec dies; the container is left in `Exited` state; nothing in `src/` ever restarts it (F-SBX-002 — no lifecycle code exists), so every subsequent file tool fails with "protocol: empty response from container" until a manual `docker start`. A single `run_python("while True: pass")` (container CPU limit slows it, timeout catches it) bricks the sandbox for the session.

**Why it matters**

The recovery action for one hung call is destroying the sandbox — and there is no automatic recovery. Availability defect on the container path that F-SBX-001's fix makes the primary path.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/rpc.py:153-179`: drop the `docker kill`; instead pass `timeout` into the toolsrv request and let `toolsrv` enforce it (it already runs `run_python` with its own timeout), plus use `docker exec`'s natural termination when the stdin pipe closes on `Popen` teardown. If a hard stop is needed, use `wsl … docker exec …` with `--detach` + `docker exec kill <pid>` semantics — never the container.
2. In `src/lucca/sandbox/rpc.py`, `execute()`: on empty-response failure, attempt one `docker start <container>` + retry before returning the error (self-healing).
3. Add `tests/test_sandbox.py::test_exec_timeout_does_not_kill_container` (T2, Docker-gated): hung sleep exec; assert the container is still `running` afterwards and a subsequent call succeeds.

**Verification test**

- **Tier:** T2
- **Input:** the test above
- **Expected output:** container survives; next call succeeds
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_exec_timeout_does_not_kill_container -q`

**Cross-references:** F-SBX-001, F-SBX-002

---

### F-SBX-006 — Egress verification docstring claims a 6-step matrix; the IPv6 check is absent and `all_passed` tests only 4 conditions

| Field | Value |
|---|---|
| **ID** | F-SBX-006 |
| **Title** | Egress verification docstring claims a 6-step matrix; the IPv6 check is absent and `all_passed` tests only 4 conditions |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/sandbox/egress.py:57-66,181-187` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/egress.py:64-66`
```python
 *         5. Non-web ports blocked (1.1.1.1:22 blocked).
 *         6. IPv6 blocked.
```
(`verify_all` implements checks 1–5 minus the IPv6 probe; `all_passed` at `:181-187` aggregates exactly four booleans.)

**What is wrong / assumed / missing**

The documented IPv6-blocked verification (the reason `lucca-egress.sh` disables IPv6 and `container_spec` sets `enable_ipv6=false`) has no implementation: an IPv6-capable egress regression would go undetected by the very tool that exists to detect egress regressions.

**Why it matters**

The egress matrix is the mechanical verification for TM-04; a claimed-but-absent check makes the matrix weaker than its own documentation while reporting `all_passed`.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/egress.py`, `verify_all()`: add step 6 — `docker run --rm --network lucca-net curlimages/curl -6 -s -m 3 https://ipv6.google.com` must fail — and include `container_ipv6_blocked` in `all_passed`.
2. Add a T2 (Docker-gated) assertion in `tests/test_sandbox.py::test_egress_matrix_includes_ipv6`.

**Verification test**

- **Tier:** T2
- **Input:** the matrix run
- **Expected output:** 5 checks aggregated; IPv6 probe present
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_egress_matrix_includes_ipv6 -q`

**Cross-references:** F-SBX-002, TM-04

---

### F-SBX-007 — `MAX_TOOL_CALLS_PER_TURN` (Spec 12 §3) is not enforced by `SequenceGuard`

| Field | Value |
|---|---|
| **ID** | F-SBX-007 |
| **Title** | `MAX_TOOL_CALLS_PER_TURN` (Spec 12 §3) is not enforced by `SequenceGuard` |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/sandbox/policy.py:61-94`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/12_threat_model.md:52,60` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/policy.py:74-94` — `check_and_record` implements only the two forbidden-sequence rules; no count constant, no cap, and no caller passes one. Spec 12 §3: "MAX_TOOL_CALLS_PER_TURN: Final = 4 … A turn exceeding MAX_TOOL_CALLS_PER_TURN stops and says so."

**What is wrong / assumed / missing**

An LLM loop (or a rule plan, per TM-09's "applies identically") can invoke an unbounded number of tools in one turn; the only brakes are per-tool confirmation and the forbidden pairs. The spec'd stop-and-say-so behaviour does not exist.

**Why it matters**

Resource-exhaustion and runaway-action control (TM-07's spirit) missing from the component that is 100 % covered by tests testing the wrong completeness.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/policy.py`: add `MAX_TOOL_CALLS_PER_TURN: Final = 4` and in `check_and_record`: `if len(self.turn_tools) >= MAX_TOOL_CALLS_PER_TURN: return False, "Tool call limit exceeded (4 per turn)."`.
2. Add `tests/test_sandbox.py::test_sequence_guard_tool_cap`: five `check_and_record("read_file")` → fifth rejected with the cap reason.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** fifth call rejected
- **Threshold:** ≤ 4 calls per turn
- **Command:** `uv run pytest tests/test_sandbox.py::test_sequence_guard_tool_cap -q`

**Cross-references:** F-BRAIN-010, TM-07/TM-09

---

### F-SBX-008 — The 1 GiB workspace cap is declared and checkable but enforced nowhere

| Field | Value |
|---|---|
| **ID** | F-SBX-008 |
| **Title** | The 1 GiB workspace cap is declared and checkable but enforced nowhere |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/sandbox/workspace.py:18,107-121`; `src/lucca/sandbox/file_tool.py:204-229` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/workspace.py:118-121`
```python
    def check_size_limit(self) -> tuple[bool, int]:
        size = self.get_total_size()
        return (size <= MAX_WORKSPACE_BYTES), size
```
(a repo-wide search finds no caller of `check_size_limit`; `write_file` caps only the individual write at 1 MiB — `file_tool.py:213-214` — and never consults the workspace budget.)

**What is wrong / assumed / missing**

Spec 09 §3's workspace quota is a dead check: `append`-mode writes and repeated `create`+`delete` cycles can grow `workspace/` without bound (only bounded by host disk), and nothing warns or refuses at the quota.

**Why it matters**

TM-07 (resource exhaustion) names read/write caps; the write cap exists per-call, the aggregate cap exists per-spec, and the connection between them is missing.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/file_tool.py`, `write_file()`: accept an optional `workspace: WorkspaceManager | None` and, when provided, refuse writes that would exceed `check_size_limit()`; wire it in `service.py`/`rpc.py` construction. Before: dead cap. After: enforced quota.
2. Add `tests/test_sandbox.py::test_write_refused_at_workspace_quota`: seed a >1 GiB logical workspace (sparse file), attempt a write → refused with a quota reason.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** quota refusal
- **Threshold:** ≤ 1 GiB
- **Command:** `uv run pytest tests/test_sandbox.py::test_write_refused_at_workspace_quota -q`

**Cross-references:** TM-07, F-SBX-001

---

### F-SBX-009 — `fetch_url`'s `render` parameter is accepted, forwarded, and ignored; headless rendering is unimplemented

| Field | Value |
|---|---|
| **ID** | F-SBX-009 |
| **Title** | `fetch_url`'s `render` parameter is accepted, forwarded, and ignored; headless rendering is unimplemented |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/sandbox/web_tool.py:140-144`; `src/lucca/sandbox/service.py:120-124`; `docker/web-sandbox/Dockerfile` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/service.py:121-124`
```python
            render = bool(args.get("render", False))
            max_chars = int(args.get("max_chars", 20000))
            ...
                structured, content = fetch_url(url=url, render=render, max_chars=max_chars)
```
(`fetch_url` never reads `render`; the web-sandbox image that exists for Chromium rendering is never started — F-SBX-002; `trafilatura` absence degrades extraction to the regex fallback silently, `web_tool.py:30-36,121-122`.)

**What is wrong / assumed / missing**

JS-rendered pages (the reason the web-sandbox image exists) return script-stripped skeletons; the parameter is a no-op the LLM can set in good faith. Extraction-quality degradation when `trafilatura` is missing is silent.

**Why it matters**

Honesty of the tool surface: the schema offers a capability that does nothing, and the silent `trafilatura` fallback is invisible in results.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/web_tool.py`, `fetch_url()`: when `render=True`, return `structured["render_unavailable"] = True` (or wire the web-sandbox container per F-SBX-002) instead of ignoring it; log `trafilatura_unavailable` once when the fallback extractor is used.
2. Add `tests/test_sandbox.py::test_render_flag_reported_honestly`: `fetch_url(url, render=True)` → `structured["render_unavailable"] is True` until real rendering lands.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** honest capability report
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_render_flag_reported_honestly -q`

**Cross-references:** F-SBX-002

---

### F-SBX-010 — `_focus_window` is a no-op that reports success ("brought to focus")

| Field | Value |
|---|---|
| **ID** | F-SBX-010 |
| **Title** | `_focus_window` is a no-op that reports success ("brought to focus") |
| **Severity** | S3 — Low |
| **Category** | UX |
| **Location** | `src/lucca/sandbox/launcher.py:229-238,154-158` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/launcher.py:234-236`
```python
            user32 = ctypes.windll.user32
            # EnumWindows or find window by process
            user32.SetForegroundWindow(user32.GetForegroundWindow())
```
(caller at `:154-158` returns `f"{app_id} is already running; brought to focus."`)

**What is wrong / assumed / missing**

`SetForegroundWindow(GetForegroundWindow())` re-sets the **currently** foreground window — it cannot focus the target application (finding its HWND is not implemented; the comment admits it). The user is told the app was focused when nothing happened. Also `single_instance` detection matches the process **name** only, so any process with the same image name counts.

**Why it matters**

Fabricated success on a user-visible action — the same honesty defect class as F-CORE-033 and the implementation prompt's mission statement ("a button that says 'restarted' must have restarted something").

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/launcher.py`: implement real focus (enumerate top-level windows via `EnumWindows`, match PID via `GetWindowThreadProcessId` against `psutil` Process exe, `SetForegroundWindow` on the match) **or** return the honest message `f"{app_id} is already running."` without the focus claim. Decision recorded: honest message now, real focus later.
2. Add `tests/test_sandbox.py::test_focus_message_honest` (UI-adjacent): single-instance path returns a message not containing "focus".

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** message without a false focus claim
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_focus_message_honest -q`

**Cross-references:** F-CORE-033

---

### F-SBX-011 — `system_tools` fabricates telemetry: hard-coded NPU "Active"/iGPU "Standby" statuses and a fake 16 GB GPU fallback

| Field | Value |
|---|---|
| **ID** | F-SBX-011 |
| **Title** | `system_tools` fabricates telemetry: hard-coded NPU "Active"/iGPU "Standby" statuses and a fake 16 GB GPU fallback |
| **Severity** | S3 — Low |
| **Category** | UX |
| **Location** | `src/lucca/sandbox/system_tools.py:64-77,180-189` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/system_tools.py:180-184`
```python
        "npu": {
            "name": "Intel(R) AI Boost",
            "status": "Active (Whisper STT & Embeddings, 15W Low Power)",
            "active": True,
        },
```
(and the nvidia-smi fallback at `:64-77` returns `available: False` **alongside** `total_mb: 16384.0, free_mb: 16384.0` — fabricated numbers next to the honest flag; the HUD/settings render these numbers.)

**What is wrong / assumed / missing**

NPU and iGPU rows are string literals — no query exists (the ASR ladder in `S1_35` showed the NPU path is in fact broken/degenerate, yet the HUD reports "Active … 15W"). The GPU fallback invents a full 16 GB free GPU. Consumers are the telemetry HUD and settings diagnostics — the user's window into hardware truth.

**Why it matters**

Fabricated telemetry displayed as real measurements: the same honesty-of-recorded-metrics family as F-CORE-009/F-BRAIN-017/F-ROUT-005, here shown to the user.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/system_tools.py`: report `"status": "Unknown (not queried)"` / `"active": None` for NPU/iGPU until a real probe exists (OpenVINO device query is available in the venv), and set all numeric GPU fields to `None` with `available: False` in the fallback. Before: fabricated. After: honest unknowns.
2. Add `tests/test_sandbox.py::test_telemetry_never_fabricates`: with nvidia-smi absent, GPU numeric fields are `None`; NPU `active` is not `True`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** unknowns, not fabrications
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_telemetry_never_fabricates -q`

**Cross-references:** F-CORE-009, F-BRAIN-017, F-ROUT-005

---

### F-SBX-012 — Hard-coded absolute host paths across the sandbox (`read_codebase_file`, egress script path, telemetry log dir)

| Field | Value |
|---|---|
| **ID** | F-SBX-012 |
| **Title** | Hard-coded absolute host paths across the sandbox (`read_codebase_file`, egress script path, telemetry log dir) |
| **Severity** | S3 — Low |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/sandbox/file_tool.py:346`; `src/lucca/sandbox/egress.py:46-47`; `src/lucca/sandbox/system_tools.py:227` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/file_tool.py:346`
```python
        codebase_root = Path(r"C:\projects\ProjectLucca")
```
(`egress.py:46`: `win_to_wsl_path(r"C:\projects\ProjectLucca\scripts\wsl\lucca-egress.sh")`; `system_tools.py:227`: `Path("C:/ProjectLucca/logs/resource_sessions")` — the F-CORE-030 pattern in three more modules; `read_codebase_file` additionally exposes the whole host repo read-only through the file-tool surface although no tool schema advertises it — the implementation half of F-BRAIN-004's "Codebase Inspection" fiction.)

**What is wrong / assumed / missing**

Three hard-coded roots bypass `LUCCA_HOME`/config; the case-mismatched `C:\projects\...` (repo lives at `C:\Projects\...`) relies on Windows case-insensitivity; and `read_codebase_file` is an unadvertised capability reachable through `SafeFileTool` (container path excepted — `toolsrv` never exposes it) that reads the product's own source.

**Why it matters**

Portability, dev/prod conflation, and an unadvertised read surface; all three are the same maintainability defect F-CORE-030 documented for core.

**Questions this raises**

1. None.

**Proposed remediation**

1. Replace each hard-coded path with `get_config().resolve_path(...)` equivalents (`file_tool.py:346` → config-anchored repo root or removal; `egress.py:46` → `Path(__file__).parents[2] / "scripts/wsl/lucca-egress.sh"`; `system_tools.py:227` → `config.resolve_path("logs/resource_sessions")`).
2. In `src/lucca/sandbox/file_tool.py`: delete `read_codebase_file` or register it honestly as a tool schema with its own risk class (decision recorded: delete until Spec 09 defines it).
3. Add `tests/test_sandbox.py::test_no_hardcoded_project_paths`: grep `src/lucca/sandbox` for `C:\projects`/`C:/ProjectLucca`/`C:\ProjectLucca` literals → zero.

**Verification test**

- **Tier:** T0
- **Input:** the grep gate above
- **Expected output:** zero hard-coded roots in `src/lucca/sandbox`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_no_hardcoded_project_paths -q`

**Cross-references:** F-CORE-030, F-BRAIN-004, F-MEM-013

---

### F-SBX-013 — Whitelist loader silently falls back to built-ins on any parse error

| Field | Value |
|---|---|
| **ID** | F-SBX-013 |
| **Title** | Whitelist loader silently falls back to built-ins on any parse error |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/sandbox/launcher.py:92-102` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/launcher.py:99-100`
```python
            except Exception as exc:  # noqa: BLE001
                logger.warning("whitelist_load_failed", error=str(exc))
```
(falls through to `defaults` — a corrupted `tool_whitelist.toml` silently swaps the operator's security configuration for the built-in five apps, at warning level.)

**What is wrong / assumed / missing**

A security-relevant configuration (which executables may launch) degrades silently on parse failure. The safe direction for a whitelist is fail-closed: refuse to launch anything until the whitelist parses, or at minimum surface the degradation to the user. Compare: the route/mem loaders have the same pattern (F-BRAIN-037, F-MEM-037) but a corrupted *whitelist* changes a security boundary.

**Why it matters**

An operator editing `tool_whitelist.toml` with one syntax error silently reverts launch authorization to the defaults — possibly re-enabling apps they removed.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/launcher.py:92-102`: on `tomllib.TOMLDecodeError`, raise `RuleError`/`SandboxPathError` (fail-closed) rather than falling back; keep the missing-file → defaults behaviour.
2. Add `tests/test_sandbox.py::test_whitelist_parse_error_fails_closed`: corrupt TOML → `launch()` refuses all apps with a "whitelist unparseable" reason.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** fail-closed refusal
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_whitelist_parse_error_fails_closed -q`

**Cross-references:** F-BRAIN-037, F-MEM-037

---

### F-SBX-014 — `search_text` has no aggregate time/file budget across the recursive scan

| Field | Value |
|---|---|
| **ID** | F-SBX-014 |
| **Title** | `search_text` has no aggregate time/file budget across the recursive scan |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/sandbox/file_tool.py:241-287` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/file_tool.py:256-267`
```python
        files_to_search = [target] if target.is_file() else sorted(target.rglob("*"))

        for f in files_to_search:
            if not f.is_file():
                continue
            try:
                with open(f, "rb") as fp:
                    ...
                    text = fp.read(MAX_FILE_BYTES).decode("utf-8", errors="replace")
```

**What is wrong / assumed / missing**

Per-file caps exist (256 KiB read, 200 hits) but the loop itself is unbounded: a workspace with 10 000 files means 10 000 opens/reads per search regardless of hits — up to the RPC's 15 s timeout on the container path and **unbounded on the direct-fallback path** (no timeout wrapper in `_execute_direct`, `rpc.py:271-285`). On the host fallback a large workspace makes `search_text` a synchronous multi-minute hang of the turn thread.

**Why it matters**

Resource-exhaustion edge (TM-07) on a live tool; the container path bounds it, the default path (F-SBX-001) does not.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/sandbox/file_tool.py`, `search_text()`: add a `deadline = time.monotonic() + 10.0` checked per file; on expiry return `{"truncated": True, "reason": "time_budget"}` with the hits so far. Before: unbounded. After: bounded scan with honest truncation.
2. Add `tests/test_sandbox.py::test_search_time_budget`: many dummy files with a patched tiny deadline → truncated result, prompt return.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** truncated result within the budget
- **Threshold:** ≤ 10 s
- **Command:** `uv run pytest tests/test_sandbox.py::test_search_time_budget -q`

**Cross-references:** F-SBX-001, TM-07

---

### F-SBX-015 — `read_file`'s binary sniff covers only the first 8 KiB; binary content after that is replaced-character garbage

| Field | Value |
|---|---|
| **ID** | F-SBX-015 |
| **Title** | `read_file`'s binary sniff covers only the first 8 KiB; binary content after that is replaced-character garbage |
| **Severity** | S4 — Info |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/sandbox/file_tool.py:181-194` |
| **Status** | OPEN |

**Evidence**

`src/lucca/sandbox/file_tool.py:182-185`
```python
            # Sniff first chunk for binary content
            sniff = f.read(SNIFF_CHUNK_SIZE)
            if b"\x00" in sniff:
                raise SandboxPathError("is_binary", f"Binary file detected: {path}")
```
(`SNIFF_CHUNK_SIZE = 8192`; the full read at `:188` then decodes up to 256 KiB with `errors="replace"`.)

**What is wrong / assumed / missing**

A text file with a binary payload appended after the first 8 KiB (or a UTF-16 file whose first chunk happens to be ASCII BOM-less text) passes the sniff and is returned as U+FFFD-laden garbage — which then flows into `content` → potential `TOOL_CONTENT_UNTRUSTED` material. Informational: the sha256 audit still matches (computed over the same bytes), so no integrity claim breaks; the issue is content quality, not safety.

**Why it matters**

Minor content-fidelity gap; worth pinning so the sniff's limitation is a documented decision rather than an accident.

**Questions this raises**

1. None.

**Proposed remediation**

1. Either extend the sniff to the whole read buffer (cheap at 256 KiB: check `b"\x00" in data` after the read) or document the 8 KiB sniff window in the docstring. Decision recorded: check the full buffer.
2. Add `tests/test_sandbox.py::test_binary_after_sniff_window_detected`: text prefix + NUL after 8 KiB → `is_binary` raised.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** `is_binary` raised
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_sandbox.py::test_binary_after_sniff_window_detected -q`

**Cross-references:** None

---

## 4. Assumptions register

| # | Location | Assumption embedded in code | Why unverified | Risk if false |
|---|---|---|---|---|
| A-S-01 | `service.py:37` | Direct host fallback is acceptable in production | Default `True`; observed zero containers (S1_22b) | Sandbox is fiction on the shipped path (F-SBX-001) |
| A-S-02 | `file_tool.py:14-17` | `resource` limits are unnecessary on Windows | Import-guarded to None; no Windows-equivalent exists | `run_python` unconfined on host (F-SBX-001) |
| A-S-03 | `web_tool.py:110` | Validation-time DNS answer equals connect-time DNS answer | Resolved IP discarded; no pinning (F-SBX-003) | DNS rebinding reaches private networks |
| A-S-04 | `egress.py:47` | `wsl -u root` is acceptable for applying iptables | Works today (S1_19b); root from a user-mode app is a privilege posture decision | Egress policy mutable by any host code running as the user |
| A-S-05 | `launcher.py:119` | `time.monotonic()` launch history survives only in-process | Per-process rate limit; multiple Lucca processes bypass it | Rate limit is per-instance, not global |
| A-S-06 | `rpc.py:110-132` | sha256 over UTF-8 re-encoding equals the container's file hash for valid UTF-8 | Holds only when content round-trips exactly (non-UTF-8 files are replaced-decoded → mismatch → ok=False); observed `sha256_audit_mismatch` in T1 logs (S1_12) | Non-UTF-8 files permanently unreadable via RPC path with audit failure |
| A-S-07 | `container_spec.py:45` | The workspace bind mount is the only host exposure | Bind is `src={wsl_mount}` — the whole `LUCCA_HOME/workspace`; correct per spec | None identified |
| A-S-08 | `system_tools.py:151` | `cpu_count or 24` fallback is harmless | Fabricates core count on exotic hosts | Cosmetic |

## 5. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-B-04 | Should the file-sandbox container be started by the supervisor at boot, or on first tool use? | Prerequisite for F-SBX-001's fix and F-SBX-002 | owner / architect |
| Q-S-01 | Should `run_python` exist at all in v1 (it is the highest-risk tool, host-exec on the fallback path), or be removed until the container path is mandatory? | F-SBX-001 remediation scope | owner |
| Q-S-02 | Is `read_codebase_file` a wanted capability (the system prompt advertises it) or should the prompt claim be deleted? | F-SBX-012 / F-BRAIN-004 alignment | owner |

## 6. Coverage gaps

### 6.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| Container lifecycle (create/start file-sandbox) | ADR-004, Spec 09 §2 | none (no code — F-SBX-002) |
| Web-sandbox ephemeral execution path | ADR-004 | none (fetch is host-side — F-SBX-002) |
| DNS-rebinding resistance | TM-03b/TM-04/TM-16 | none (TOCTOU — F-SBX-003) |
| IPv6 egress verification | Spec 09 §8 step 6 | none (F-SBX-006) |
| Tool-call cap per turn | Spec 12 §3 | none (F-SBX-007) |
| Workspace 1 GiB quota enforcement | Spec 09 §3 | check exists, unenforced (F-SBX-008) |
| `run_python` resource limits on the shipped platform | TM-07 | none (POSIX-only — F-SBX-001) |
| Honest render capability | — | none (F-SBX-009) |
| `EgressVerifier` invocation from any entry point | Spec 09 §8 | none (`lucca-admin sandbox verify` unimplemented — S1_32) |
| Non-UTF-8 file read semantics via RPC | T-SBX-16 | audit-mismatch path tested; the underlying UTF-8 round-trip assumption untested (A-S-06) |

### 6.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| `tests/test_sandbox.py` (container arg-shape tests) | Normative container hardening | Arg list shape only; no container is ever created from them (F-SBX-002) |
| `tests/test_sandbox.py` (file-tool tests) | Sandboxed file operations | All via `_execute_direct` — i.e. the unconfined host path the tests were supposed to abstract away (F-SBX-001) |
| `tests/test_sandbox.py::test_t_sbx_16` (sha256 audit) | Host-side integrity audit | Verified only on the UTF-8 round-trip happy path; replaced-decode mismatch is logged as a failure, not distinguished (A-S-06) |

## 7. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** Reviewing F-SBX-001 (fallback default) surfaced F-SBX-002 (the containers the fallback replaces are never created — the deeper defect), the Windows-rlimits detail inside 001, and the search-time-budget sibling F-SBX-014 (unbounded precisely because the fallback has no RPC timeout). Reviewing F-SBX-003 (rebinding) surfaced F-SBX-004 (the verifier's own LAN exposure) during the egress read. Reviewing F-ROUT-003's whitelist drift surfaced F-SBX-013 (fail-open whitelist loader).
2. **Unasked questions.** 2 registered (§5) plus the carried Q-B-04; decisions that could be made were made in the findings (F-SBX-001: default-off fallback; F-SBX-005: never kill the container; F-SBX-010: honest message; F-SBX-012: delete `read_codebase_file`; F-SBX-015: full-buffer sniff).
3. **Unwarranted assumptions.** The first draft of F-SBX-001 was graded S0 ("no sandbox"); downgraded to S1 after verifying that `run_python` sits behind the WRITE-confirmation gate and that path validation still constrains the file tools on the fallback path — the unconfined surface is real but user-gated. The first draft of F-SBX-011 claimed "NPU status is a lie" — verified against `S1_35` (NPU degenerate) and reworded to "fabricated string, no probe", S3. The T-SBX-16 sha256 finding was downgraded to an assumption (A-S-06) after confirming the audit *works* — it is the UTF-8 round-trip assumption that is untested.
4. **Incomplete planning.** Every remediation names file, function, before/after, and a runnable command; owner-owned calls parked as Q-S-01/Q-S-02 with recorded defaults (keep `run_python` but default the fallback off; delete `read_codebase_file` until specified).
5. **Architectural flaws → F-ARCH candidates.** (a) F-SBX-001/002 together: the entire ADR-004 container architecture is scaffolding on the shipped path — the strongest SBX F-ARCH candidate, to be merged with the F-CORE-003 unwiring family into the "Phase 2–4 architecture specified but not instantiated" roll-up; (b) F-SBX-011 joins the honesty-of-recorded-metrics F-ARCH family.

Severity re-grades during the pass: F-SBX-001 S0→S1 (confirmation gate + path validation bound the fallback; the unconfined arbitrary-exec remains the defect); F-SBX-004 kept S2 (real LAN exposure window, mitigated by duration); F-SBX-015 set S4 (content fidelity, no safety impact).
