# Spec 09 — Sandbox Hardening: containers, RPC, file tool, web tool, launcher, egress verification

Implements ADR-003, ADR-004, D-08. Replaces doc 03 §Domain C and `src/lucca/sandbox/safe_file_tool.py` behaviour.

## 1. Host ↔ container RPC

- **Transport:** `docker exec -i <container> lucca-toolsrv` with newline-delimited JSON over stdin/stdout (one request, one response, process exits). No TCP ports published, no Docker socket exposed to anything but `lucca-core` (which calls the Docker CLI through `wsl -d Ubuntu -- docker …`; the Python `docker` SDK is **not** used because it would need the daemon socket exposed to Windows).
- Request: `{"call_id","tool","args","deadline_ms"}`; response: `{"call_id","ok","exit_code","structured","content","content_truncated","stderr","elapsed_ms"}` validated on the host into `ToolResult`. Malformed → `ToolResult(ok=False, exit_code=-2, stderr="protocol")`.
- Per-call wall timeout enforced on the **host** (`asyncio.timeout(deadline)`), then `docker kill -s KILL` of the exec'd pid via `docker exec … kill`. Container itself has `--stop-timeout 2`.
- Signing: host-side `ToolResultSigner` after validation (spec 03). The container image contains no keys.

## 2. Container specs (`sandbox/container_spec.py` renders these)

```bash
# file-sandbox (long-lived per task)
docker run -d --name lucca-file-sandbox \
  --network none \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  --mount type=bind,src=/mnt/c/ProjectLucca/workspace,dst=/workspace \
  --user 1000:1000 --cap-drop=ALL --security-opt=no-new-privileges --security-opt=seccomp=default \
  --memory=768m --memory-swap=768m --cpus=1.5 --pids-limit=256 --ulimit nofile=256:256 --ulimit fsize=52428800 \
  --stop-timeout 2 --init lucca/file-sandbox:<tag> sleep infinity

# web-sandbox (ephemeral per call)
docker run --rm -i --name lucca-web-<call_id> \
  --network lucca-net --dns 1.1.1.1 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  --user 1000:1000 --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=512m --memory-swap=512m --cpus=1.0 --pids-limit=128 \
  --stop-timeout 2 --init lucca/web-sandbox:<tag> lucca-toolsrv

# web-sandbox-js (ephemeral, only for render=true)
docker run --rm -i --network lucca-net --dns 1.1.1.1 --read-only \
  --tmpfs /tmp:rw,nosuid,size=256m --shm-size=256m \
  --user 1000:1000 --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=1024m --memory-swap=1024m --cpus=2.0 --pids-limit=1024 \
  --stop-timeout 5 --init lucca/web-sandbox-js:<tag> lucca-toolsrv     # chromium --no-sandbox --disable-gpu
```

No `--gpus` anywhere. Images built from `python:3.12-slim`, pinned digests, non-root user created in Dockerfile, `pip install --no-cache-dir` of exact versions, `HEALTHCHECK` not needed (exec model).

drvfs mount for `/mnt/c` in `/etc/wsl.conf`: `[automount] options="metadata,uid=1000,gid=1000,umask=022,fmask=111"` so files created by the container are owned by uid 1000 and readable on Windows. Caveat documented: drvfs throughput ≈ 50–150 MB/s; fine for text.

## 3. Workspace lifecycle (D-08)

- `C:\ProjectLucca\workspace` is the **only** mounted path. `inbox\` is never mounted.
- Task open: `reset_workspace()` if the previous task did not close cleanly (per `task_journal`); copy requested `inbox\` files in (user-named, ≤ 200 MB total).
- Task close / `hard_kill_and_recreate` / boot: host deletes every entry under `workspace\` (retry on sharing violations 3× with 200 ms delay; log any leftover), then `docker rm -f` + `docker run` the file-sandbox. Test T-SBX-05 asserts `workspace\` is empty after close and the container id changed.
- Size cap 1 GiB (`fsize` ulimit per file 50 MB; host check on close).

## 4. File tool (`lucca-toolsrv` inside file-sandbox; host mirror of the same validation in `sandbox/file_tool.py` for defence in depth)

Path validation (`validate_rel_path(p: str) -> PurePosixPath`), all checks **before** touching the filesystem:

1. Type str, 1 ≤ len ≤ 1 024, valid UTF-8, no NUL, no chars in `[\x00-\x1f\x7f]`, no `%` (reject percent-encoding outright — no decoding attempts), no backslash.
2. Must be relative; split on `/`; no segment equals `.` or `..`; no empty segments except trailing; no segment starts with `~`; no Windows reserved names (`con, prn, aux, nul, com1-9, lpt1-9`) case-insensitively (harmless on Linux, keeps the mount Windows-readable).
3. Resolve: `real = os.path.realpath("/workspace/" + p)`; require `os.path.commonpath([real, "/workspace"]) == "/workspace"`.
4. Symlinks: `os.lstat` every component; any symlink → `PathTraversal` (workspace never legitimately contains symlinks; archive tools must not create them).
5. Open with `os.open(real, flags | O_NOFOLLOW | O_CLOEXEC)` — TOCTOU mitigation.

Error type: **one** exception `SandboxPathError(code, message)` with codes `traversal|invalid_chars|reserved|too_long|symlink|not_found|too_large|is_binary|is_dir`. Doc 04's `PermissionError` expectation is retired; tests assert on `code`.

Operations and limits:

| Tool | Args | Limits | `structured` (TOOL_VERIFIED) | `content` (UNTRUSTED) |
|---|---|---|---|---|
| `list_dir` | path, recursive=false | ≤ 500 entries (truncated flag) | entries `{name,size,mtime,is_dir}` | — |
| `read_file` | path, max_bytes=262144 | 256 KiB; binary sniff (NUL in first 8 KiB → `is_binary`) ; decode UTF-8 `errors="replace"` | `{size, sha256, truncated}` | text |
| `write_file` | path, content, mode=`create|overwrite|append` | ≤ 1 MiB; parent must exist; `create` fails if exists | `{size, sha256}` | — |
| `search_text` | pattern (literal or glob), path, max_hits=200 | no regex from LLM (ReDoS); case-insensitive literal | `{hits:[{file,line,col}]}` | snippets |
| `run_python` | code, timeout=10 | `python -I -S`, `RLIMIT_AS 256 MB`, `RLIMIT_CPU 10`, no network (container has none), stdout ≤ 64 KiB | `{exit_code, elapsed_ms}` | stdout/stderr |
| `delete_file` | path | only within workspace; no dirs | `{deleted:true}` | — |

Risk: `list_dir/read_file/search_text` = READ; `write_file/delete_file/run_python` = WRITE.

## 5. Web tool (`fetch_url`, web-sandbox)

- Args: `url`, `render=false`, `max_chars=20000`. Scheme must be `http|https`; **URL ≤ 512 chars, query string ≤ 128 chars, no userinfo (`user:pass@`)** — limits the LLM-carried exfiltration channel (TM-03b); violations are refused and logged with `sbx.url_query_len`. Host must not resolve to any blocked range (**resolve on host first** via `socket.getaddrinfo`, reject RFC1918/link-local/loopback/CGNAT/multicast/IPv6 — defence in depth over ADR-003; log `dns_rebinding_suspect` if host resolved differently inside container).
- `httpx` GET only, follow ≤ 8 redirects (re-validate each hop), timeout 10 s connect/15 s total, `Accept-Encoding gzip`, body ≤ 2 MiB (stream and abort), content-type must be `text/*` or `application/(xhtml+xml|json|xml)`; else `structured.blocked_content_type`.
- Extraction: `trafilatura.extract(html, include_links=False, include_comments=False)`; fallback to `<title>` + visible text. Truncate to `max_chars`; mark `content_truncated`.
- Never sends cookies, auth headers, or a referer. UA string identifies Lucca.
- `render=true` uses web-sandbox-js (Playwright Chromium, `--no-sandbox` because `cap-drop=ALL` — documented). Only when the first pass yields < 200 chars and page looks JS-driven (`<noscript>`/`__NEXT_DATA__`/`ng-app` heuristics) **and** config `web.allow_render=true`.
- Risk: NETWORK (auto, READ-equivalent). Output content is `TOOL_CONTENT_UNTRUSTED` always.

## 6. Host app launcher (`sandbox/launcher.py`, runs in `lucca-core`, no container)

- Whitelist `config\tool_whitelist.toml`:
  ```toml
  [apps.calculator] exe = "calc.exe"            aliases = ["calculator","calc"]     args = []
  [apps.notepad]    exe = "notepad.exe"         aliases = ["notepad","text editor"] args = ["{file?}"]  # optional file inside workspace only
  [apps.browser]    exe = "msedge.exe"          aliases = ["browser","edge"]        args = ["{url?}"]   # http(s) only
  ```
- Launch via `subprocess.Popen([exe, *args], shell=False, creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP)`; `exe` resolved with `shutil.which` or absolute path from config; **never** `shell=True`, never `os.startfile` on arbitrary paths.
- Templated args validated per app: `{file}` must pass `validate_rel_path` and exist under `workspace\`; `{url}` must be `https?://` public host (same resolver check as §5).
- If already running (process name match) → `focus` via `SetForegroundWindow` instead of a second instance (config `apps.<x>.single_instance=true`).
- Rate limit: ≤ 3 launches / minute; ≤ 1 per 5 s.
- Risk: LAUNCH → always confirm (spoken). `apps_running` snapshot for `RuleState` comes from `psutil` filtered to whitelisted exe names only.

## 7. Confirm flow (shared by WRITE/LAUNCH)

TTS: "Do you want me to <action summary>? Say yes or no." → UI `confirm` state (also click buttons) → next PTT transcript matched against `^(yes|yeah|yep|do it|go ahead|confirm)\b` / `^(no|nope|cancel|stop|don't)\b` → else "Cancelled." Timeout 15 s → cancelled. The confirm decision is logged in `DecisionRecord.tool_calls[i].confirmed_via`.

## 8. Egress verification (positive-controlled) — run by `lucca-admin sandbox-verify` and by test T-SBX-07..12

| Step | Expect |
|---|---|
| Start `python -m http.server 8089 --bind <Windows LAN IPv4>` on host | — |
| From Ubuntu shell: `curl -s -m 3 http://<LAN IP>:8089/` | **200** (proves listener reachable → test is not vacuous) |
| From web-sandbox: same URL | exit 7/28 within 3 s |
| From web-sandbox: `curl -s -m 5 https://example.com` | 200 |
| From web-sandbox: `nc -zv -w 3 1.1.1.1 22` | blocked |
| From web-sandbox: `curl -6 -m 3 https://ipv6.google.com` | fails (no IPv6) |
| From web-sandbox: `dig @192.168.1.1 example.com` (LAN resolver) | blocked; `dig example.com` (embedded/1.1.1.1) works |
| From file-sandbox: any `curl` | fails immediately (no network namespace route) |
| `iptables -S LUCCA-EGRESS` | rule order equals ADR-003 listing exactly (string compare) |

## 9. Tests (matrix IDs)

| ID | Test | Pass |
|---|---|---|
| T-SBX-01 | Path fixtures: 60 malicious (`../`, `..%2f`, `\`, NUL, `~`, `nul`, 1 100 chars, symlink) → `SandboxPathError` with expected code; 20 benign → ok | exact |
| T-SBX-02 | Hypothesis: random strings never escape `/workspace` (realpath check) and never raise anything but `SandboxPathError` | 5 000 cases |
| T-SBX-03 | `read_file` 300 KiB → truncated flag, 256 KiB content; binary → `is_binary` | — |
| T-SBX-04 | `run_python` `while True: pass` → killed at 10 s; `bytearray(10**9)` → MemoryError inside, ok=False | — |
| T-SBX-05 | Task close wipes workspace; container id changes | — |
| T-SBX-06 | Host timeout kills a sleeping exec within deadline+500 ms | — |
| T-SBX-07…12 | Egress table §8 | as listed |
| T-SBX-13 | `fetch_url` to `http://127.0.0.1`, `http://[::1]`, `http://169.254.169.254`, hostname resolving to 10.x → rejected on host before container start | — |
| T-SBX-14 | Launcher: `"open calculator"` → confirm → `calc.exe` spawned with `shell=False`; `"open cmd"` → not whitelisted → refused; 4th launch in a minute → rate-limited | — |
| T-SBX-15 | `TOOL_CONTENT_UNTRUSTED` body with `<script>` and prompt-injection text → stored in `tool_contents`, never in `memories`; LLM summary spoken | Tier 2 |
| T-SBX-19 | FakeLLM issues `read_file` then `fetch_url` in one turn → second call refused with spoken explanation; URL with 200-char query → refused | Tier 2 |
