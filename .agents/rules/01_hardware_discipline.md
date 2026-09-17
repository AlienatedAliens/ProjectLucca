# Rule 01: Hardware Discipline & Compute Placement

1. **dGPU (RTX 5080 16GB VRAM, Blackwell sm_120):**
   - Strictly reserved for Ultravox 8B (vLLM) and its KV cache.
   - Target VRAM ceiling: $\le 9.8\text{GB}$.
   - CUDA version: 12.8+.

2. **Intel NPU (Arrow Lake Core Ultra 9 275HX):**
   - Exclusively accessed natively on Windows 11 via OpenVINO (`device="NPU"`).
   - Workloads: Kokoro TTS (INT8), Silero VAD / Whisper (logging), and ModernBERT feature extractor.
   - **Never run NPU workloads inside WSL2 or Docker.**

3. **System RAM (16GB Shared Pool):**
   - WSL2 memory must be clamped to 4.5GB (`4608MB`) via `.wslconfig`.
   - Playwright instances inside Docker must be headless, single-tab, and destroyed after each tool call.

4. **CPU (Arrow Lake 24 Cores):**
   - Hosts Orchestrator, Micro-Scheme LISP engine, ChromaDB, and XGBoost/LightGBM inference.
