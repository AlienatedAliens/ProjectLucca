# Project Lucca — System Architecture Master Specification
**Document ID:** `SPEC-MASTER-005`  
**Revision:** 4.0  
**Classification:** Enterprise System Architecture Standard  

---

## 1. System Overview (For Laymen & Users)

**Project Lucca** is an autonomous, local-first desktop companion. Unlike cloud assistants that send your private data to remote servers or open-ended AI agents that hallucinate wild code loops, Lucca is engineered with strict physical and logical boundaries:
1. **Zero Cloud Requirement:** Every spoken word, thought, and action runs directly on your MSI laptop's silicon (RTX 5080 dGPU, Intel Arrow Lake NPU, and 24-core CPU).
2. **Push-to-Talk Real-Time Voice:** Lucca speaks and listens naturally with sub-400 millisecond response times and an animated 2D companion avatar.
3. **No Hallucinated Memory:** Lucca will never remember something just because it "imagined" or narrated it. Only facts explicitly verified by tool execution or spoken directly by you can enter long-term memory.
4. **Symbolic Learning:** Over time, Lucca compiles repeated reasoning patterns into lightning-fast, inspectable symbolic rules (LISP), making it smarter and faster the more you interact with it.
5. **Secure Sandbox:** Any file operations or web browsing are executed inside a locked-down container that cannot escape to your personal files or access your local home network.

---

## 2. Architectural Blueprint (For Developers & Autonomous Agents)

Lucca is structured as an **Event-Driven, Hardware-Partitioned Hexagonal Architecture**:

```
                               ┌───────────────────────────┐
                               │     PHYSICAL SENSES       │
                               │  - Push-to-Talk (Win32)   │
                               │  - WASAPI Capture (16kHz) │
                               │  - Silero VAD             │
                               └─────────────┬─────────────┘
                                             │ AudioPacket
                                             ▼
                               ┌───────────────────────────┐
                               │     EXECUTIVE ROUTER      │
                               │  - ModernBERT Encoder     │
                               │  - XGBoost Classifier     │
                               │  - Conformal Guard        │
                               └──────┬──────┬──────┬──────┘
                                      │      │      │
            ┌─────────────────────────┘      │      └─────────────────────────┐
            │ DIRECT_TO_LLM                  │ CHECK_LISP_FIRST               │ CALL_TOOL
            ▼                                ▼                                ▼
┌───────────────────────┐        ┌───────────────────────┐        ┌───────────────────────┐
│     NEURAL BRAIN      │        │    SYMBOLIC ENGINE    │        │    DOCKER SANDBOX     │
│  - Ultravox 8B (WSL2) │        │  - Micro-Scheme AST   │        │  - Safe File I/O      │
│  - RTX 5080 (CUDA12.8)│        │  - 5-Strike Gate      │        │  - Headless Browser   │
│  - NVFP8 KV Cache     │        │  - Gas Metered Eval   │        │  - No RFC1918 Egress  │
└───────────┬───────────┘        └───────────┬───────────┘        └───────────┬───────────┘
            │ Token Stream                   │ Action Stream                  │ Tool Result
            └───────────────────────┬────────┴────────────────────────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │    PROVENANCE WRITE GATE  │
                      │  (Rejects LLM Narration)  │
                      └─────────────┬─────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │     VOICE & AVATAR OUT    │
                      │  - Kokoro TTS (Intel NPU) │
                      │  - 2D Sprite Viseme Sync  │
                      │  - WASAPI Playback (24kHz)│
                      └───────────────────────────┘
```

---

## 3. Strongly Typed Contracts & Data Schemas (Pydantic v2)

### 3.1 Audio & Sensing Schemas
```python
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import numpy as np


class AudioPacket(BaseModel):
    sample_rate: int = Field(default=16000, description="Sample rate in Hz")
    channels: int = Field(default=1, description="Mono channel")
    pcm_data: bytes = Field(..., description="Raw 16-bit signed PCM audio bytes")
    duration_ms: float = Field(..., description="Duration of audio packet in milliseconds")
    energy_level: float = Field(..., description="Calculated RMS energy")
    is_speech_final: bool = Field(default=True, description="VAD endpointing flag")


class VisemeFrame(BaseModel):
    timestamp_ms: float
    viseme_id: str  # e.g., 'sil', 'aa', 'ee', 'ih', 'oh', 'ou', 'pp'
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)
```

---

### 3.2 Memory & Provenance Schemas
```python
class MemoryProvenance(str, Enum):
    USER_EXPLICIT = "USER_EXPLICIT"  # Explicitly spoken by user during PTT turn
    TOOL_VERIFIED = "TOOL_VERIFIED"  # JSON payload verified from container tool
    LISP_ASSERTION = "LISP_ASSERTION"  # Deterministic rule derivation
    LLM_NARRATION = "LLM_NARRATION"  # FORBIDDEN for long-term memory write


class MemoryCommitPayload(BaseModel):
    entry_id: str = Field(..., description="Deterministic UUIDv5 of content")
    content: str = Field(..., description="Normalized semantic text fact")
    provenance: MemoryProvenance
    signature_token: str = Field(
        ..., description="HMAC-SHA256 signature generated by sensing or tool module"
    )
    created_at_utc: float
    entities: List[str] = Field(default_factory=list, description="Extracted entity nodes")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class WorkingMemoryState(BaseModel):
    task_id: str
    active_intent: str
    intermediate_tool_outputs: List[Dict[str, Any]] = Field(default_factory=list)
    step_count: int = 0
    max_steps: int = 8
    is_active: bool = True
```

---

### 3.3 Routing & Telemetry Schemas
```python
class RouteAction(str, Enum):
    DIRECT_TO_LLM = "DIRECT_TO_LLM"
    CHECK_LISP_FIRST = "CHECK_LISP_FIRST"
    CALL_COMPILED_TOOL = "CALL_COMPILED_TOOL"
    SAFE_FALLBACK_ESCALATE = "SAFE_FALLBACK_ESCALATE"


class DecisionRecord(BaseModel):
    record_id: str
    timestamp_utc: float
    raw_query: str
    npu_embedding_vector: List[float]
    tabular_features: Dict[str, float]
    heuristic_recommendation: RouteAction
    model_prediction: RouteAction
    calibrated_probabilities: Dict[RouteAction, float]
    conformal_prediction_set: List[RouteAction]
    final_dispatched_action: RouteAction
    execution_duration_ms: float
    user_interrupted: bool = False
    task_success: Optional[bool] = None
```

---

### 3.4 Sandbox Tool Schemas
```python
class ToolExecutionRequest(BaseModel):
    call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    timeout_seconds: float = Field(default=5.0, le=30.0)


class ToolExecutionResponse(BaseModel):
    call_id: str
    tool_name: str
    exit_code: int
    stdout: str
    stderr: str
    structured_data: Optional[Dict[str, Any]] = None
    execution_time_ms: float
    tamper_proof_token: str
```

---

## 4. Micro-Scheme / LISP Engine Specification

### 4.1 S-Expression Grammar (EBNF)
```ebnf
Expression  ::= Atom | List
List        ::= '(' Expression* ')'
Atom        ::= Identifier | Number | String | Boolean
Identifier  ::= [a-zA-Z_+\-*/<>=][a-zA-Z0-9_+\-*/<>=?]*
Number      ::= [0-9]+ ('.' [0-9]+)?
String      ::= '"' [^"]* '"'
Boolean     ::= '#t' | '#f'
```

### 4.2 Standard Primitive Functions (Pure & Gas-Metered)
* **Logic:** `(and expr...)`, `(or expr...)`, `(not expr)`, `(= a b)`, `(< a b)`, `(> a b)`
* **Control Flow:** `(if cond then else)`, `(cond (test expr)...)`, `(seq expr...)`
* **Data Accessors:** `(get dict key)`, `(matches? pattern str)`, `(contains? list item)`
* **Actions:** `(call-tool name arg-dict)`, `(emit-speech text)`, `(log message)`
* **Gas Metering:** Every reduction step decrements `gas_remaining`. Default: $G = 1,000$. If $G \le 0$, execution aborts cleanly with `ExecutionGasExhaustedException`.

---

## 5. Developer Implementation Checklist & Acceptance Rules

To maintain the architectural integrity of Project Lucca across implementations:
1. **Rule of Clean Separation:** No module may import another module's internal classes. Communication must proceed strictly via the typed Pydantic contracts in Section 3.
2. **Rule of Verifiable Provenance:** Every call to `memory_subsystem.commit()` must pass a cryptographically signed `signature_token` matching the internal orchestrator key. The key is never exposed to the LLM prompt.
3. **Rule of Hardware Discipline:** Never allocate memory to the iGPU or dGPU without verifying against the memory budgets in `SPEC-TOPOLOGY-003`.
4. **Rule of Zero Regression:** No new symbolic rule may be added to `active_rules.lisp` unless it passes 100% of historical cases in the regression test suite.
