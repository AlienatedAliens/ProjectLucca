# 17 — Project Lucca: What It Is, What v1.0 Delivers, Where It Can Go, and How It Compares

Audience: the project owner, future collaborators, and anyone deciding whether Lucca is worth their time. Plain language; engineering references in brackets point at the specs.

---

## 1. What Project Lucca is

Lucca is a **local desktop companion** that lives on one laptop, listens when you hold a key, answers in a natural voice within about half a second, can do a small set of real things on your computer inside a locked box, and **remembers only what it can prove you told it or what it verifiably did**. Over weeks it notices what you repeatedly ask for and proposes to do those things automatically — but only after it has watched itself get them right, silently, several separate times, and only with your permission to keep the habit.

It is a **research project** first. The research question is not "can a laptop run a chatbot" — that's settled. The question is:

> *Can a small, fully local agent be given memory and the ability to learn habits **without** inheriting the two failures that make today's assistants untrustworthy: remembering things it made up, and doing things it wasn't asked to?*

Everything unusual about Lucca's design exists to answer that question honestly:

- **Nothing leaves the machine.** No cloud model, no telemetry, no account. [spec 11 §8, spec 12]
- **Provenance-gated memory.** Every memory carries a signed record of where it came from: your verbatim words, a structured fact grounded word-for-word in your words, or a verifiable outcome of a tool. The model's own narration has no signer and therefore *cannot* become memory, by construction rather than by prompt. [ADR-006, spec 03]
- **Compiled habits with a statistical gate.** Repeated behaviour becomes a small, human-readable rule only after ≥ 5 distinct successes with zero failures and a passing regression suite; one failure in production demotes it; you can retire it by voice. [ADR-007, spec 05]
- **Two sandboxes, never one.** The container that can touch your files has no network; the one with network has no files. Anything that writes or launches asks you aloud first. [ADR-003/004, spec 09]
- **Honest numbers.** Latency, memory, and accuracy claims are only ever taken from the system's own traces and benchmark files; no threshold is loosened to pass a test. [spec 10, matrix v2, AGENTS.md]

Hardware target: one MSI Vector 16 HX AI (RTX 5080 16 GB, Intel NPU, 16 → 64 GB RAM). The design deliberately spreads work across GPU (language model), NPU (hearing, speech, embeddings), and CPU (everything symbolic) so the whole companion fits on a machine you already own.

---

## 2. What version 1.0 delivers

**Definition:** v1.0 = Phases 0–3 complete and signed off, plus the Phase 4 logging pipeline running. In one line: **Lucca can talk, act, and remember — and is collecting the data it needs to start learning.** (Phase 3 is in progress at the time of writing.)

| Capability | What you experience | Sign-off evidence |
|---|---|---|
| **Talk** (Phase 1) | Hold right-Ctrl, speak, release. First audio typically ~0.5 s later (≤ 0.6 s median gate). Natural voice (Kokoro). Interrupt at any time by pressing again. 2D sprite reacts. | latency reports in both audio and transcript modes; 10-turn no-desync; VRAM ≤ 9.5 GB; barge-in ≤ 30 ms to silence |
| **Act** (Phase 2) | Read/search/write files you place in `C:\ProjectLucca\inbox`; summarise a public web page; open whitelisted apps. Every write/launch is confirmed by voice, naming the real target. | positive-controlled egress test; path-traversal fuzzing; forbidden-sequence refusal; container spec snapshot |
| **Remember** (Phase 3) | "Remember that…" facts survive restarts; "I moved to Berlin" supersedes Seattle while keeping history; "forget that" works and is reversible for 30 days; retrieval finds exact identifiers and paraphrases; a full export of everything it knows is one command. | hallucination-write test end-to-end (0 rows written); Hit@1 ≥ 0.93 on identifiers; Recall@3 ≥ 0.90 on paraphrases; supersession + forget tests; integrity/backups |
| **Observe** (Phase 4 pipeline) | Invisible to you, but every turn is logged with its routing decision and an automatically derived "was that right?" label, ready for learning. | one decision row + one label per turn; labeling function unit-tested |

**What v1.0 deliberately does not do:** learn habits yet (that is v1.1 = Phase 5, and it needs weeks of your real use), replace its simple router with a trained one (v1.2 = Phase 6, needs ~600 real interactions), see your screen, run on anything but this laptop, serve more than one person, or speak unprompted.

---

## 3. What it becomes as it grows with you

Growth in Lucca is **curated, inspectable, and reversible** — the opposite of a model silently drifting. Three things accumulate:

1. **A memory that is provably yours.** Every fact traces to a sentence you said or a thing it verifiably did. After months, Lucca knows your people, projects, preferences, and the shape of your days — and you can read the whole thing as a text file. The knowledge graph is bi-temporal, so it also knows what *used* to be true.

2. **A library of habits it earned.** Each promoted rule is a few lines of readable Scheme: *when* (a pattern in what you said and the state of your machine) → *plan* (a tool call and a sentence). Habits accumulate one at a time, each announced, each revocable. In effect Lucca compiles the boring, repeated parts of working with you into deterministic, sub-millisecond shortcuts, leaving the language model for the genuinely new.

3. **A router that learns from your corrections.** Every "no" and every interruption becomes a label. Once there is enough data, a small, calibrated classifier takes over routing and uses a conformal guard to fall back to the safe path when unsure — with coverage guarantees, not vibes.

Beyond those three built-in growth channels, the architecture leaves clean seams for:

- **A second, slower brain** (after the 64 GB upgrade): a much larger model, resident in RAM, woken only when you're idle, to propose better rules and review extracted facts — quality up, live latency untouched. [ADR-010 §4]
- **Affect that is honest** — a small, explainable mood state driven by real signals, never a claimed feeling, never a stored fact. [guide 16 §4, ADR-009 proposed]
- **Vision** (screen/OCR), a richer avatar (Live2D/VRM), coreference across turns, non-English, domain allow-lists, stronger sandboxes. [phase plan §Deferred]

The research payoff, if it works: a demonstration that **trust in a personal agent can be an engineering property** — enforced by types, signatures, statistical gates, and containers — rather than a hope about model behaviour.

---

## 4. How Lucca compares to what exists

### 4.1 Big-tech voice assistants (Alexa, Google Assistant/Gemini Live, Siri, Copilot Voice, ChatGPT Advanced Voice)

| | Them | Lucca |
|---|---|---|
| Where it runs | Cloud (sometimes hybrid) | Entirely on your laptop |
| Latency | 300–800 ms, network-dependent | ~500 ms, network-independent |
| Model quality | Frontier-class | 8B-class: fine for conversation and tool use, not frontier reasoning |
| Memory | Opaque; "memory" features are provider-controlled, mostly LLM-summarised | Provenance-gated, exportable, reversible; model narration can't enter it |
| Acts on your PC | Limited or none (Copilot is expanding, with mixed reception) | Yes, in split sandboxes with spoken confirmation |
| Learns your habits | Only via provider-side personalisation | Locally, as readable rules you approve |
| Privacy | Data leaves device; policies change | Nothing leaves; no telemetry |
| Setup | Zero | Significant: specific hardware, WSL2 + Docker CE, model downloads |

**Honest read:** they win on intelligence and convenience; Lucca wins on privacy, control, agency on the local machine, and *auditability*. Windows Recall's reception in 2024–25 showed the market's appetite for local-only, inspectable memory — and its intolerance for "trust us."

### 4.2 Open-source local companions (Open-LLM-VTuber, Amica, AIRI, Neuro clones)

These are Lucca's closest relatives: local voice loop, avatar, pluggable ASR/LLM/TTS. Several are more polished visually (Live2D/VRM) and have larger communities. Differences:

- They treat **memory as a summary the LLM writes** — exactly the hallucination path Lucca forbids.
- None has a **statistically gated habit-learning loop**, a provenance model, a threat model, or split sandboxes.
- Most run as one Python process; Lucca's four-process design keeps audio real-time and isolates crashes.
- Lucca is currently uglier and harder to install. That is a fixable gap; theirs are architectural.

### 4.3 Agent memory products (Letta/MemGPT, mem0, Zep/Graphiti)

Serious engineering, and Lucca borrows from them (tiered memory; bi-temporal edges). They are **libraries for developers building cloud agents**; they store whatever the LLM extracts and trust it. Lucca's contribution is the *gate in front of them*: quote-grounding, signed provenance, and a refusal path. A "provenance-gated memory" library extracted from Lucca would be a plausible standalone artefact.

### 4.4 Autonomous agent frameworks (OpenHands, Devin-like tools, Claude Code / Codex CLI)

Far more capable at *doing*; they run long tool chains with high autonomy. Lucca is intentionally the opposite: short chains (≤ 4 tool calls/turn), spoken confirmation for anything irreversible, forbidden sequences, no autonomous loops. It is a companion, not a contractor.

### 4.5 Character/companion apps (Replika, Character.ai, Talkie)

Optimised for emotional engagement, cloud-hosted, monetised through attachment. Lucca explicitly refuses to *claim* feelings, exposes its mood state's causes, and keeps your data on your disk. Less sticky by design; more trustworthy by design.

### 4.6 Where Lucca is genuinely differentiated

1. Provenance-gated memory enforced structurally (no known consumer or OSS companion does this).
2. Compiled, human-readable habits behind a statistical promotion gate (the Soar/ACT-R idea, made safe for an LLM era).
3. Split-sandbox agency with spoken confirmation and forbidden sequences.
4. Honest, trace-derived performance reporting as a hard rule.
5. All of it on one consumer laptop with no cloud dependency.

Where it is behind: raw intelligence, polish, install friction, breadth of tools, vision, platform reach.

---

## 5. Monetisation — what to watch before deciding

Decide nothing until Phases 4–5 have run on real usage. The signals that would say "this is compelling":

| Signal | Where it's measured | "Compelling" looks like |
|---|---|---|
| You keep using it without forcing yourself | `decisions` per day over 8 weeks | daily use persists after novelty (week 3+) |
| Habits emerge and you keep them | `rules list` | ≥ 3 promoted rules you *didn't* retire within a month |
| Corrections fall | `router report` label ratios | NEG label rate trending down session over session |
| Memory feels right | your own `memory export` review | you rarely delete; recalls are accurate; supersession behaves |
| It changes how you work | qualitative | you route real tasks through the inbox because it's easier |

If those hold, plausible paths — each with a caveat:

- **Open-core companion**: free local core; paid curated model bundles, avatar packs, one-click installer, hardware-tuned profiles. *Caveat:* install friction must be solved first; Llama 3.1 Community License is fine at this scale but requires attribution; PyQt6 is GPL — switch to PySide6 (LGPL) before distribution [ADR-005].
- **"Trusted memory" as a library/SDK**: the provenance gate + grounding + bi-temporal store as a standalone package for agent developers. *Caveat:* competes with well-funded memory startups; the differentiator is the *gate*, which must be demonstrably valuable (the hallucination-write benchmark becomes the pitch).
- **Enterprise/regulated variant**: audit log, exportable provenance, no-cloud guarantee are exactly what compliance-sensitive buyers ask for. *Caveat:* long sales cycles; would need multi-user and non-Windows work.
- **Research output**: write-ups/benchmarks on provenance-gated memory and gated habit compilation have standalone value and cost nothing extra given the trace/report discipline already in place.

Non-negotiable regardless of path: the local-first and no-telemetry invariants are the product. Monetising by weakening them would remove the reason Lucca exists.

---

## 6. One-paragraph version

Project Lucca is a fully local, push-to-talk desktop companion for a single high-end laptop that answers in about half a second, can safely read, write, fetch, and launch inside split sandboxes with spoken confirmation, and remembers only what it can prove — your verbatim words, facts grounded in them, or verified tool outcomes — never its own narration. Version 1.0 delivers talking, acting, and remembering with every performance claim taken from the system's own traces. As you use it, it earns human-readable habits through a statistical gate you can veto, and learns routing from your corrections with calibrated fallback. Against cloud assistants it trades raw intelligence for privacy, agency, and auditability; against open-source companions it adds the trust machinery none of them have. It is a research project into whether trust in a personal agent can be engineered rather than hoped for — and, if daily use proves it compelling, a candidate for an open-core product or a standalone trusted-memory library.
