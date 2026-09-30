# Rule 01: Hardware Discipline & Compute Placement

1. **dGPU (RTX 5080 16GB VRAM, Blackwell sm_120):**
   - Strictly reserved for Gemma-4-12B-Heretic Q6_K (`llama-server.exe`) and its KV cache (`cache-type-k=q8_0`, `cache-type-v=q8_0`).
   - Default context window: 32,768 tokens (32K) in v1.3.0 (16,384 tokens in v1.2 baseline).
   - Dedicated compute mode (`Disp.A: Off`): Windows desktop display offloaded to Intel iGPU, allocating ~9.97 GiB VRAM under 32K context with Flash Attention 2, leaving ~5.95 GiB free physical VRAM headroom.
   - CUDA version: 12.8+ with Flash Attention enabled.

2. **Intel iGPU (Intel Core Ultra 9 275HX Integrated Graphics):**
   - Host display driving Windows 11 desktop and DWM compositor, keeping dGPU free of display overhead.

3. **Intel NPU (Arrow Lake Core Ultra 9 275HX):**
   - Exclusively accessed natively on Windows 11 via OpenVINO (`device="NPU"`).
   - Workloads: Kokoro TTS (INT8), Silero VAD / Faster-Whisper ASR, and 384-D vector embeddings (`all-MiniLM-L6-v2`).
   - **Never run NPU workloads inside WSL2 or Docker.**

4. **System RAM (16GB Shared Pool):**
   - WSL2 memory must be clamped to 4.5GB (`4608MB`) via `.wslconfig`.
   - Playwright instances inside Docker must be headless, single-tab, and destroyed after each tool call.

5. **CPU (Arrow Lake 24 Cores):**
   - Hosts Orchestrator, Micro-Scheme LISP engine, SQLite WAL + `sqlite-vec` + FTS5, and XGBoost/LightGBM inference.
