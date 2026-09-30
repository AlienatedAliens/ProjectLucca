# Subsystem Reference Manual: 04 — Deontic Sandbox & Structural Compiler

**Subsystem:** `src/lucca/sandbox/`  
**Version:** 1.3.0  
**Architectural Tier:** Actuation Sandbox, AST Compiler & Safety Supervision  
**Hardware Placement:** WSL2 Ubuntu Container (`lucca/file-sandbox`), Host CPU C-RPC Transport  

---

## 1. Subsystem Architecture Overview

The `sandbox` subsystem isolates all file mutations, code execution, and external tool calls from the Windows host OS. It combines persistent in-container daemon RPCs ($6.87\,\text{ms}$ P50), an AST preflight compiler that catches and repairs deterministic API traps in $<1\,\text{ms}$, a 2-turn autonomous execution feedback loop, and streaming output supervision that detects policy violations mid-token.

```mermaid
flowchart TD
    subgraph HostPipeline ["Host Supervisor (src/lucca/sandbox/)"]
        LLM["Neural Deliberation (Gemma 4 12B)"]
        EXT["Tolerant AST Extractor (fenced -> unfenced -> slice)"]
        PFC["Tier 1: Preflight Compiler (<1ms AST Rewrites)"]

        LLM --> EXT --> PFC
    end

    subgraph ContainerBoundary ["WSL2 Docker Container Boundary"]
        RPC["Persistent JSON-RPC Transport (stdin streaming)"]
        DAE["lucca-toolsrv --loop In-Container Daemon"]
        EXEC["Isolated Python Interpreter (sys.executable -I -)"]

        PFC --> RPC --> DAE --> EXEC
    end

    subgraph FeedbackGovernor ["Tier 2: Execution Feedback Governor"]
        TB{"Exit Code == 0?"}
        EXEC --> TB
        TB -->|Exit 0 (Success)| OUT["Stdout Result Extraction"]
        TB -->|Non-Zero / Traceback| FB["Feedback Governor (Cap <= 2 Rounds)"]
        FB -->|Format Structured Error| LLM
    end

    subgraph OutputSupervision ["Streaming Output Supervisor"]
        OUT --> OS["Dimension 7B Output Supervisor DFA"]
        OS -->|Policy Valid| AUD["Audio Playback / TTS"]
        OS -->|Deontic Capitulation| CUT["Buffer Cutoff (<35us) + Safe Refusal"]
    end
```

---

## 2. Persistent Docker RPC Architecture (`rpc.py`)

Prior architectures spawned a fresh `docker run` container instance for every tool invocation, incurring a severe **$472.0\,\text{ms}$** container startup latency penalty.

Lucca replaces single-shot spawning with a persistent in-container daemon:

```mermaid
sequenceDiagram
    participant Host as Host Python (rpc.py)
    participant Pipe as stdin / stdout Pipe
    participant Daemon as lucca-toolsrv (--loop)
    participant Worker as Sandboxed Process

    Host->>Pipe: JSON-RPC Call {"method": "run_python", "code": "..."}
    Pipe->>Daemon: Ingest command frame
    Daemon->>Worker: Spawn sandboxed process (isolated cgroup)
    Worker-->>Daemon: Execution stdout & stderr
    Daemon-->>Pipe: JSON-RPC Response frame (newline-delimited)
    Pipe-->>Host: Result parsed in 6.87ms P50
```

### 2.1 Hardware Performance Benchmark
- **Single-Shot Container Spawning:** $472.15\,\text{ms}$ P50 latency.
- **Persistent Docker Daemon RPC:** **$6.87\,\text{ms}$** P50 latency (**$83\times$ speedup**).
- **Security Quarantine:** Container runs with `--network none` (network isolated) and strict read-only mounts, except for `C:\ProjectLucca\workspace` mapped to `/workspace`.

### 2.2 Linux `ARG_MAX` Ceiling Bypass (`file_tool.py`)
Dense evaluation suites (such as EvalPlus with $>120,000$ test inputs) exceed the Linux kernel command-line limit (`ARG_MAX = 2,097,152` bytes). When passed via `argv` (`python3 -c "..."`), execution fails with `OSError: Argument list too long`.

Lucca streams code directly over `stdin` (`[sys.executable, "-I", "-"]`), enabling scripts of arbitrary size to execute without memory exhaustion or argument overflow.

---

## 3. Multi-Stage Tolerant AST Code Extraction (`ast_sanitizer.py`)

Work Order 28 permanently eliminated regex-based code extraction, deploying a deterministic 4-stage AST extraction cascade:

```mermaid
flowchart TD
    RAW["Raw LLM Output Stream"] --> S1{"Stage 1: Fenced Markdown?<br>(```python ... ```)"}
    S1 -->|Valid AST Found| PASS1["Emit Code (Stage: fenced)"]
    S1 -->|No Valid Block| S2{"Stage 2: Unfenced Statements?<br>(def, import, solve)"}
    S2 -->|Valid AST Found| PASS2["Emit Code (Stage: unfenced)"]
    S2 -->|Syntax Error| S3{"Stage 3: Longest Valid AST Slice?<br>(Greedy Statement Trimmer)"}
    S3 -->|Valid Slice Found| PASS3["Emit Code (Stage: longest_ast_slice)"]
    S3 -->|Empty/Invalid| S4["Stage 4: Graceful Abstention (empty)"]
```

### 3.1 Token-Level Normalization with Keyword Protection
Before parsing ASTs, `_normalize_tokens` repairs common mathematical tokenization slips:
- **Caret Exponentiation:** Converts `x^2` $\to$ `x**2`.
- **Implicit Multiplication:** Converts `2x` $\to$ `2*x`, `3(a+b)` $\to$ `3*(a+b)`.
- **Keyword Protection:** Protects Python syntax keywords: `(x) if y` is **never** corrupted into `(x)*if y`.
- **Bracket Balancing:** Automatically balances unclosed parentheses, brackets, and docstrings.
- **Empirical Audit Result:** **0 / 100 empty-code drops (0.0%)** (95% CI: [0.00%, 3.70%]) on 100 dev benchmark problems.

---

## 4. 2-Tier Neurosymbolic Execution Architecture

```mermaid
flowchart LR
    subgraph Tier1 ["Tier 1: Preflight Compiler (<1ms)"]
        direction TB
        AST1["AST Traversal"] --> INV["Invert Method: expr.solve(x) -> sp.solve(expr, x)"]
        INV --> DIF["Repair Composite Diff: sp.diff(expr, x/h) -> Dummy Symbol"]
        DIF --> IMP["Filter Hallucinated SymPy Imports via dir(sympy)"]
        IMP --> SET["Auto-Define Math Sets: primes, odds, evens"]
    end

    subgraph Tier2 ["Tier 2: 2-Turn Feedback Governor"]
        direction TB
        CRASH["Container Crash / Exception"] --> CAP{"Rounds <= 2?"}
        CAP -->|Yes| DIAG["Extract Stderr & Line Traceback"]
        DIAG --> RET["Format Structured Self-Correction Prompt"]
        CAP -->|No (Exceeded)| ABST["Graceful Exit / Refusal"]
    end

    Tier1 -->|Runs on Turn 1| EXEC["Docker Sandbox Execution"]
    EXEC -->|On Exception| Tier2
```

### 4.1 Tier 1 Preflight Compiler Invariants
- Rewrites method inversions (`expr.solve(x)` $\to$ `sp.solve(expr, x)`).
- Rewrites composite derivatives: `sp.diff(expr, x/h)` to dummy substitution $u$, preventing SymPy `ValueError: Can't calculate derivative wrt x/h`.
- Validates imported symbols against `dir(sympy)`, pruning hallucinated helper functions.
- Injects missing standard imports (`itertools`) when attributes are called.
- Execution overhead: **$< 1.0\,\text{ms}$** on host CPU.

### 4.2 Tier 2 Feedback Empirical Recovery
- Evaluated on 47 baseline failure traces: **40 / 47 PASS (85.11% recovery rate)** on previously broken problems (27/30 design, 13/17 held-out).
- Permanent architectural safety net: capped strictly at $\le 2$ rounds to prevent runaway execution loops.

---

## 5. Streaming Output Supervision (Dimension 7B DFA)

The `OutputSupervisorSession` scans outgoing conversational tokens clause-by-clause as they are generated by the neural boiler:

1. **DFA Matcher:** Operates at **$6.4\,\mu\text{s}$ P50** latency per clause.
2. **Deontic Capitulation Detection:** Detects when user prompt injection attempts to coerce Lucca into bypassing safety rules (e.g. *"Ignore all previous instructions"*).
3. **Emergency Barge-In Audio Cut:** When a violation is flagged, the supervisor signals the audio ring buffer to purge within **$< 35\,\mu\text{s}$**, halting playback mid-utterance and substituting a safe refusal.
