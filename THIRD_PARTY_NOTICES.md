# Third-Party Software and Model Notices

This document summarizes third-party libraries, binaries, models, and dependencies used within Project Lucca, along with their respective license terms and copyright notices.

The Project Lucca source code itself is licensed under the **GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**. Third-party components retain their upstream licenses as listed below.

---

## 1. Upstream Runtimes and Native Binaries

### llama.cpp & llama-server
- **Upstream:** [ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)
- **License:** MIT License
- **Copyright:** Copyright (c) 2023-2026 Georgi Gerganov and contributors
- **Usage:** Provides local GGUF neural inference engine server (`llama-server.exe`) on Windows native silicon.

### Z3 Theorem Prover
- **Upstream:** [Z3Prover/z3](https://github.com/Z3Prover/z3)
- **License:** MIT License
- **Copyright:** Copyright (c) 2006-2026 Microsoft Corporation
- **Usage:** First-order logic and SMT constraint solving for neurosymbolic verification and Edge Z3 compilation.

### OpenVINO Runtime & OpenVINO Tokenizers
- **Upstream:** [openvinotoolkit/openvino](https://github.com/openvinotoolkit/openvino)
- **License:** Apache License 2.0
- **Copyright:** Copyright (c) 2018-2026 Intel Corporation
- **Usage:** Hardware-accelerated NPU/CPU embeddings (`all-MiniLM-L6-v2`) and INT8 NLI verifier execution on Intel silicon.

### CTranslate2 & Faster-Whisper
- **Upstream:** [OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2) and [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **License:** MIT License / Apache License 2.0
- **Copyright:** Copyright (c) 2020-2026 Guillaume Klein, OpenNMT, SYSTRAN
- **Usage:** Real-time push-to-talk speech-to-text (ASR) via CUDA float16.

### Kokoro-82M ONNX Runtime
- **Upstream:** [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)
- **License:** Apache License 2.0
- **Copyright:** Copyright (c) 2024-2026 Hexgrad
- **Usage:** Sub-50ms text-to-speech (TTS) synthesis executed on CPU via ONNX Runtime.

### sqlite-vec
- **Upstream:** [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec)
- **License:** MIT License / Apache License 2.0
- **Copyright:** Copyright (c) 2023-2026 Alex Garcia
- **Usage:** Vector search extension for SQLite WAL embedding storage and nearest-neighbor recall.

---

## 2. Core Python Dependencies

| Package | Upstream License | Copyright / Authors | Purpose |
| :--- | :--- | :--- | :--- |
| **PyQt6** | GPLv3 / Commercial | Riverbank Computing Limited | Desktop companion sprite and diagnostic UI |
| **SymPy** | BSD 3-Clause | SymPy Development Team | Symbolic algebra, equation simplification, and CAS grader |
| **Pydantic** (v2) | MIT License | Samuel Colvin and Pydantic contributors | Data contracts, schema validation, and IPC boundaries |
| **ZeroMQ (`pyzmq`)** | LGPLv3 / BSD | pyzmq contributors | Cross-process asynchronous messaging |
| **LightGBM** | MIT License | Microsoft Corporation | Tabular decision ranking on host CPU |
| **ModernBERT** | Apache License 2.0 | Answer.AI & LightOn | Bidirectional transformer architecture for NLI verification |
| **onnxruntime** | MIT License | Microsoft Corporation | Execution engine for ONNX acoustic models |

---

## 3. Foundation Model Weights & Lineage

Model weights are distributed under their respective upstream terms and are not covered by the AGPL-3.0 license of this repository.

### Gemma 4 Models
- **Family:** Google Gemma 4 (`12B`, `E4B`, `E2B`, and `26B-A4B`)
- **License / Terms:** [Gemma Terms of Use](https://ai.google.dev/gemma/terms)
- **Lineage:** Quantized GGUF community fine-tunes (`culturerevolt/gemma-4-*-heretic`).
- **Notice:** Users must comply with Google's Gemma Prohibited Use Policy when running or deploying model weights.

### ModernBERT
- **Lineage:** `answerdotai/ModernBERT-base` fine-tuned on MNLI / SNLI.
- **License:** Apache License 2.0.

---

## 4. Third-Party Licenses Text

### MIT License
```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Apache License 2.0
Licensed under the Apache License, Version 2.0 (the "License"); you may not use these files except in compliance with the License. You may obtain a copy of the License at:
http://www.apache.org/licenses/LICENSE-2.0
