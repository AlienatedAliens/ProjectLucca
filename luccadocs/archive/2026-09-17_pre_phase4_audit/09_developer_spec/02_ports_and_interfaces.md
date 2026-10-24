# Spec 02 — Ports (hexagonal boundaries) and Adapter Contracts

Every external capability is reached only through a `typing.Protocol` in `lucca/core/ports.py`. Adapters live in the owning package. `lucca.core` and `lucca.brain` import **ports only**, never adapters. Enforced by `import-linter` (contracts in spec 11 §Static gates).

Rules for all ports: `async` where I/O; zero `Any` (use `JsonValue` for genuinely dynamic tool args); every method documents its timeout and its typed exceptions (`lucca.core.exceptions`); every adapter ships a **Fake** in `tests/fakes/` that is deterministic and scriptable.

## Common types (`lucca/core/schemas.py`)

```python
class AudioRef(BaseModel):  # never carries PCM over IPC
    ring: Literal["cap"]
    seq_start: int
    seq_end: int
    rate: Literal[16000]


class Transcript(BaseModel):
    text: str
    segments: list[Segment]
    avg_logprob: float
    model: str
    audio_sha256: str
    elapsed_ms: float


class ToolCall(BaseModel):
    tool: str
    args: dict[str, JsonValue]
    call_id: str


class ToolResult(BaseModel):
    call_id: str
    ok: bool
    exit_code: int | None
    structured: dict[str, JsonValue] | None  # TOOL_VERIFIED facts
    content: str | None  # TOOL_CONTENT_UNTRUSTED body (capped)
    content_truncated: bool
    elapsed_ms: float
    stderr: str
```

## Ports

### `SpeechLLMPort` (adapter: `brain/llm_client.py` → llama-server)
```python
async def stream(self, req: LLMRequest) -> AsyncIterator[LLMEvent]
    # LLMRequest: system: str, memory_block: str, history: list[Msg], user_audio: AudioRef | None,
    #             user_text: str | None, tools: list[ToolSchema], grammar: str | None, max_tokens: int
    # LLMEvent = TokenDelta(text) | ToolCallStart | ToolCallDelta(json_fragment) | ToolCallEnd(ToolCall) | Done(usage)
    # Timeout: 10 s to first event, 60 s total. Raises LLMUnavailable, LLMTimeout, LLMProtocolError.
async def abort(self, trace_id: str) -> None      # ≤ 50 ms; idempotent
async def health(self) -> LLMHealth               # {ok, model, mode: "audio"|"transcript", slots_idle}
```
Contract: exactly one of `user_audio`/`user_text` per request in `audio` mode (audio); `transcript` mode uses `user_text` only. Adapter must place `system + memory_block` **before** history and audio for prefix-cache reuse.

### `STTPort` (adapter: `senses/asr.py` in `lucca-npu`, called via IPC proxy `senses/asr_proxy.py`)
```python
async def transcribe(self, audio: AudioRef, *, trace_id: str) -> Transcript   # timeout 3 s
def device(self) -> Literal["NPU","GPU","CPU"]
```

### `TTSPort` (adapter: `senses/tts.py` in `lucca-npu`)
```python
async def synthesize(self, chunk: TTSChunk) -> TTSChunkDone   # TTSChunk{trace_id, chunk_id, text, voice, is_first}
    # PCM goes to play_ring, not returned. Timeout 2 s per chunk. Raises TTSFailed.
async def abort(self, trace_id: str) -> None
def device(self) -> Literal["NPU","GPU","CPU"]
def rtf_estimate(self) -> float           # last measured real-time factor
```

### `EmbeddingPort` (adapter: `senses/embed.py`)
```python
async def embed(self, texts: Sequence[str]) -> list[list[float]]   # dim 384, L2-normalised; ≤ 128 tokens each (truncate, log)
def dim(self) -> int
```

### `MemoryStorePort` (adapter: `memory/store.py`; sole SQLite writer)
```python
async def commit(self, payload: SignedPayload) -> MemoryId      # atomic; raises ProvenanceRejected, GroundingError
async def search(self, q: RetrievalQuery) -> list[MemoryHit]    # hybrid RRF; ≤ 25 ms p95 at 50 k rows
async def supersede(self, old: MemoryId, new: MemoryId, reason: str) -> None
async def forget(self, ids: list[MemoryId], *, user_confirmed: bool) -> None
async def graph_neighbors(self, entity: str, hops: int = 1) -> list[Edge]
```

### `VectorStorePort` / `TextIndexPort` (internal to memory; adapters `sqlite-vec`, `fts5`; alt adapter `chroma` documented but not shipped)

### `RuleEnginePort` (adapter: `reasoning/rules.py`)
```python
def evaluate(self, state: RuleState, *, mode: Literal["shadow","active"]) -> list[RuleOutcome]
    # RuleOutcome{rule_id, fired: bool, plan: Plan | None, gas_used, elapsed_us, error: str | None}
def register_candidate(self, cand: CandidateRule) -> RuleId
def record_shadow(self, rule_id: RuleId, *, matched: bool, cluster_id: str, indeterminate: bool) -> None
def promote_if_eligible(self, rule_id: RuleId) -> PromotionResult
def verify_regression_suite(self) -> RegressionReport       # never vacuous; report lists cases run
```

### `RouterPort` (adapter: `router/heuristic.py` Phase 4; `router/classifier.py` Phase 6)
```python
def route(self, feats: RouteFeatures) -> RouteDecision   # {action: RULE|LLM|CLARIFY, probs, set_size, calibrated, elapsed_us}
```

### `SandboxPort` (adapters: `sandbox/client.py` for file/web sandboxes; `sandbox/launcher.py` for host launcher)
```python
async def run(self, call: ToolCall, *, trace_id: str) -> ToolResult   # per-tool timeout ≤ 30 s
async def reset_workspace(self) -> None       # wipes C:\ProjectLucca\workspace, recreates container
def tool_schemas(self) -> list[ToolSchema]    # what the LLM is offered
def risk_of(self, tool: str) -> Risk          # READ|WRITE|LAUNCH|NETWORK
```

### `ClockPort`, `RandomPort` — injected for determinism in tests (replay of sessions requires fixed time/nonces).

### `TracePort` (adapter: `core/trace.py`)
```python
def mark(self, trace_id: str, point: TracePoint, t_ns: int | None = None) -> None
def finish(self, trace_id: str) -> TurnTrace     # computed stage durations; persisted to logs\traces.jsonl and SQLite
```

## Adapter acceptance (applies to every adapter)

| Check | Requirement |
|---|---|
| Fake exists | `tests/fakes/fake_<port>.py`, scriptable via a list of scripted responses; used by all Tier-2 tests |
| Contract test | `tests/contract/test_<port>_contract.py` runs the **same** test module against Fake and Real (real marked `@pytest.mark.hw`) |
| Timeout enforced | every awaited call wrapped in `asyncio.timeout`; timeout raises the port's typed exception, never `asyncio.TimeoutError` to callers |
| No `Any` | `mypy --strict` clean on the port and adapter |
| Import boundary | `import-linter` passes |
