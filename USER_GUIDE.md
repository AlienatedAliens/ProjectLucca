# Project Lucca — User Guide

Welcome to the Project Lucca User Guide.

The authoritative, line-by-line verified capabilities manual and testing protocol for Project Lucca is maintained in the documentation directory:

👉 **[`docs/USER_GUIDE_WHAT_LUCCA_DOES.md`](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md)**

---

## Quick Reference & Table of Contents

1. **[0. The One-Paragraph Summary](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md#0-the-one-paragraph-version)**: What Lucca is, how the local 12B neural brain (`gemma-4-12b-heretic-Q6_K.gguf`) operates under the $\le 12.8$ GB resident VRAM clamp on the RTX 5080 Laptop GPU, and how the deterministic reflex and reasoning layers guard it.
2. **[1. Starting Her (Quick-Start)](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md#1-starting-her-quick-start)**:
   - WSL2 and Docker setup
   - Running the 10-point system environment and hardware diagnostic (`Lucca.exe --check` or `python -m lucca.admin env-check`)
   - Launching the system tray sprite
   - Push-to-talk (Right Alt / `alt_gr`), barge-in interruption (<50 ms), and emergency stop commands (<150 ms)
3. **[2. What She Does Today](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md#2-what-she-does-today--and-what-she-actually-does-when-you-ask)**:
   - Conversation, affect prosody, and honest abstention
   - Fast deterministic token recall without LLM invocation (`src/lucca/reasoning/recall.py`)
   - The 24 native sandboxed tools (body, host perception, shared boundary, grounded commit)
   - Rung A1 autobiographical memory (`ASSISTANT_UTTERANCE`, `ASSISTANT_ACTION`, `SELF_HISTORY`)
   - The 15 active MicroScheme rules and forward-chaining assertion engine
    - **Three-Track Cognitive & Academic Benchmark Verification** (Track 1 `SPEC-BENCH-100-v1.0` 91%; Track 2 Canonical HumanEval 95.73%, GSM8K PAL 100%, BBH 92.4%; Track 3 GSM-Symbolic 100%, HumanEval-Plus 91.46%, MATH-500 77% strict / 87% SymPy)
    - **v1.3.0 Structural Compiler & 2-Tier Neurosymbolic Execution** (Tolerant AST extractor with 0.0% empty code residual, Turn-1 compiler preflight, 2-turn execution feedback recovering 85.11% of baseline runtime crashes, and 3-stage CAS equivalence grader)
4. **[3. The Two Big Architecture Claims & How to Test Them](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md#3-the-two-big-claims--how-true-are-they-at-l2-and-how-do-you-test-them)**:
   - Claim A: Federated cognitive architecture & independent skill registration
   - Claim B: Reasoning onion & bidirectional substrate interaction (12-step verification battery)
5. **[4. Capability Status Matrix](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md#4-not-yet--and-when)**: Shipped capabilities (WO-20 through WO-28) vs. deferred roadmap items.
6. **[5. Onboarding Protocol](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md#5-how-to-begin--a-protocol-that-is-also-the-evidence-the-roadmap-needs)**: 4-session protocol for building real usage history, activating rule induction, and establishing habit promotion.
7. **[6. Troubleshooting & Diagnostics](./docs/USER_GUIDE_WHAT_LUCCA_DOES.md#6-if-something-is-wrong)**: Reason codes, CLI rule inspect, finding templates, and the **Visual Pipeline Debugger** (`http://localhost:8765`) for real-time 9-tank dataflow inspection.
