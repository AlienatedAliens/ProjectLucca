# Spec 08 — Streaming Text Chunker and Tool-Call Demultiplexer

Replaces `src/lucca/voice/streaming_chunker.py`. Lives in `lucca.brain.chunker` and `lucca.brain.toolcall_demux`, runs in `lucca-core` between `SpeechLLMPort.stream()` and `TTSPort.synthesize()`.

## 1. Pipeline

```
LLMEvent stream ─► ToolCallDemux ─► text deltas only ─► Normaliser ─► Chunker ─► TTSChunk(s)
                        └─► ToolCallEnd(ToolCall) ─► orchestrator (risk policy / execute)
```

## 2. Tool-call demultiplexer

`llama-server` with `--jinja` returns tool calls as structured `tool_calls` deltas for Llama-3.1 templates; **but** the model may also emit raw `<|python_tag|>{"name":…}` or a bare JSON object in `content` when it disobeys the template. The demux therefore:

1. Passes structured `ToolCallStart/Delta/End` events straight through (never to TTS).
2. Watches `content` deltas for a **suspected inline tool call**: buffer starts with optional whitespace then `{` or `<|python_tag|>` within the first 12 chars of the reply. Hold up to 400 chars or until the JSON closes; if it parses as `{"name": str, "parameters"|"arguments": object}` → synthesise `ToolCallEnd`; else release the buffer to TTS as text (it was a genuine "{" — rare).
3. Anything inside ``` fences is treated as code: not spoken; replaced by the phrase "code block omitted" once per block (config `tts.speak_code=false`).

Gate T-CHK-10: 30 fixture streams (10 structured tool calls, 10 inline JSON tool calls, 10 plain text starting with brace-like characters) → 0 tool-call JSON reaches TTS; 10/10 plain texts spoken intact.

## 3. Normaliser (applied to text before chunk boundary detection)

| Rule | Example → spoken |
|---|---|
| Strip markdown emphasis `**x**`, `*x*`, `_x_`, `` `x` `` → x | `**Done**` → `Done` |
| Headings `#`, list bullets `- ` / `* ` / `1. ` at line start → remove marker; treat line end as boundary | |
| Links `[text](url)` → `text` | |
| Bare URLs → "a link" (config `tts.speak_urls`) | |
| Emoji / pictographs (Unicode categories So, Sk beyond ASCII) → removed | |
| Smart quotes → ASCII quotes; `…` → `...`; `—`/`–` → `, ` | |
| Multiple spaces/newlines → single space; `\n\n` → boundary | |
| Filenames keep their dots (`config.yaml`) — protected by the boundary rules below, not rewritten | |
| Numbers are **not** rewritten (misaki handles `3.14`, `1,000`, `$5`) | |

## 4. Boundary detection (streaming, one-token lookahead)

A candidate boundary is a position after `.`, `!`, `?`, `;`, `:` or `\n`. It is **confirmed** only when the *next* delta has arrived (or stream ended) and all hold:

1. Next char is whitespace or end-of-stream (so `3.14`, `v2.0`, `config.yaml`, `C:\a.b\c` never split — the char after the dot is not whitespace).
2. The token before the punctuation is not in `ABBREVIATIONS` (`mr, mrs, ms, dr, prof, sr, jr, st, vs, etc, e.g, i.e, no, approx, dept, est, fig, inc, ltd, co, corp, u.s, u.k, a.m, p.m` + single capital letters like `J.`).
3. Not inside an open quote/paren pair (track `"“(` depth; reset if depth > 3 — malformed).
4. Not an ellipsis (`...` counts as one boundary only if followed by whitespace + uppercase).
5. Not a numbered-list marker (`^\d+\.$` as the whole segment so far).

Measurement of segment size is in **characters and words**, never tokens:

| Parameter | Value | Reason |
|---|---|---|
| `first_chunk_min_chars` | 24 | enough for natural prosody |
| `first_chunk_max_chars` | 90 | bounds first-audio latency |
| `min_chars` (later chunks) | 40 | avoids choppy 1-word chunks |
| `max_chars` | 220 | bounds TTS synth time (~1.5 s speech ≤ 180 ms) |
| `soft_boundary` | `,` allowed as boundary only when segment ≥ `min_chars` | |
| `force_split_at` | 260 chars: split at last whitespace even without punctuation | run-on protection |
| `idle_flush_ms` | 350 | if no delta for 350 ms and buffer ≥ 12 chars, flush (LLM stalled) |

Emission: `TTSChunk{trace_id, chunk_id (0-based), text, is_first}`. Empty/whitespace-only chunks are never emitted.

## 5. Lifecycle & thread-safety

```python
class Chunker:
    def feed(self, delta: str) -> list[TTSChunk]     # may return 0..n chunks
    def flush(self) -> list[TTSChunk]                # end-of-stream; emits remainder, resets
    def reset(self) -> None                          # barge-in; drops buffer, resets is_first, depth, abbreviations state
    @property
    def spoken_prefix(self) -> str                   # text of chunks emitted so far (for history on interrupt)
```
Single-owner object per turn; created in DISPATCH, discarded in POSTTURN. Not shared across tasks. `reset()` must be callable at any time without raising.

## 6. Tests (frozen fixtures `tests/fixtures/chunker/*.jsonl`: `{"deltas":[...], "expected_chunks":[...]}`)

| ID | Case | Pass |
|---|---|---|
| T-CHK-01 | `"Pi is 3.14. Next."` streamed char-by-char | chunks `["Pi is 3.14.", "Next."]` — never `"Pi is 3."` |
| T-CHK-02 | `"Open config.yaml and README.md now."` | one chunk; dots preserved |
| T-CHK-03 | `"Dr. Smith arrived. He left."` | `["Dr. Smith arrived.", "He left."]` |
| T-CHK-04 | `"e.g. apples, i.e. fruit. Done."` | no split after `e.g.`/`i.e.` |
| T-CHK-05 | 400-char text with no punctuation | force-split at whitespace ≤ 260; no chunk > 260 |
| T-CHK-06 | `"Wait... really? Yes!"` | `["Wait... really?", "Yes!"]` |
| T-CHK-07 | Markdown: `"**Bold** and `code` and [link](http://x). Next."` | spoken text has no `*`, backticks, URL |
| T-CHK-08 | Emoji + smart quotes | removed/normalised |
| T-CHK-09 | Delivery order + `is_first` only on chunk 0; after `reset()` next chunk has `is_first=True` | — |
| T-CHK-10 | Tool-call demux fixtures (see §2) | 0 leaks |
| T-CHK-11 | Idle flush: deltas stop for 400 ms with 30 chars buffered → chunk emitted | — |
| T-CHK-12 | Hypothesis: random Unicode deltas → never raises; `"".join(chunks) == normalise(text)` up to whitespace | 2 000 cases |
| T-CHK-13 | Latency: for 50 fixture replies, first chunk emitted ≤ 90 chars and within 8 deltas of stream start | — |
| T-CHK-14 | `"1. First item\n2. Second item"` | numbered markers not treated as sentence ends; items become 2 chunks |
