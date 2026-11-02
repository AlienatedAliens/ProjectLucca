# Work Order 37: Visual Session Memory, NLI Model Swap, Belief Topic Fix & Repository Truthfulness

```yaml
doc_status: canonical
as_of: 2026-10-25
target_release: v1.47.0 / WO-37
supersedes: []
superseded_by: []
verification: code-cited
```

**Target Release:** Project Lucca `v1.47.0`
**Audience:** An implementing agent with no prior context. Every phase lists exact files, exact actions, functional acceptance criteria, traps, and STOP gates. **STOP** means halt and report — do not improvise.
**Golden rules:** One phase = one commit. Run `uv run pytest -q -m "not tier2 and not hw and not soak"` after every step (baseline: record the actual count you see before your first commit). Never edit `luccadocs/archive/`. Never edit an existing migration file. Never "fix forward" from a red suite — revert and re-read.
**Provenance:** WO-36 PASS (v1.46.5). Session arose from live hallucination observed on vision follow-up turns: after `ui.attach_image` on Turn 1, Turn 2 text queries caused confabulation because `_pending_image_b64` was cleared and no persistent image reference existed. External peer review also identified an 81% NLI verification timeout rate, a stance-topic extraction regression (`topic='about it'`), and documentation truthfulness gaps.

---

## Current State

1. **Vision (ephemeral, broken for follow-ups):** `_pending_image_b64` is set by `ui.attach_image` ([`orchestrator.py:1091`](../src/lucca/core/orchestrator.py#L1091)) and consumed-and-cleared by `turn_pipeline.py` on Turn 1 ([`turn_pipeline.py:893-896`](../src/lucca/core/turn_pipeline.py#L893)). On Turn 2, no image is injected. The model confabulates.
2. **No local image cache:** Attached images live only in memory as `_pending_image_b64`. There is no `data/sessions/images/` directory, no image index, no on-demand reload path.
3. **NLI timeout rate:** `VerifierWorker` ([`src/lucca/senses/verifier.py:60`](../src/lucca/senses/verifier.py#L60)) runs ModernBERT-base (149M params) via OpenVINO at ~60-80ms/pair against a 50ms hard ceiling. Measured timeout rate: **81% of verification pairs** classified as `degraded`. Batches of 3-5 pairs during LLM+TTS saturation exceed 200ms.
4. **Belief topic regression:** `_extract_stance_topic()` ([`src/lucca/core/memory_commit_service.py:39`](../src/lucca/core/memory_commit_service.py#L39)) grabs text after a stance marker without a stopword filter. "My engagement register is quite high when I think about it" produces `topic='about it'`.
5. **Documentation:** README mixes marketing, changelog, and architecture spec. Self-run benchmarks labelled "Verified". `25.9 MB Lucca.exe` description misleading (models are multi-GB). External cleanup audit (2026-10-25) lists 8 priorities with 70+ items.

---

## Phase 0 - Local Session Image Cache (VisualSessionStore)

**Goal:** Persist every attached or captured image to `LUCCA_HOME/data/sessions/images/` and maintain a lightweight in-memory index. Foundation for on-demand reload in Phase 1.

**Rationale:** Storing locally decouples "image available" from "currently in prompt context". Follow-up questions cost a single `Path.read_bytes()` + base64 encode (~1ms). Multiple images across a session can be indexed and selectively reloaded.

**Manifest:**

| File | Action |
|---|---|
| `src/lucca/core/visual_session.py` (new) | Create `VisualSessionStore` and `VisualArtifact` dataclass. |
| `src/lucca/core/orchestrator.py` | Import and instantiate `VisualSessionStore` in `__init__`. Wire `store_image()` at every `_pending_image_b64` write point (lines ~867, ~1091, ~3652). |
| `src/lucca/core/config.py` | Add `sessions_images: str = "data/sessions/images"` field to `PathsSettings`. |
| `tests/test_visual_session.py` (new) | Unit tests per acceptance criteria. |

**`VisualSessionStore` public interface:**

```python
@dataclass
class VisualArtifact:
    image_id: str       # "img_01", "img_02", ...
    sha256: str         # hex digest of raw JPEG bytes
    path: Path          # absolute path on disk
    captured_at: float  # time.time()
    description: str = ""

class VisualSessionStore:
    MAX_IMAGES: int = 8

    def __init__(self, store_dir: Path) -> None: ...
    def store_image(self, b64_jpeg: str, description: str = "screenshot") -> VisualArtifact: ...
    def get_active(self) -> VisualArtifact | None: ...
    def get_by_id(self, image_id: str) -> VisualArtifact | None: ...
    def load_b64(self, artifact: VisualArtifact) -> str | None: ...
    def clear(self) -> None: ...
    @property
    def count(self) -> int: ...
```

Behaviour:
- `store_image()`: decode b64, compute SHA-256, dedup if already stored, write `{sha256[:16]}.jpg` to `store_dir`, append to index, evict oldest if `len > MAX_IMAGES`.
- `load_b64()`: `Path.read_bytes()` + base64 encode. Returns `None` on `OSError`.
- All methods thread-safe via a single `threading.RLock`.
- Zero `Any` invariant enforced throughout.

**Orchestrator wiring (in `Orchestrator.__init__()`, after `self._pending_image_b64: str | None = None`):**

```python
from lucca.core.visual_session import VisualSessionStore
_img_store_dir = self.config.home_dir / self.config.paths.data / "sessions" / "images"
self.visual_session: VisualSessionStore = VisualSessionStore(_img_store_dir)
```

At every `self._pending_image_b64 = <value>` write, also call `self.visual_session.store_image(b64_jpeg=<value>, description="screenshot"|"user_upload")`. Do NOT remove the `_pending_image_b64` assignment.

**Functional acceptance:**
- `store_image(b64_jpeg)` writes a `.jpg` to disk and returns a `VisualArtifact`.
- Storing the same image twice returns the same artifact (dedup by SHA-256).
- `get_active()` returns `None` on empty store, last artifact after one store.
- `load_b64(artifact)` round-trips to the original `b64_jpeg`.
- Storing 9 images evicts oldest, leaving `count == 8`.
- `Orchestrator` instantiates `self.visual_session` without error.
- After `ui.attach_image`, `orchestrator.visual_session.count >= 1` and `.jpg` exists on disk.
- Suite green vs baseline.

**Traps:**
- **TRAP 1:** `VisualSessionStore` is additive only. Do NOT remove any existing `_pending_image_b64` write.
- **TRAP 2:** `store_dir.mkdir(parents=True, exist_ok=True)` must run in `__init__`.
- **TRAP 3:** `load_b64()` must catch `OSError` and return `None` — never raise.
- **TRAP 4:** Zero `Any`. `VisualArtifact` is a typed `@dataclass`, not `dict[str, Any]`.

**STOP gate:** None. Record baseline test count before Phase 0 commit.

---

## Phase 1 - Sticky Session Image & Epistemic Vision Guard

**Goal:** On vision follow-up turns, reload the active session image from disk and inject it. If the user asks a vision question but no image is in the session store, emit an honest epistemic refusal.

**Rationale:** Closes the root cause of Turn 2 confabulation. Disk reload costs ~1ms. Text-only turns that do not reference vision inject zero extra tokens, preserving KV cache.

**Manifest:**

| File | Action |
|---|---|
| `src/lucca/core/turn_pipeline.py` | Modify `run()` at line 893. Add `_is_vision_query()` classvar and epistemic guard. Add `VisualSessionStore` import at module top. |
| `src/lucca/core/orchestrator.py` | In `UI_CLEAR_IMAGE` event handler, also call `self.visual_session.clear()`. |
| `tests/test_vision_ingestion.py` | Add `test_multiturn_sticky_image_continuity()` and `test_vision_guard_no_image()`. |

**Replace lines 893-896 in `turn_pipeline.py:run()` with:**

```python
# WO-37 Phase 1: Sticky Session Image
_new_image = inp.image_b64 or getattr(self.orch, "_pending_image_b64", None)
if _new_image:
    eff_image_b64: str | None = _new_image
else:
    _store: VisualSessionStore | None = getattr(self.orch, "visual_session", None)
    _active = _store.get_active() if _store is not None else None
    if _active is not None and self._is_vision_query(user_text):
        eff_image_b64 = _store.load_b64(_active) if _store is not None else None
        if eff_image_b64:
            logger.debug("visual_session_reloaded", image_id=_active.image_id,
                         path=str(_active.path))
    else:
        eff_image_b64 = None

self.orch.current_turn_image_b64 = eff_image_b64
if hasattr(self.orch, "_pending_image_b64"):
    self.orch._pending_image_b64 = None

# Epistemic Vision Guard
if eff_image_b64 is None and self._is_vision_query(user_text):
    _store = getattr(self.orch, "visual_session", None)
    if _store is None or _store.count == 0:
        _refusal = (
            "I don't have an active image in our session to look at right now. "
            "Could you attach or capture one using the camera button?"
        )
        self.orch._speak_text(trace, _refusal)
        self.orch._publish_caption(_refusal, source="assistant", is_final=True)
        self.orch.history.append({"role": "user", "content": user_text or "[Voice]"})
        self.orch.history.append({"role": "assistant", "content": _refusal})
        self.orch.play_ring.set_flag(FLAG_EOS)
        self.orch._finalize_turn(trace, decision_id)
        return
```

**Add as `TurnPipeline` class-level attribute:**

```python
_VISION_QUERY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(in (the |this |that )?(image|screenshot|picture|photo|capture|frame)|"
        r"what (do you |can you |did you )?(see|spot|notice|observe|look at)|"
        r"describe (what|it|that|the)|"
        r"(look at|examine|inspect) (it|that|this|the image)|"
        r"what (does it|do I|does that) look like|"
        r"(what|who|where|how many) (is|are|do you see) (in|on|there))\b",
        re.IGNORECASE,
    ),
)

def _is_vision_query(self, text: str) -> bool:
    """Returns True only if the query specifically requires visual inspection."""
    if not text:
        return False
    for pat in self._VISION_QUERY_PATTERNS:
        if pat.search(text):
            return True
    return False
```

**Functional acceptance:**
- Turn 1 (image attached, vision question): `eff_image_b64` set, grounded response.
- Turn 2 (no new image, vision question): `visual_session_reloaded` log emitted, image injected, grounded response.
- Turn 3 (no new image, non-vision question): `eff_image_b64 = None`, no image injected.
- Empty store + vision question: epistemic refusal emitted, LLM never called.
- `UI_CLEAR_IMAGE` clears store. Next vision question hits epistemic guard.
- `test_multiturn_sticky_image_continuity` and `test_vision_guard_no_image` pass.
- Suite green vs baseline.

**Traps:**
- **TRAP 1:** `_is_vision_query()` must be conservative. False positives inject image unnecessarily and bloat KV cache. False negatives just miss a reload — acceptable.
- **TRAP 2:** `load_b64()` returning `None` (file deleted) must fall through to `eff_image_b64 = None`. Do NOT trigger the epistemic guard on a cache miss — only on an empty store.
- **TRAP 3:** Import `VisualSessionStore` at module top of `turn_pipeline.py`. No inline import inside `run()`.
- **TRAP 4:** The epistemic guard early return MUST call `_finalize_turn()` before returning.

---

## Phase 2 - NLI Model Swap (ModernBERT to MiniLM-L6)

**Goal:** Replace the ModernBERT-base OpenVINO model (149M params, 60-80ms/pair) with `cross-encoder/nli-MiniLM2-L6-H768` (22M params, Apache-2.0, 8-12ms/pair), eliminating the 81% verification timeout rate without any custom training.

**Manifest:**

| File | Action |
|---|---|
| `scripts/export_nli_minilm.py` (new) | One-time export script to download and convert model to OpenVINO INT8 IR. |
| `src/lucca/senses/verifier.py` | Add `VERIFIER_MINILM_DIR` constant. Change `DEFAULT_VERIFIER_DIR` to point to it. Update docstring. |
| `src/lucca/core/config.py` | Add `VerifierSettings(BaseModel)` with `model_dir` and `timeout_ms` fields. Add `verifier: VerifierSettings` to `LuccaConfig`. |
| `pyproject.toml` | Add `[project.optional-dependencies]` section `[export]` containing `optimum-intel`. |
| `tests/test_verifier.py` | Add `test_verifier_latency_p95_under_50ms()` asserting 10 sequential pairs each complete in <= 50ms. |

**Export script (run once, not part of runtime):**

```python
# scripts/export_nli_minilm.py
# uv run --extra export python scripts/export_nli_minilm.py
MODEL_ID = "cross-encoder/nli-MiniLM2-L6-H768"
OUT_DIR = Path(r"C:\ProjectLucca\models\verifier_minilm")
# Export via optimum-intel OVModelForSequenceClassification with load_in_8bit=True
# Save model + tokenizer to OUT_DIR
# Assert openvino_model.xml, openvino_model.bin, tokenizer.json all exist
```

**Label mapping check:** After export, inspect `OUT_DIR/config.json` `id2label`. The model uses `{0: "contradiction", 1: "entailment", 2: "neutral"}`. Verify this matches the logit-index-to-`VerifierLabel` mapping in `_run_inference()`. If it differs, update `_run_inference()` mapping only — do NOT change the `VerifierLabel` enum.

**STOP gate:** Run export script. Confirm `openvino_model.xml`, `openvino_model.bin`, `tokenizer.json` exist. Record file sizes. Do not proceed until confirmed.

**Functional acceptance:**
- `VerifierWorker(model_dir=VERIFIER_MINILM_DIR)` initialises without error.
- `check_consistency("The cat is on the mat.", "There is a cat on the mat.")` returns `label=ENTAILMENT`.
- `check_consistency("The cat is on the mat.", "There is no cat here.")` returns `label=CONTRADICTION`.
- `test_verifier_latency_p95_under_50ms()` passes.
- All pre-existing `tests/test_verifier.py` tests pass.
- Suite green vs baseline.

**Traps:**
- **TRAP 1:** Do NOT raise `timeout_ms`. The model must fit in 50ms. If it does not, STOP and report.
- **TRAP 2:** The existing fallback in `_init_model()` (graceful degradation when `openvino_model.xml` absent) must remain intact.
- **TRAP 3:** `optimum-intel` goes under `[export]` optional dependency, not core. Runtime must not import it.

---

## Phase 3 - Belief Stance Topic Extraction Fix

**Goal:** Fix `_extract_stance_topic()` so idiomatic phrases like "when I think about it" do not produce garbage `ASSISTANT_BELIEF` topics like `topic='about it'`.

**Manifest:**

| File | Action |
|---|---|
| `src/lucca/core/memory_commit_service.py` | Replace `_extract_stance_topic()` (lines 39-50) with the version below. Add module-level `_TOPIC_STOPWORDS` constant before the function. |
| `tests/test_memory_commit_service.py` | Add `test_stance_topic_extraction_stopword_filter()`. |

**Replace lines 39-50 in `memory_commit_service.py` with:**

```python
_TOPIC_STOPWORDS: frozenset[str] = frozenset({
    "it", "that", "this", "so", "about", "about it", "about that",
    "about this", "of it", "of that", "the same", "as much",
    "much", "quite", "very", "really", "honestly",
})


def _extract_stance_topic(text: str) -> str:
    """Extracts candidate topic from a first-person stance utterance (Spec §7, WP-2).

    Applies a stopword/pronoun filter: idiomatic phrases like 'when I think about it'
    do not produce topics like 'about it'. Falls back to the pre-marker clause (the
    main subject) or full text[:40] if no meaningful candidate is found.
    """
    lower = text.lower()
    for marker in STANCE_MARKERS:
        if marker in lower:
            idx = lower.find(marker)
            sub = text[idx + len(marker) :].strip(" ,:.-")
            if sub:
                clause = re.split(r"[.!?;\n]+", sub)[0].strip()
                candidate = clause[:40].strip()
                if candidate and candidate.lower() not in _TOPIC_STOPWORDS:
                    words = candidate.lower().split()
                    if not all(w in _TOPIC_STOPWORDS for w in words):
                        return candidate
    # Fallback: use the pre-marker clause (the main subject of the sentence)
    for marker in STANCE_MARKERS:
        if marker in lower:
            pre = text[: lower.find(marker)].strip(" ,:.-")
            if pre:
                clause = re.split(r"[.!?;\n]+", pre)[-1].strip()
                candidate = clause[:40].strip()
                if candidate and candidate.lower() not in _TOPIC_STOPWORDS:
                    return candidate
    return text[:40].strip()
```

**Functional acceptance:**
- `_extract_stance_topic("My engagement register is quite high when I think about it")` does NOT return `"about it"`. Expected return: `"My engagement register is quite high"`.
- `_extract_stance_topic("I think about it a lot")` does not return `"about it"`.
- `_extract_stance_topic("I believe that neural scaling is the key insight here")` returns `"that neural scaling is the key insight"` (existing behaviour preserved).
- `test_stance_topic_extraction_stopword_filter` passes.
- Suite green vs baseline.

**Traps:**
- **TRAP 1:** `_TOPIC_STOPWORDS` is a module-level `frozenset` constant — outside the function, not constructed on each call.
- **TRAP 2:** Do NOT add bare `"that"` to `_TOPIC_STOPWORDS`. "I believe that neural scaling..." must still extract the content.
- **TRAP 3:** The fallback to the pre-marker clause is the key new behaviour. Test explicitly: `"My engagement register is quite high when I think about it"` must extract from the pre-marker part.

---

## Phase 4 - README Truthfulness & Repository Hygiene

**Goal:** Rewrite README to under 150 lines with honest benchmark labelling, add a Known Limitations section, consolidate `AGENTS.md`/`GEMINI.md`, and add `scratch*/` to `.gitignore`. Documentation-only phase — no source code changes.

**Golden rule for this phase:** Never alter measured results or benchmark artifacts. Change wording, not numbers. Every claim must cite an evidence file.

**Manifest:**

| File | Action |
|---|---|
| `README.md` | Rewrite to < 150 lines. Structure: what it is, requirements, quick start, architecture link, benchmark table (Author-measured, with evidence links), known limitations, research note, license. |
| `AGENTS.md` | Canonical agent rules file. Migrate any unique content from `GEMINI.md`. |
| `GEMINI.md` | Reduce to a 3-line redirect stub pointing to `AGENTS.md`. |
| `.gitignore` | Add `scratch*/` entry. |
| `luccadocs/` cross-references | Update any link pointing to `GEMINI.md` to point to `AGENTS.md`. |

**Required README sections:**

1. **One-paragraph description** (what Lucca is, no jargon).
2. **Status block** — "Single-developer research project. Hardware-specific. All benchmarks author-measured on one machine. No independent reproduction yet."
3. **Known Limitations** — must include:
   - Self-run benchmarks not externally verified.
   - Truth-in-Receipt: 1/23 ungrounded action claims detected in 23-utterance live battery. Output supervision is not a reliable safety boundary yet.
   - NLI verifier: 81% timeout rate under production load (being fixed in WO-37).
   - Hardware-specific: full functionality requires RTX GPU + NPU + WSL2 + Docker.
4. **Requirements** — concise bullet list.
5. **Quick Start** — < 10 lines.
6. **Architecture** — one link to `luccadocs/ARCHITECTURE.md`.
7. **Benchmark Results** — table with columns: Benchmark, Config, Result, Evidence file. Replace all "Verified" labels with "Author-measured". Each row must have an evidence file path.
8. **Research** — one link to `luccadocs/research/README.md` + "Papers are drafts, not peer-reviewed."
9. **License** — one line.

**Functional acceptance:**
- `README.md` line count <= 150.
- No scorecard row contains the word "Verified" without a linked evidence artifact.
- "Known Limitations" section is present and includes the 1/23 Truth-in-Receipt figure.
- `GEMINI.md` body <= 10 lines, redirects to `AGENTS.md`.
- `scratch*/` is in `.gitignore`.
- Suite green vs baseline (no source changes; baseline must not regress).

**Traps:**
- **TRAP 1:** Do NOT change any benchmark number. If a result is 91.0%, it stays 91.0%.
- **TRAP 2:** Do NOT delete `scratch_*` directory contents from git history. Add `.gitignore` entries only.
- **TRAP 3:** Run the full test suite after `GEMINI.md` consolidation. `test_static_gates.py` may check `AGENTS.md` content. Fix gate regressions before committing.
- **TRAP 4:** The 1/23 Truth-in-Receipt figure is the most critical honesty disclosure — it must be in the "Known Limitations" section, not buried.

---

## Pre-Registered Acceptance Gates (WO-37)

- **`G-WO37-VISUAL-STORE`**: `VisualSessionStore.store_image()` writes `.jpg`, returns typed `VisualArtifact`, deduplicates by SHA-256, evicts at MAX_IMAGES=8. `load_b64()` round-trips. `Orchestrator` instantiates `self.visual_session` without error.

- **`G-WO37-STICKY-IMAGE`**: Turn 1 image attached + vision question -> grounded response. Turn 2 text-only vision follow-up -> `visual_session_reloaded` log + grounded response. Turn 3 non-vision text -> no image injected. `test_multiturn_sticky_image_continuity` passes.

- **`G-WO37-VISION-GUARD`**: Empty `VisualSessionStore` + vision question -> epistemic refusal emitted, LLM never called. `test_vision_guard_no_image` passes.

- **`G-WO37-NLI-LATENCY`**: `VerifierWorker` loads `verifier_minilm`. 10 sequential NLI pairs each complete in <= 50ms. `test_verifier_latency_p95_under_50ms` passes.

- **`G-WO37-BELIEF-TOPIC`**: `_extract_stance_topic("My engagement register is quite high when I think about it")` does NOT return `"about it"`. `test_stance_topic_extraction_stopword_filter` passes.

- **`G-WO37-README`**: `README.md` <= 150 lines. No "Verified" without evidence link. "Known Limitations" present with 1/23 figure. `GEMINI.md` is a redirect stub.

- **`G-WO37-REGRESSION`**: Full test suite green with 0 failures across all phases.
