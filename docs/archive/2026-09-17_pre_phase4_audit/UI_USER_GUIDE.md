# Project Lucca — User Interface Guide & Reference Manual

*A desktop companion powered by Chrono Trigger aesthetics, deterministic MicroScheme reasoning, dual-vector voice synthesis, and real-time multi-substrate hardware telemetry.*

---

## 1. Overview & SNES Chrono Trigger Design System

Project Lucca features an app-wide visual theme inspired by the iconic Super Nintendo (SNES) RPG *Chrono Trigger*:
- **Window Frames**: Triple-layered royal blue gradient (`#1c2e88` -> `#101c54` -> `#081036`) with deep inner drop-shadows.
- **Double Silver Borders**: High-contrast, clean `#f0f4ff` double borders reminiscent of classic SNES dialogue boxes.
- **Gold Header Typography**: High-readability gold headers (`#ffd700`) with drop shadows.
- **Cyan & Amber Accents**: Subtle glows (`#38bdf8` and `#f59e0b`) indicating active hardware and speech states.
- **Retro HP/MP Bar Meters**: Live telemetry gauges styled after retro battle status bars.

---

## 2. Desktop Avatar & Interaction Model

Lucca floats on your Windows desktop as a lightweight, interactive companion widget.

### Mouse Interactions

| Action | Result | Description |
| :--- | :--- | :--- |
| **Single-Click on Lucca** | **Toggle Dialogue & Chat Bar** | Immediately brings up the subtitle dialogue bubble and quick chat input bar with keyboard focus and click-to-talk button (🎙️). |
| **Double-Click on Lucca** | **Toggle Commorose Menu** | Unfolds the battlefield-style concentric radial menu centered around Lucca. Double-clicking her again smoothly closes the menu. |
| **Left-Click & Drag** | **Move Avatar** | Move Lucca anywhere across your screens. Subtitles, chat bars, and menus automatically reposition to stay anchored to her. |
| **Right-Click on Lucca** | **Desktop Context Menu** | Quick access menu: Always on Top toggle, Reset Position, Settings & Diagnostics, and Quit. |

> **Zero Obstruction Guarantee**: The center hole of the Commorose menu has an 88-pixel radius that is 100% transparent and clear of buttons or close icons. You maintain an unobstructed view of Lucca at all times, with zero floor circles or hint text beneath her.

---

## 3. Battlefield-Style Concentric Commorose (Radial Menu)

Double-clicking Lucca deploys an 8-sector concentric radial menu ($R_{in} = 88\text{ px}$, $R_{out} = 175\text{ px}$) with 3° radial slit cuts and hover blooms.

```text
                  [ 📊 TELEMETRY ]
       [ 💻 CODEBASE ]         [ ⚙️ SETTINGS ]
  [ 🛠️ TOOLS ]              ◎              [ 💬 CHAT BAR ]
       [ 🎙️ VOICE ]            (Lucca)     [ 📁 FOLDERS ]
                   [ 🧠 PERSONA ]
```

### Radial Menu Actions

1. **📊 TELEMETRY (Sector 0 · North)**:
   - Toggles the floating Chrono Trigger Hardware Telemetry HUD.
2. **⚙️ SETTINGS (Sector 1 · North-East)**:
   - Opens the 11-tab comprehensive configuration dialog.
3. **💬 CHAT BAR (Sector 2 · East)**:
   - Toggles the quick text input bar and subtitle speech bubble.
4. **📁 FOLDERS (Sector 3 · South-East)**:
   - Launches Windows Explorer to the root workspace at `C:\ProjectLucca\`.
5. **🧠 PERSONA (Sector 4 · South)**:
   - Directly opens the Persona & Archetype Studio (Settings Tab 0).
6. **🎙️ VOICE (Sector 5 · South-West)**:
   - Directly opens the Voice Blender & Tensor Mixer (Settings Tab 1).
7. **🛠️ TOOLS (Sector 6 · West)**:
   - Directly opens the Application Whitelist & Tool Studio (Settings Tab 3).
8. **💻 CODEBASE (Sector 7 · North-West)**:
   - Opens Windows Explorer directly to the source repository at `C:\projects\ProjectLucca\` for safe read-only inspection.

> **Quick Dismiss**: You can close the Commorose by double-clicking Lucca, pressing <kbd>Esc</kbd>, clicking any empty space on the desktop outside the ring, or selecting any action.

---

## 4. Live Hardware Matrix & Telemetry HUD

The Telemetry HUD queries live hardware metrics across all 5 physical and neural computing substrates:

| Substrate | Hardware Detected | Assigned Role in Lucca |
| :--- | :--- | :--- |
| **dGPU** | **NVIDIA GeForce RTX 5080 Laptop GPU (16.0 GB VRAM)** | Powers `llama-server.exe` with Flash-Attention and quantized KV-cache. |
| **NPU** | **Intel AI Boost NPU (OpenVINO)** | Dedicated 15W neural unit executing Whisper STT audio transcription and vector embeddings. |
| **CPU** | **Intel Core Ultra 9 275HX (24 Cores)** | Runs the Supervisor, ZeroMQ IPC message bus, Kokoro-82M TTS synthesis, and tool execution. |
| **RAM** | **16.0 GB Host Physical RAM** | Tracks Lucca's 4-process RSS memory consumption alongside total host system utilization. |
| **iGPU** | **Intel Arc Graphics** | Standby GPU for lightweight OpenVINO fallback operations. |

### Telemetry HUD Features
- **Live Polling (1000ms)**: Real-time queries via `psutil`, `nvidia-smi`, and OpenVINO hardware enumeration.
- **Pin / Unpin Mode**: Click **📌 Pinned** to make the HUD solid (100% opacity) or **Unpinned** (40% translucent overlay that doesn't distract).
- **Session Telemetry Logger**: Writes time-stamped JSONL logs to `C:\ProjectLucca\logs\resource_sessions\` tracking VRAM usage, CPU percentages, and memory footprints over time.

---

## 5. Comprehensive 11-Tab Configuration Suite

The configuration suite provides complete control over every facet of the companion:

### Tab 0: 🧠 Persona Studio
- **Archetype Presets & Custom Archetypes**: Select between hybrid prose built-in archetypes (*Inventor*, *Genki*, *Kuudere*) or author and delete custom archetypes saved directly to `config/persona.toml`.
- **Prose Compilation Invariant**: All personality, behavior, and trait controls strictly compile into natural-language English sentences. No pseudo-code, `trait=value`, numbers, or bracket syntax is ever injected into the prompt.
- **Formality Modes**: Aligned across UI, config, and prompt compilation into `Casual` (approachable, snappy), `Neutral` (balanced, composed), and `Precise` (meticulous technical precision).
- **Behavior & Boundaries Controls**:
  - *Address me by name*: Injects directives to naturally address the user by name when known.
  - *Admit uncertainty aloud*: Instructs Lucca to openly say "I am not sure" rather than hallucinating or guessing.
  - *Never pretend to feel (affect = system state)*: Enforces describing internal emotional state strictly in terms of system affect and operational registers (e.g. "engagement register is high"), never simulating biological feelings.
- **Refuse Topics Editor**: Configurable list of declined topics (e.g. unauthorized execution, financial speculation) rendered as natural prose decline directives.
- **Affect Engine Settings**: Configures affective decay half-life $\tau$ (60–1800s) and maximum TTS pacing modulation speed delta ($\pm 0.00$ to $0.25$), persisted to `[affect]` in `persona.toml`.
- **Granular Trait Modulator Sliders**:
  - *Technical Depth (0–100)*: Controls technical depth from high-level summaries to substrate-level mechanical explanation.
  - *Warmth / Playfulness (0–100)*: Modulates interpersonal warmth from dry, understated wit to infectious camaraderie.
  - *Directness (0–100)*: Controls conversational framing from nuanced context-first to bottom-line upfront conclusions.
  - *Live Prose Compilation Readout*: Real-time display showing the exact natural English sentences compiled from the active trait coordinates. Defaults (50/50/50) produce zero prompt bloat.
- **Truthful Token-Counted System Prompt Preview**: Live display of the full, truthful compiled prompt (combining archetype voice, formality rules, voice constraints, boundaries, traits, architectural self-awareness, and additive custom directives) with approximate token calculation.

---

### Tab 1: 🎙️ Voice Blender & English Anime Voice Pipeline
- **ALL Installed Kokoro Vectors**: Instant access to all 54 installed Kokoro-82M voice style vectors (`af_alloy` through `zm_yunyang`).
- **Synthesis Modes**:
  1. *Single Native Vector*: Standard unblended Kokoro voice profile.
  2. *Pre-Engineered Recipes*: Curated blends including `anime_heroine_expressive`, `genki_heroine`, `energetic_dub`, `soft_kuudere`, and `young_shonen`.
  3. *Dual-Vector Live Blender*: Interpolate two voice tensors $\alpha \cdot \mathbf{v}_A + (1 - \alpha) \cdot \mathbf{v}_B$ with real-time slider control.
- **✨ One-Click English Anime Heroine Preset**:
  - Blends Kokoro's female voice tensors at 70% `af_bella` + 30% `af_sarah` for a bright, high-register anime voice profile.
  - Native pacing automatically set to **1.20x** (optimal 1.15x–1.25x anime dub cadence).
- **Expressive Punctuation Shaping (G2P Pitch Contours)**:
  - Text pre-processing injects commas, ellipses (`...`), hyphens (`-`), and exclamation marks to guide Kokoro's grapheme-to-phoneme engine into producing sudden pitch jumps, breath pauses, and lively anime voice inflection.
- **Live Audition Player**: Stream and preview the blended voice with synchronized audio-paced subtitles.

---

### Tab 2: ⚡ LLM Tuning, Model Registry & VRAM Fit Guard
- **Dynamic Model Registry**:
  - Automatically scans `models/llm/*.gguf` on disk with live detection of model weights and multimodal projectors.
  - Inspects binary GGUF headers to extract architecture, parameter tensor counts, KV metadata, and quantization versions.
- **Binary Audio-Compatibility Badges**:
  - 🎙 **Audio-Native**: Displays when a model has a valid paired `mmproj*.gguf` projector on disk (e.g., Ultravox models). Enables raw `input_audio` mode.
  - 📄 **Text via Whisper**: Standard text LLMs (e.g. Llama 3.1, Qwen 2.5). Operates seamlessly using Whisper STT transcriptions on every turn.
  - ⚠ **mmproj required**: Identifies audio models lacking projector weights, with direct download guidance.
- **Granular Context Length Slider**:
  - Continuous slider from **512** to **32,768** tokens in **256-token steps** with quick-select preset buttons (2K, 4K, 8K, 16K, 32K).
- **KV-Cache Quantization & Memory Footprint**:
  - Real-time VRAM estimator calculating exact memory consumption for `FP16`, `Q8_0`, and `Q4_0` cache types.
- **15GB VRAM Fit Guard (RTX 5080 16GB Protection)**:
  - Dynamically calculates total VRAM requirement: $\text{Model Weights} + \text{KV-Cache Footprint} + 1.0\text{ GB System Overhead}$.
  - If total memory exceeds the **15.0 GB** threshold, an amber/red warning is displayed and the "Apply & Restart" button is safely locked to prevent Out-Of-Memory (OOM) GPU crashes.
- **Honest llama-server Control**:
  - Dedicated background worker (`server_ctl.py`) executes genuine process termination, subprocess launch of `llama-server.exe`, and HTTP `/health` polling.
  - Real-time status reporting: "Stopping active server..." $\rightarrow$ "Launching llama-server.exe..." $\rightarrow$ "Waiting for /health (HTTP 200)..." $\rightarrow$ "✓ Healthy (port 8080, X.Xs)".
- **Curated Model Catalog & Secure Downloader**:
  - Download table with verified HTTPS endpoints for Ultravox Llama-3.1-8B Q6_K, paired multimodal projectors, and Qwen2.5-Instruct models.
  - Raw URL downloader validates the binary `GGUF` magic header upon download completion, preventing corrupt or incompatible files from entering the registry.

---

### Tab 3: 🛠️ Tool Whitelist Studio
- **Application Authorization**: Whitelist executable applications that Lucca is permitted to launch or inspect.
- **Security Guardrails**: Toggle confirmation prompts for sensitive operations.
- **Codebase Access**: Safe read-only inspection permission for `C:\projects\ProjectLucca`.

### Tab 4: λ MicroScheme LISP Domain Reasoning Studio
- **Domain Reasoning Pathways**: Categorized rules (*Hardware & Safety*, *Cognitive & Temporal*, *Tools & Execution*, *Persona & Inflection*, *Memory & Recall*).
- **Rule Inspector**: View plain-English purpose, gas limit (1000), execution priority (0–100), and lifecycle state.
- **In-Place S-Expression Code Editor**: Syntax validation against AST rules using `parse_rule`.
- **Test Evaluation Engine**: Dry-run rule execution conditions with gas metering.

### Tab 5: ⌨️ Hotkeys & Rebinding
- **Arbitrary Push-To-Talk (PTT)**: Interactive key listener allows rebinding PTT to any keyboard key (default: Right Ctrl / F24).
- **Hands-Free Wake Word**: Toggle local wake word detector listening for "Lucca".

---

### Tab 6: 🎛️ Granular DSP Audio Chain & English Anime Voice Processing
- **✨ One-Click English Anime Voice DSP Preset**:
  - **Formant-Preserved Pitch Shift**: Shifting +2.5 to +3.0 semitones brings Kokoro's output up into a youthful, bright anime heroine register.
  - **120 Hz High-Pass Filter**: Cuts heavy chest resonance and room rumble below 120 Hz, thinning the voice for an authentic animated voiceover tone.
  - **Vocal Presence Boost (+3.0 dB @ 4.0 kHz)**: Sharpens consonant articulation and forward vocal projection.
  - **Air Boost High-Shelf (+2.5 dB @ 10.0 kHz)**: Introduces breathy, energetic top-end shimmer.
  - **Fast Dynamic Compressor**: Rapid 10ms attack and 50ms release with a 3.5:1 ratio and -18 dB threshold to level vocal dynamics and keep speech right against the listener's ear.
  - **Harmonic Exciter / Saturation (Drive 0.20)**: Subtle soft-knee saturation generating upper-harmonic sheen reminiscent of studio condenser microphones.
  - **Master Gain & Soft Limiter**: Level matching with a 0.98 ceiling to prevent digital clipping.
- **Live DSP Audition**: Real-time interactive playback testing directly renders the complete DSP filter chain.
- **Optional RVC (Retrieval-based Voice Conversion) Intermediate Pipeline**:
  - For projects desiring hyper-specific character timbre (e.g. an exact English anime VA voice model), Project Lucca supports an optional local RVC v2 inference stage.
  - *Pipeline Flow*: `Kokoro TTS (with expressive punctuation)` $\rightarrow$ `RVC v2 Inference Server (local dGPU, pitch guidance enabled)` $\rightarrow$ `Anime DSP Post-Processing Chain` $\rightarrow$ `Sounddevice Output`.
  - Kokoro provides natural conversational pacing, expressive phoneme timing, and breath marks, while RVC converts the spectral timbre to the target character index, and the DSP chain adds presence and dynamic polish.

### Tab 7: 💾 Episodic & Semantic Memory System
- **Database Statistics**: Live counts of active records, forgotten memories, 384-D vector index status, and disk size of `C:\ProjectLucca\data\memory.sqlite`.
- **Search & Filtering**: Search by keyword and filter by kind (`All Kinds`, `episodic`, `fact`, `preference`).
- **Interactive Memory Table**: Inspect ID, Kind, Content, Importance Weight, and Timestamp.
- **In-Place Memory Editor**: Edit content, adjust importance weight slider (0.00 to 1.00), and apply updates.
- **Database Actions**:
  - *💾 Save Changes*: Writes modifications to SQLite-vec database.
  - *🗑️ Prune / Forget*: Soft-deletes memories (`status = forgotten`).
  - *➕ Teach New Fact*: Manually insert and vector-embed custom instructions.
  - *🧹 Vacuum Database*: Reclaims disk space and optimizes SQLite-vec indices.

### Tab 8: 📊 Telemetry & Embedded Log Inspector
- **Session Log Selector**: Browse and select rolling `*.jsonl` log files from `C:\ProjectLucca\logs\resource_sessions\`.
- **Parsed Telemetry Table**: Real-time tabular display of Timestamp, Host RAM %, Lucca 4-process RSS MB, dGPU RTX 5080 VRAM, CPU % Total / Lucca, and NPU Status.
- **Raw JSONL Inspector**: View raw JSONL records with color-coded syntax.
- **Live Tail Mode (1s)**: Automatically scroll and refresh new incoming hardware metrics.

### Tab 9: 📖 Interactive User Manual
- **Split-Pane Architecture**: Left Table of Contents linking to 10 comprehensive chapters with a right scrollable documentation pane.
- **Covered Topics**: Getting Started, Radial Commorose, Voice Blender, Granular DSP, LLM Tuning, MicroScheme LISP, SQLite-vec Memory, Hardware Telemetry, Codebase Inspection, and Troubleshooting.

### Tab 10: ℹ️ Dedicated About Lucca Section
- **Character Lore & Origin**: Lucca Ashtear from the Kingdom of Guardia (1000 AD) in Squaresoft's *Chrono Trigger*.
- **4-Process Decoupled Architecture**: Detailed breakdown of `lucca-supervisor`, `lucca-audio`, `lucca-npu`, and `lucca-ui`.
- **Physical Hardware Topology Detected**: Summary of RTX 5080 Laptop GPU, Core Ultra 9 275HX, 16 GB RAM, and AI Boost NPU.
- **Technology Stack**: Python 3.12, PyQt6, PyZMQ, Kokoro-ONNX, Faster-Whisper, SQLite-vec, and MicroScheme.
- **Licensing & Credits**: MIT License and DeepMind Advanced Agentic Coding credits.

---

## 6. Audio-Paced Speech Streaming & Subtitles

Lucca's speech bubble operates in lockstep with the Kokoro-82M text-to-speech audio stream:
- **Natural Cadence**: Text streams phrase-by-phrase at ~18 characters per second, perfectly matching human speech tempo.
- **Punctuation Pauses**: Natural micro-pauses at commas (180ms) and sentence boundaries (350ms).
- **No Skipping**: Click-to-skip fast forwarding is disabled to guarantee audio and subtitle synchronization.
- **Turn Latency & Clock**: Displays a live 12-hour local clock and the exact round-trip turn latency in milliseconds.
- **Confirmation Prompts**: Sensitive actions display interactive **[Confirm]** / **[Cancel]** buttons.

---

*Project Lucca — Engineered for performance, transparency, and retro delight.*
