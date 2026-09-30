# Visual Pipeline Debugger & Forensic Trace Architecture
**Specification 32 // Project Lucca Core Architecture**
**Version:** 1.3.0 Production
**Status:** ACTIVE
**Author:** Google DeepMind / Project Lucca Architecture Team
**Last Updated:** September 30, 2026

---

## 1. Goal & Operational Principles

The **Visual Pipeline Debugger** is a daily development, testing, and benchmarking tool for Project Lucca. It visualizes how an input prompt traverses the cognitive cascade, what transformations each stage performs, and how code recirculates through self-correction loops before materializing into an answer or physical action.

### Key Tenets
* **Daily Workstation Tool:** Built for daily engineering, test analysis, and benchmark evaluation—not a demo prop.
* **Dual Readability:** Designed so that a layman can understand the story in 10 seconds, while an expert can isolate compiler syntax errors, traceback frames, and LaTeX equivalence discrepancies without leaving the screen.
* **The Zero-Simulation Principle:** Every node status, payload, and duration displayed in the UI originates from physical monotonic timestamps (`QueryPerformanceCounter` nanoseconds) and real disk logs. Reconstructed historical records must be explicitly marked `"reconstructed": true` with unmeasured sub-stage durations left blank (`null`), never fabricated.

---

## 2. Concept: Dataflow Graph with Test Probes

The interface adopts a **circuit schematic with test points** mental model:
* **Fixed Dataflow Layout:** Every stage is an interactive component card connected by signal wires.
* **Component Probes:** Clicking any stage card opens a side probe showing:
  - Input payload received
  - Action / transformation performed
  - Output payload emitted (rendered as a before/after diff)
  - Monotonic duration in milliseconds
  - Stderr / Traceback console (if error)
* **Wire Probes:** Clicking any connector wire displays the exact raw payload transmitted along that link.
* **Proportional Latency Encoding:** Component card borders or connector thicknesses scale with duration, making it instantly obvious that 98%+ of latency is GPU neural deliberation rather than container startup.

---

## 3. The 3 Zoom Levels & Dynamic Nomenclature

The debugger provides a **Plain / Technical** nomenclature toggle. Stage names and summaries are stored as data definitions rather than hard-coded strings.

### Stage Nomenclature Mapping

| Stage ID | Technical Name | Plain Name (Layman Verb) | What Happened (Curious User) | Subsystem & Silicon |
| :--- | :--- | :--- | :--- | :--- |
| **Tank 1** | Ingestion & Demulsifier | **Hears the question** | Receives audio stream or chat text; checks voice activity | PortAudio / Faster-Whisper on Intel AI Boost NPU |
| **Tank 2** | Conformal Intent Valve | **Checks confidence to answer** | Evaluates safety non-conformity $\hat{q}_\alpha$; detects emergency interrupts | ConformalGovernor on Intel Core Ultra 9 275HX |
| **Tank 3** | MicroScheme Centrifuge | **Tries exact math first** | Evaluates deterministic Lisp S-expressions without neural weights | MicroScheme AST on Intel Core Ultra 9 275HX |
| **Tank 4** | Context Infusion | **Recalls what she knows** | Blends persona, silicon telemetry, tool registry, and Belnap ledger | PromptBuilder & SQLite index |
| **Tank 5** | Neural Deliberation Boiler | **Thinks it through and writes code** | Autoregressive decoding at ~50.23 tok/s; synthesizes Python PAL script | `gemma-4-12b-heretic-Q6_K.gguf` on RTX 5080 Laptop GPU |
| **Tank 6** | Sandbox Execution Turbine | **Runs the code safely** | Executes Python in isolated container with resource caps | Docker `lucca-file-sandbox` in WSL2 Ubuntu |
| **Tank 6b** | Recirculation Loop | **Fixes mistakes and tries again** | Detects tracebacks, injects compiler error into Turn 2 prompt | 2-Turn Feedback Governor |
| **Tank 7** | Purifier & Equivalence Grader | **Cleans up and checks answer** | Strips scratchpads; runs Belnap verification & SymPy normalization | ResponseCleaner & SymPy Grader |
| **Tank 8** | Acoustic Turbine & Speech Sinks | **Speaks and animates UI** | Kokoro-82M TTS audio waveform synthesis & PyQt6 sprite updates | Kokoro ONNX on CPU + Intel Graphics iGPU *(companion mode only; bypassed in benchmarks)* |
| **Tank 9** | Autobiographical WAL Basin | **Remembers what happened** | Commits complete transaction envelope to persistent SQLite WAL | SQLite WAL Engine on NVMe SSD |

### The 3 Zoom Levels
1. **Level 1 (The Story):**
   - Natural language, template-driven status caption:
     - *On Success:* `"She wrote a Python solution, ran it in the sandbox, and verified the answer."`
     - *On Self-Correction:* `"She wrote code, it crashed with a syntax error on line 19, she diagnosed the traceback, fixed it, and verified the answer."`
     - *On Equivalence Miss:* `"She calculated the correct mathematical value, but the grader expected LaTeX notation."`
   - Visible "Try Again" recirculation arrow with attempt counter.
2. **Level 2 (What Happened Here):**
   - Per-stage summary cards: `"Got: problem statement. Did: generated SymPy script. Passed on: 12 lines of code."`
   - Direct retry diff view highlighting the exact code correction (e.g. `2y` $\to$ `2*y`).
3. **Level 3 (Raw Expert):**
   - Complete tokenized prompt payload, decode throughput (tok/s), full Docker stderr traceback, exact nanosecond monotonic timings, git commit SHA, context size (16K vs 32K), model file hash, and strict vs lenient verdicts.

---

## 4. Live Monitor Features

1. **Active Dataflow Graph:** Displays cards with real execution times (`0.15ms`, `180ms`, `8.4s`) and status borders (green = pass, amber = retried, red = error).
2. **Real-Time Execution Waterfall:** Live proportion bar showing:
   $$\text{[Neural Deliberation: 98.2\% (18.2s)]} \quad \text{[Docker Sandbox: 1.5\% (0.19s)]} \quad \text{[Grader: 0.3\% (0.04s)]}$$
3. **Streaming Work Console:** Shows the Python script as tokens decode, plus Docker stderr traceback and expected-vs-predicted diff immediately upon return.
4. **Stacked Failure Breakdown:** Separates errors by `failure_class`:
   - `runtime_crash`: SyntaxError, IndentationError, TypeError in Docker.
   - `equivalence_format_miss`: Mathematical match rejected due to LaTeX notation (`20000/pi` vs `\frac{20000}{\pi}`).
   - `prose_slip`: Output formatting or missing print.
   - `genuine_derivation_miss`: Incorrect mathematical calculation.
5. **400-Cell Interactive Matrix:** Ribbon of 400 color-coded cells allowing 1-click navigation to any trace.
6. **Physical Telemetry Gauges:** Live sampling of RTX 5080 Laptop GPU from `nvidia-smi`:
   - VRAM: Exact MiB and GiB (`10,064 MiB / 16,303 MiB (9.83 GiB / 15.92 GiB)`).
   - Power Draw: Current watts vs. 175W laptop TGP ceiling (`156 W / 175 W`).
   - Temperature: Thermal logging to detect throttling across multi-hour runs.
   - GPU Utilization: Decode compute percentage (`92–98%`).

---

## 5. Trace Schema & Data Storage

### 5.1 Configuration Guard & Ledger Separation
* Benchmark runs are logged to `logs/telemetry/flow_traces.jsonl` (gitignored).
* Companion daily sessions are logged to `logs/telemetry/companion_traces.jsonl`.
* Every trace record embeds a configuration block:
  ```json
  "config": {
    "config_label": "v1.2-baseline-heldout-400",
    "git_commit": "37fde25",
    "context_size": 16384,
    "model": "gemma-4-12b-heretic-Q6_K.gguf",
    "hardware": "NVIDIA GeForce RTX 5080 Laptop GPU (16 GB) + Intel Core Ultra 9 275HX"
  }
  ```
* **Resume Safety:** Passing `--resume` strictly verifies that the active run's configuration hash matches the checkpoint; if context size, model, or prompt template changed, `--resume` refuses to continue to prevent mixing experimental regimes.

### 5.2 Forensic Trace Record Format
```json
{
  "trace_id": "trace-math500-129-historical",
  "timestamp": "2026-09-29T19:30:00Z",
  "reconstructed": true,
  "config": { ... },
  "task_info": {
    "index": 129,
    "total": 400,
    "subject": "Precalculus",
    "level": 4,
    "problem": "...",
    "expected_ans": "288 \\pi"
  },
  "predicted_ans": "",
  "expected_ans": "288 \\pi",
  "passed": false,
  "verdict": {
    "strict_pass": false,
    "lenient_pass": false,
    "failure_class": "runtime_crash"
  },
  "total_latency_s": 22.59,
  "tags": ["reconstructed_from_task_9624"],
  "tanks": [
    {
      "tank_id": "tank_1_ingestion",
      "tank_name": "Input Ingestion & Demulsifier",
      "subsystem": "Task Streamer / UTF-8 Ingestion",
      "status": "PASS",
      "duration_ms": null,
      "unmeasured": true,
      "received": "...",
      "action": "Ingested competition problem",
      "output": "...",
      "stderr": ""
    },
    {
      "tank_id": "tank_6_sandbox_turbine",
      "tank_name": "Sandbox Execution Turbine",
      "subsystem": "DockerRPCTransport (WSL2)",
      "status": "ERROR",
      "duration_ms": null,
      "unmeasured": true,
      "received": "...",
      "action": "Executed in Docker container lucca-file-sandbox.",
      "output": "",
      "stderr": "File \"<stdin>\", line 19\n    d2_sq = (x - 2y + z)**2 / 6\n                 ^\nSyntaxError: invalid decimal literal"
    }
  ]
}
```

---

## 6. Replay Modes & Safety Isolation

The system supports two distinct replay modes:
1. **Playback Mode (Inspect Only):**
   - Redisplays recorded stages, code, tracebacks, and waterfall timelines. Purely read-only; zero compute or side effects.
2. **Re-Execution Mode (Debugging & A/B Testing):**
   - Re-runs the prompt through the active engine code to test a bugfix.
   - **Rule 1 (Autobiographical Isolation):** Replays must **NEVER** write to SQLite WAL or episodic memory. All re-executions run with `WAL_READ_ONLY = True` to prevent contaminating Lucca's real memory with duplicate turns or revised beliefs.
   - **Rule 2 (Tool Dry-Run Mocks):** Side-effecting tools (`file_write`, `clipboard_read`, `schedule_event`, system execution) are intercepted and mocked in dry-run mode. Class C confirmation gates apply.
   - **Rule 3 (GPU Non-Determinism):** CUDA multi-threaded floating-point reductions exhibit minor non-associativity across runs. Same-seed replays are treated as "same inputs," not bit-identical guarantees.

---

## 7. Hardware & Performance Ground Truth

* **Host Machine:** MSI Vector 16 HX AI.
* **Processor (CPU):** Intel Core Ultra 9 275HX (24 Cores: 8 Performance Cores, 16 Efficient Cores).
* **Neural Processing Unit (NPU):** Intel AI Boost NPU (dedicated Whisper ASR & embeddings).
* **Discrete GPU (dGPU):** NVIDIA GeForce RTX 5080 Laptop GPU (16.0 GB GDDR7, 175W TGP). Configured in dedicated compute mode (`Disp.A: Off`).
* **Integrated GPU (iGPU):** Intel(R) Graphics (drives Windows 11 desktop and PyQt6 compositor).
* **Measured Decode Speed:** **50.23 tok/s** on `gemma-4-12b-heretic-Q6_K.gguf` under 16K context with FlashAttention-2.
* **Measured Resident VRAM:** **10,064 MiB (9.83 GiB / 15.92 GiB)** allocated, leaving 6,239 MiB (38.3%) free physical VRAM headroom.
* **Zero AMD/Radeon silicon exists.**

---

## 8. Acceptance Verification

1. **The 10-Second Test:** A non-technical user looking at the Level 1 story view can immediately state what happened: *"She wrote code, hit a typo in line 19, fixed it, and got the right answer."*
2. **The Expert Test:** An engineer can identify whether a problem failed due to a missing asterisk, an unclosed bracket, or a LaTeX fraction mismatch in $<5$ seconds.
3. **Zero-Simulation Audit:** All stage durations trace back to physical monotonic measurements; reconstructed data is explicitly flagged with null sub-stage timings.
4. **Static Gate Verification:** Verified 100% green against all 24 static architectural gates (`pytest tests/test_static_gates.py`).
