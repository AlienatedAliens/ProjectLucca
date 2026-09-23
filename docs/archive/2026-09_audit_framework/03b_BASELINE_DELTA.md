# 03b — Baseline Delta (re-inventory, S2b)

**Captured:** 2026-09-18T06:04–06:21Z by subtask S2b, per F-BRAIN-008 remediation step 2 (ratified by the audit owner).
**Method:** `git status --porcelain` + `git rev-parse HEAD` + `git branch --show-current` → [`evidence/S2b_01_git_status.txt`](evidence/S2b_01_git_status.txt); line counts with S0's own method — `(Get-Content <file> | Measure-Object -Line).Lines` — over `src tests config docker scripts packaging` (`*.py *.toml *.sh *.ps1`) excluding `__pycache__` → [`evidence/S2b_02_line_counts.txt`](evidence/S2b_02_line_counts.txt).
**HEAD:** `ed14f6b44fc233c94f01c9f9f3c1f68619e026e7` on `master` — unchanged from S0.

---

## 1. Measurement-method correction (supersedes the S2b first pass)

S0's inventory (`03_BASELINE.md` §5) counts **non-blank** lines (`Measure-Object -Line` skips empty lines). S2b's first comparison wrongly used total lines (from file reads), producing a false "+63/+25/+40/+21/+74 lines" delta for all five brain modules and a false "704 vs 608" orchestrator discrepancy. Under S0's own metric the trees agree almost everywhere. This correction is recorded in `findings/brain.md` §12 and F-BRAIN-008 has been rewritten.

## 2. Git status vs S0 (`03_BASELINE.md` §2)

In-scope entries are **identical to S0** (same 34 tracked-modified + 19 untracked in-scope paths), with exactly three differences, all accounted for:

| Path | S0 (2026-09-17T23:54Z) | Now | Explanation |
|---|---|---|---|
| `scripts/test_s1_startup.py` | not listed (unmodified, tracked) | `M` | **new post-S0 modification** (see §3) |
| `docs/…` pre-audit files | untracked `?? docs/IMPLEMENTATION_PROMPT_…`, `?? docs/UI_USER_GUIDE.md` | `D` (deleted from tracking; content in `docs/archive/…`, unchanged) | S0's own archive move (§7) |
| `docs/archive/`, `docs/audit/` | absent | `??` (untracked) | audit artefacts, expected |

## 3. Line-count deltas vs S0 (S0 metric, non-blank lines)

Of the 110 text files inventoried, **107 are byte-count-identical in line count to S0** — including all four other brain modules (`chunker.py` 196, `llm_client.py` 174, `prompt_builder.py` 584, `toolcall_demux.py` 130), `orchestrator.py` (608), every memory/reasoning/router/sandbox/senses/ui module, every test, both migrations-era configs, and 13 of 15 scripts. **Three files differ:**

| Path | S0 lines | Now | Δ | Evidence of *when* |
|---|---:|---:|---:|---|
| `src/lucca/brain/server_ctl.py` | 336 | 346 | +10 | **after S1**: artefact `S1_15a_launch_cmd_from_code.txt` (00:28Z) shows the then-code emitting `--log-format json`, absent from the current `build_launch_command()`; `S1_SUMMARY` §4.1 records S1-era stderr→DEVNULL, current code redirects stdout+stderr to `logs\llama-server.log` (`server_ctl.py:320-327`) |
| `src/lucca/main.py` | 150 | 180 | +30 | after S0 (tracked-file line delta); `git status` shows `M` both at S0 and now, so timing vs S1 is not provable from line counts alone; the added block is the boot-failure log-tail printer (`main.py:123-133`) which S2a's F-CORE-012 (written against the pre-change behaviour "stderr discarded, blind 60 s wait") does not describe |
| `scripts/test_s1_startup.py` | 51 | 49 | −2 | after S0 — newly `M` in `git status` (S0's porcelain did not list it); content deltas not identified |

`config/persona.toml` (20), `config/intents.toml` (16), `config/tool_whitelist.toml` (27), `docker/toolsrv/server.py` (177), `packaging/build_exe.py` (83): unchanged vs S0.

## 4. Conclusion

1. The frozen-tree violation (F-BRAIN-008) is **real but narrow**: `server_ctl.py` was demonstrably changed after the S1 capture window (flag removal + log-file redirect — a coherent fix of F-CORE-012's mechanism), and `main.py` + `scripts/test_s1_startup.py` changed after S0 (main.py's change is what F-CORE-012's current text half-describes). All other in-scope files are unchanged since S0.
2. All S2a/S2b `file:line` citations remain valid **for the current tree**; S1-era behavioural descriptions in `core.md` F-CORE-012 ("stderr is discarded") match the pre-change state and should be read as historical (S1 artefacts are the evidence).
3. Re-baselining (a full S0 redo) is **not required**: the delta is three files, fully characterised above. Subsequent area subtasks (MEM/REAS/ROUT/SBX/SENS/UI/TEST) audit the current tree with this document as the delta record.
