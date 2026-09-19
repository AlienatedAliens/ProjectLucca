# Rule 01: Hardware Discipline & Compute Placement

1. **dGPU (RTX 5080 16GB VRAM, Blackwell sm_120):**
   - Strictly reserved for Mistral NeMo 12B Instruct Abliterated Q6_K (`llama-server.exe`) and its 16K KV cache (`cache-type-k=q8_0`, `cache-type-v=q8_0`).
   - Target VRAM ceiling: $\le 12.5\text{ GB}$ (12,800 MB), leaving $\ge 3.5\text{ GB}$ headroom for Windows desktop and browser acceleration.
   - CUDA version: 12.8+ with Flash Attention enabled.

2. **Intel NPU (Arrow Lake Core Ultra 9 275HX):**
   - Exclusively accessed natively on Windows 11 via OpenVINO (`device="NPU"`).
   - Workloads: Kokoro TTS (INT8), Silero VAD / Faster-Whisper ASR, and 384-D vector embeddings (`all-MiniLM-L6-v2`).
   - **Never run NPU workloads inside WSL2 or Docker.**

3. **System RAM (16GB Shared Pool):**
   - WSL2 memory must be clamped to 4.5GB (`4608MB`) via `.wslconfig`.
   - Playwright instances inside Docker must be headless, single-tab, and destroyed after each tool call.

4. **CPU (Arrow Lake 24 Cores):**
   - Hosts Orchestrator, Micro-Scheme LISP engine, SQLite WAL + `sqlite-vec` + FTS5, and XGBoost/LightGBM inference.
