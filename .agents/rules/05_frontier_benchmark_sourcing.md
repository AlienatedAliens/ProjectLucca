# Rule 05: Modern Frontier Benchmark Sourcing & Comparative Rigor

1. **Mandatory Live Sourcing Before Any Comparison:**
   - Before writing any comparative evaluation, architectural positioning, or performance claims comparing Project Lucca to external frontier cloud models or agentic harnesses, the agent **MUST** actively search the web for contemporary late-2026 state-of-the-art benchmarks.
   - Never rely on static training memory, obsolete historical assumptions, or legacy 2023–2024 baselines (e.g., GPT-4, Claude 3.5 Sonnet, Gemini 1.5, or basic GSM8K/MMLU) as representations of current frontier capability.

2. **Required Contemporary Model Targets:**
   - Any comparison against the proprietary frontier must reflect late-2026 models and active checkpoints:
     - **Anthropic:** Claude Opus 5 / 5.5, Claude Fable series, Claude Code agentic CLI.
     - **OpenAI:** GPT-5.6 Sol, GPT-6 Astra / Sol series, o-series test-time compute architectures.
     - **Google:** Gemini 3.8 Flash, Gemini 4 / 4-Argon series, Gemini 3.1 Pro.
     - **Open-Weights Vanguard:** DeepSeek-V4-Pro / V4-Pro-Max, Qwen 3.8-Max / Qwen 3 Reasoning.

3. **Required Benchmark Standards (Post-Saturation Suites):**
   - Comparisons must prioritize benchmarks designed to resist saturation and contamination:
     - **Software Engineering:** *SWE-bench Pro* and *SWE-bench Verified* across dedicated harnesses (`mini-SWE-agent`, `OpenHands`, `Devin`, `Claude Code`), noting benchmark saturation (>95% on SWE-bench Verified vs 20–45% on SWE-bench Pro).
     - **Academic & Scientific Reasoning:** *GPQA Diamond* (PhD-level Google-proof, 94–96% frontier bracket), *FrontierMath* (Epoch AI Tier 4 research mathematics), and competition *AIME* (with test-time compute).
     - **Agentic Multi-Step & OS Control:** *GAIA* (multi-modal tool orchestration), *OSWorld* (full desktop OS control), and *WebArena* (end-to-end browser workflows).
     - **Abstract Generalization:** *ARC-AGI-2* (compositional reasoning, ~37–54%) and *ARC-AGI-3* (interactive dynamic environments).

4. **Symmetric Architecture Disclosure:**
   - When comparing Lucca to external systems, explicitly distinguish between:
     - **Raw Next-Token Inference:** A bare model generating direct text without execution feedback.
     - **Test-Time Compute (CoT / Thinking):** Models utilizing internal reasoning tokens prior to response.
     - **Agentic Scaffolding:** Models operating inside iterative loops with code sandboxes, SMT solvers, compilers, or programmatic search (e.g., Z3, SymPy, Docker CEGIS, OpenHands, Devin).
