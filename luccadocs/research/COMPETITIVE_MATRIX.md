# Project Lucca — Competitive Matrix (User-Job Comparison)

**Doc ID:** `RES-COMP-MATRIX-v0.1`
**Created:** 2026-11-01 (WO-39 planning set)
**Status:** SKELETON — Lucca column filled from [`../specs/CAPABILITY_REGISTER.md`](../specs/CAPABILITY_REGISTER.md); **every competitor cell is `NV` (not verified) until live-sourced** per the protocol in §2.
**Governing rule:** `AGENTS.md` Rule 05 (live sourcing of late-2026 products only; no 2023–2024 baselines) and Rule 8 (no unverified labels).

---

## 0. Why this is a skeleton, not a finished comparison

On 2026-11-01 the live-sourcing tools available to the planning session could not produce verifiable late-2026 feature data: Nia deep research is not on the current plan, and quick search returned link lists without page content. Rather than fill cells from model memory (which would be stale and violate Rule 05), this document fixes **the columns, the sourcing protocol, and the candidate list**, and records honestly that the cells are unverified.

What *can* be said without live data is stated only at category level in §4, and is explicitly labelled as hypothesis.

---

## 1. Columns = user jobs (shared spine with the capability register)

| Column | Register ID(s) | Question the cell answers |
|---|---|---|
| Talk | `CAP-VOICE` | Real-time voice? Latency class? Interruptible? |
| Presence | `CAP-PRESENCE` | Push-to-talk / wake word / always-on? Which devices? |
| Remember you | `CAP-MEM-U` | Persistent memory? User can inspect & delete individual items? |
| Self-record | `CAP-MEM-S` | Can it truthfully answer "did you actually do X?" from records? |
| Abstain | `CAP-ABSTAIN` | Documented refusal to invent the past? |
| Know you | `CAP-KNOWYOU` | Inferred preferences/goals? With user confirmation? |
| Work & code | `CAP-WORK`, `CAP-CODE` | File work, code execution — sandboxed? |
| Research | `CAP-RESEARCH` | Web search/fetch; injection/exfiltration defences documented? |
| See | `CAP-SEE` | Screen/image understanding — local or cloud? |
| Act on PC | `CAP-HOST` | App launch, GUI automation, mail/calendar integrations? |
| Remind | `CAP-REMIND` | Reminders that actually fire? |
| Proactive | `CAP-PROACT` | Initiates without being asked? |
| Learn | `CAP-LEARN` | Learns new skills/routines; how gated? |
| Honest actions | `CAP-HONEST` | Mechanism preventing claims of actions not performed? |
| Privacy | `CAP-PRIVACY` | Runs fully local/offline? What leaves the device? |
| Persona control | — | Owner control over persona/content policy? |
| Setup cost | — | Hardware required; install complexity; price. |

---

## 2. Sourcing protocol (how a cell becomes non-`NV`)

1. **Source types allowed:** vendor docs/help center, official changelog or release notes, repo README/docs at a pinned commit, or a hands-on test by the owner (recorded as `HANDS-ON`).
2. **Every filled cell carries:** value, source URL (or test log path), access date, and product version/commit. Format: `value [S#]` with `S#` in the §5 source ledger.
3. **No inference from marketing adjectives.** "Remembers you" ≠ "user can inspect and delete individual items". If the doc does not say it, the cell stays `NV` or becomes `NOT DOCUMENTED`.
4. **Allowed cell values:** `YES [S#]`, `NO [S#]`, `PARTIAL: <what> [S#]`, `NOT DOCUMENTED [S#]`, `NV`.
5. **Freshness:** cells older than 90 days revert to `STALE` on the quarterly refresh (§6).
6. **No benchmark-score columns.** Competitor products rarely publish comparable numbers, and comparing local Gemma tiers to frontier cloud models is not like-for-like (Rule 05 parity disclosure). Capability *presence and quality of guarantee* is compared, not leaderboard scores.

---

## 3. Matrix

Legend: Lucca cells use register rungs (L0–L4, see register §1). Competitor cells are `NV` until §2 is satisfied.

### 3.1 Lucca vs. cloud frontier assistants

| Job | **Lucca** | ChatGPT | Gemini | Claude | Microsoft Copilot | Apple Siri / Apple Intelligence |
|---|---|---|---|---|---|---|
| Talk | L3, PTT, barge-in | NV | NV | NV | NV | NV |
| Presence | L2, one Windows laptop, PTT only | NV | NV | NV | NV | NV |
| Remember you | L3, every item inspectable/deletable (admin CLI, settings) | NV | NV | NV | NV | NV |
| Self-record | L2→L3, signed receipts; own speech excluded from evidence | NV | NV | NV | NV | NV |
| Abstain | L3, deterministic recall + conformal gate | NV | NV | NV | NV | NV |
| Know you | L1→L2 (inference deliberately gated) | NV | NV | NV | NV | NV |
| Work & code | L3, Docker sandbox, host exec disabled | NV | NV | NV | NV | NV |
| Research | L3, taint + sequence guard | NV | NV | NV | NV | NV |
| See | L2→L3, local OCR + local vision | NV | NV | NV | NV | NV |
| Act on PC | L2, narrow **by design** (no GUI automation/mail/calendar) | NV | NV | NV | NV | NV |
| Remind | **L2** (SQLite persistence + idle heartbeat fire) | NV | NV | NV | NV | NV |
| Proactive | L1→L2 | NV | NV | NV | NV | NV |
| Learn | L2, quarantine + operator promotion | NV | NV | NV | NV | NV |
| Honest actions | **L2** (`WO-42` clause-level NPU `NeuralActionClaimVerifier`: `99.26%` accuracy, `98.73%` recall, `0.58%` FPR on `N=2,022`, `28/28` live 4-model FAC; 30-day dogfood ledger pending for L3) | NV | NV | NV | NV | NV |
| Privacy | L3, fully local product path | NV | NV | NV | NV | NV |
| Persona control | Full owner control (uncensored persona, `D-SOV-01`) | NV | NV | NV | NV | NV |
| Setup cost | High: RTX-class dGPU, 64 GB RAM, WSL2 + Docker | NV | NV | NV | NV | NV |

### 3.2 Lucca vs. open-source local companions & frameworks

| Job | **Lucca** | Project AIRI | Open-LLM-VTuber | Letta (MemGPT) | mem0 | Open Interpreter |
|---|---|---|---|---|---|---|
| Talk | L3 | NV | NV | NV | n/a (library) | NV |
| Presence | L2 | NV | NV | n/a | n/a | NV |
| Remember you | L3 | NV | NV | NV | NV | NV |
| Self-record | L2→L3 | NV | NV | NV | NV | NV |
| Honest actions | L2 | NV | NV | NV | n/a | NV |
| Work & code | L3 sandboxed | NV | NV | NV | n/a | NV |
| Act on PC | L2 narrow | NV | NV | NV | n/a | NV |
| Privacy | L3 local | NV | NV | NV | NV | NV |
| Avatar / embodiment | 2D sprite (PyQt6) | NV | NV | n/a | n/a | n/a |
| Setup cost | High | NV | NV | NV | NV | NV |

Additional candidates surfaced by the 2026-11-01 quick search (unreviewed, include only after a README read): `bo1202/aivy-os`, `RafaelTuber/Mark-XL`, `zarldev/zarl`, the "Alice" desktop AI covered by Bright Coding (2026-09-02).

### 3.3 Lucca vs. cognitive-architecture research systems

Carried from [`2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md`](./2026-10-17_NIA_LIVE_COMPETITIVE_AND_COGNITIVE_ARCHITECTURE_SURVEY.md): `qca-cycle`, `nmem-sym` / `nmem-act`, `agidb`, NeuSymMS, EpisTwin. That survey compared **features from documentation only; none were executed**. Re-use its rows here only with the §2 source format, and mark them `DOC-ONLY` until hands-on.

---

## 4. Category-level hypotheses (to confirm or refute — not claims)

These are the working positioning hypotheses. Each must be confirmed by filling the corresponding cells above before it is used in any paper, README, or pitch.

| # | Hypothesis | Cells that confirm/refute it |
|---|---|---|
| H1 | Cloud assistants lead on model quality, integrations (mail/calendar/docs), cross-device presence, voice polish, and computer use. | 3.1: Talk, Presence, Act on PC, See |
| H2 | Lucca's defensible differentiator is a **fully local companion whose memory and action claims are structurally honest** — signed provenance, own-speech excluded from evidence, receipts-gated action claims. Few or no products enforce this at the storage layer. | 3.1/3.2: Remember you, Self-record, Honest actions, Privacy |
| H3 | H2 is only defensible once `CAP-HONEST` reaches L3. As of `WO-42` (2026-11-06), `NeuralActionClaimVerifier` achieves `99.26%` accuracy (`98.73%` recall, `0.58%` FPR) on `N=2,022` and `28/28` live 4-model FAC interception, leaving only the 30-day daily-use dogfood ledger to close L3. | Register `CAP-HONEST` |
| H4 | Open-source companions lead on avatar/embodiment, open-mic presence, cross-platform support, install ease, and plugin ecosystems; Lucca leads on sandboxing, provenance memory, and honesty architecture. | 3.2 all rows |
| H5 | Lucca's reasoning benchmarks are **not** a competitive differentiator: frontier cloud models dominate them, and companion products do not publish comparable numbers. | Excluded by §2 rule 6 |
| H6 | Lucca's largest gaps vs. every category: reminders (L1), proactivity (L1→L2), "knows you" (L1→L2), presence (L2), setup cost. | Register target profile §7 |

---

## 5. Source ledger

| S# | Product | URL / log path | Accessed | Version | Notes |
|---|---|---|---|---|---|
| — | (empty — populate during first refresh) | | | | |

Quick-search leads recorded 2026-11-01 (not yet read; do not cite as sources until read):
- Open-LLM-VTuber reviews: andrew.ooo, promptquorum.com, ai-uchi.ru
- Project AIRI guide: faycalazib.com
- Bright Coding, "Open-Source Desktop AI with Voice & Memory" (2026-09-02)

---

## 6. Refresh protocol

- **Cadence:** quarterly, plus before any external publication (paper, README positioning, funding doc).
- **Procedure:** for each `NV`/`STALE` cell, find a §2-allowed source → fill with `[S#]` → add a ledger row. Owner hands-on tests (`HANDS-ON`) are preferred for the top-3 competitors per category.
- **Change control:** a hypothesis in §4 may only move to "confirmed" in a PR that cites the filled cells.
- **Tooling note:** live research may use cloud assistants (e.g. Gemini in Antigravity) because it is public-web material only; never paste Lucca memory, keys, or traces into those sessions.
