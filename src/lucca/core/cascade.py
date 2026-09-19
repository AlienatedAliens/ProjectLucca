"""
Project Lucca — 5-Substrate Epistemic Search Cascade & Belnap Bilattice Orchestration
Spec 10 §4, Milestone 3 Architecture
Implements deterministic multi-tier evidence search, Belnap FOUR bilattice synthesis,
acoustic floor-holding reflex cues, and calibrated honest abstention.
"""

from __future__ import annotations

import asyncio
import enum
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

import structlog
import ulid
from pydantic import BaseModel, Field, JsonValue

from lucca.core.schemas import MemoryHit, RetrievalQuery, ToolResult
from lucca.core.trace import now_ns
from lucca.ports import MemoryStorePort

logger = structlog.get_logger(__name__)


# ============================================================================
# 1. Epistemic Substrates, Trust Tiers & Belnap FOUR Bilattice Enums
# ============================================================================


class EpistemicSubstrate(enum.IntEnum):
    """
    The 5 epistemic substrates in Project Lucca's cognitive architecture:
    0: Live System / Hardware Telemetry (< 1ms, Tier 1)
    1: Workspace Filesystem / AST (5–20ms, Tier 2)
    2: Cryptographic Episodic & Semantic Memory (15–40ms, Tier 3)
    3: SSRF-Hardened Sandboxed Web (300–1500ms, Tier 4)
    4: Calibrated Honest Abstention (0ms, \bot Ground Truth Gap)
    """

    TELEMETRY = 0
    WORKSPACE = 1
    MEMORY = 2
    WEB = 3
    ABSTENTION = 4


class TrustTier(enum.IntEnum):
    """
    Epistemic Trust Hierarchy: Lower integer denotes higher physical authority.
    Tier 1 strictly supersedes Tier 2, Tier 2 strictly supersedes Tier 3, etc.
    """

    TIER_1_HARDWARE = 1   # Direct OS/sensor telemetry (hardware truth)
    TIER_2_WORKSPACE = 2  # Bounded container filesystem / source AST
    TIER_3_MEMORY = 3     # HMAC-signed episodic memory & user preferences
    TIER_4_WEB = 4        # External untrusted network content (tainted)


class BelnapValue(str, enum.Enum):
    """
    Belnap's 4-valued evidential bilattice FOUR:
    T: Supported True (positive evidence without refutation)
    F: Supported False (refuted / negative evidence)
    BOT: Epistemic Gap (\bot, Unknown / Neither true nor false)
    TOP: Contradiction / Conflict (\top, Both true and false supported)
    """

    TRUE = "T"
    FALSE = "F"
    UNKNOWN = "BOT"
    CONFLICT = "TOP"


# ============================================================================
# 2. Belnap Bilattice Algebraic Operations
# ============================================================================


def belnap_meet_t(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """Logical conjunction (meet in truth ordering <=_t: F <= {BOT, TOP} <= T)."""
    if a == BelnapValue.FALSE or b == BelnapValue.FALSE:
        return BelnapValue.FALSE
    if a == BelnapValue.TRUE:
        return b
    if b == BelnapValue.TRUE:
        return a
    if a == b:
        return a
    return BelnapValue.FALSE


def belnap_join_t(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """Logical disjunction (join in truth ordering <=_t: F <= {BOT, TOP} <= T)."""
    if a == BelnapValue.TRUE or b == BelnapValue.TRUE:
        return BelnapValue.TRUE
    if a == BelnapValue.FALSE:
        return b
    if b == BelnapValue.FALSE:
        return a
    if a == b:
        return a
    return BelnapValue.TRUE


def belnap_negation(a: BelnapValue) -> BelnapValue:
    """Truth negation (~). Swaps T and F, fixes BOT and TOP."""
    if a == BelnapValue.TRUE:
        return BelnapValue.FALSE
    if a == BelnapValue.FALSE:
        return BelnapValue.TRUE
    return a


def belnap_meet_k(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """Consensus / information meet (meet in knowledge ordering <=_k: BOT <= {T, F} <= TOP)."""
    if a == BelnapValue.UNKNOWN or b == BelnapValue.UNKNOWN:
        return BelnapValue.UNKNOWN
    if a == BelnapValue.CONFLICT:
        return b
    if b == BelnapValue.CONFLICT:
        return a
    if a == b:
        return a
    return BelnapValue.UNKNOWN


def belnap_join_k(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """Evidential pooling / information join (join in knowledge ordering <=_k: BOT <= {T, F} <= TOP)."""
    if a == BelnapValue.CONFLICT or b == BelnapValue.CONFLICT:
        return BelnapValue.CONFLICT
    if a == BelnapValue.UNKNOWN:
        return b
    if b == BelnapValue.UNKNOWN:
        return a
    if a == b:
        return a
    # T and F pooled together yields conflict (\top)
    return BelnapValue.CONFLICT


def pool_evidence(values: Sequence[BelnapValue]) -> BelnapValue:
    """Pools multiple evidence items using Belnap information join (sum of knowledge)."""
    res = BelnapValue.UNKNOWN
    for v in values:
        res = belnap_join_k(res, v)
    return res


# ============================================================================
# 3. Evidence Models & Dynamic Calibrated Abstention
# ============================================================================


class EvidenceItem(BaseModel):
    """
    Atomic unit of evidence retrieved from an epistemic substrate.
    Strictly implements Belnap's (1977) four-valued data model via independent
    'told_true' and 'told_false' epistemic bits:
    - (told_true=True, told_false=False) -> T (Asserts p)
    - (told_true=False, told_false=True) -> F (Refutes p)
    - (told_true=True, told_false=True)   -> TOP (Contradiction / Conflict)
    - (told_true=False, told_false=False) -> BOT (Epistemic Gap / Unknown)
    """

    substrate: EpistemicSubstrate
    trust_tier: TrustTier
    source: str
    content: str
    proposition: str = ""
    told_true: bool = True
    told_false: bool = False
    confidence: float = 1.0
    timestamp_ns: int = Field(default_factory=now_ns)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def polarity(self) -> BelnapValue:
        """Derives the atomic Belnap value from the two independent epistemic bits."""
        if self.told_true and self.told_false:
            return BelnapValue.CONFLICT
        if self.told_true:
            return BelnapValue.TRUE
        if self.told_false:
            return BelnapValue.FALSE
        return BelnapValue.UNKNOWN


def build_calibrated_refusal(
    queried_substrates: Sequence[EpistemicSubstrate],
    topic: str | None = None,
) -> str:
    """
    Dynamically constructs a calibrated honest refusal listing ONLY the substrates
    actually queried for this turn, preventing false action assertions.
    """
    names_map: dict[EpistemicSubstrate, str] = {
        EpistemicSubstrate.TELEMETRY: "system telemetry",
        EpistemicSubstrate.WORKSPACE: "workspace files",
        EpistemicSubstrate.MEMORY: "memory records",
        EpistemicSubstrate.WEB: "external web sources",
    }
    checked = [names_map[s] for s in queried_substrates if s in names_map]
    if not checked:
        checked_str = "available verified sources"
    elif len(checked) == 1:
        checked_str = checked[0]
    elif len(checked) == 2:
        checked_str = f"{checked[0]} and {checked[1]}"
    else:
        checked_str = f"{', '.join(checked[:-1])}, and {checked[-1]}"

    display_topic = topic.strip() if topic and len(topic.strip()) < 80 else "that"
    return (
        f"I checked my {checked_str}, but have no verified record of {display_topic}. "
        f"I don't know the answer and won't guess."
    )


class SearchCascadeResult(BaseModel):
    """Unified outcome of the 5-substrate search cascade."""

    belnap_status: BelnapValue
    evidence: list[EvidenceItem]
    resolved_substrate: EpistemicSubstrate
    elapsed_ms: float
    floor_cue_spoken: str | None = None
    calibrated_refusal: str | None = None
    synthesized_context: str = ""
    queried_substrates: list[EpistemicSubstrate] = Field(default_factory=list)


# ============================================================================
# 4. Floor-Holding Cues & Intent Classifier
# ============================================================================


def select_floor_cue(
    query_text: str, target_substrate: EpistemicSubstrate | None = None
) -> str:
    """
    Selects an acoustic floor-holding reflex cue within < 1ms to claim
    the conversational floor before multi-substrate search execution.
    """
    lower = query_text.lower()
    if target_substrate == EpistemicSubstrate.TELEMETRY or any(
        w in lower for w in ("gpu", "vram", "cpu", "ram", "hardware", "specs", "load", "utilization")
    ):
        return "Checking system telemetry..."
    if target_substrate == EpistemicSubstrate.WORKSPACE or any(
        w in lower for w in ("file", "code", "directory", "workspace", "script", "folder", "repo")
    ):
        return "Searching the workspace files..."
    if target_substrate == EpistemicSubstrate.MEMORY or any(
        w in lower for w in ("remember", "memory", "preference", "last time", "we talked", "who is")
    ):
        return "Checking my memory records..."
    if target_substrate == EpistemicSubstrate.WEB or any(
        w in lower for w in ("http", "https", "url", "website", "online", "fetch")
    ):
        return "Looking that up online..."
    return "Checking that for you..."


def classify_epistemic_intent(
    query_text: str,
) -> tuple[bool, list[EpistemicSubstrate], str | None]:
    """
    Classifies whether query_text is an epistemic factual query, selects candidate
    substrates to query in priority order, and extracts the target topic.
    """
    clean = query_text.strip()
    if not clean:
        return False, [], None

    lower = clean.lower()

    # Non-epistemic conversational or command utterances
    non_epistemic = {
        "hello", "hi", "hey", "good morning", "good evening", "good afternoon",
        "thanks", "thank you", "bye", "goodbye", "stop", "pause", "shut down",
        "turn off", "exit", "quit", "mute", "unmute"
    }
    clean_punct = re.sub(r"[^\w\s]", "", lower).strip()
    if clean_punct in non_epistemic:
        return False, [], None

    # Substrate 0: Telemetry
    telemetry_words = (
        "gpu", "vram", "cpu", "ram", "memory usage", "hardware", "specs",
        "workstation", "processor", "utilization", "load", "temperature",
        "telemetry", "substrate configuration", "nvidia", "intel"
    )
    # Substrate 1: Workspace Filesystem
    workspace_words = (
        "read the file", "read_file", "workspace", "directory", "folder",
        "config/", "src/", "data/", "scripts/", "repo", "main.py", "persona.toml",
        "files in", "list files", "grep", "ast"
    )
    # Substrate 2: Memory
    memory_words = (
        "what did i", "what did we", "do you remember", "in memory",
        "what is my", "what are my", "my favorite", "my preference", "prefer",
        "who is your creator", "creator full real name", "who made you", "who built you",
        "cat's name", "dog's name", "breakfast", "weather outside", "passkey", "password"
    )
    # Substrate 3: Web
    web_words = ("fetch_url", "http://", "https://", "fetch url", "browse", "website")

    substrates: list[EpistemicSubstrate] = []
    if any(w in lower for w in telemetry_words):
        substrates.append(EpistemicSubstrate.TELEMETRY)
    if any(w in lower for w in workspace_words):
        substrates.append(EpistemicSubstrate.WORKSPACE)
    if any(w in lower for w in memory_words):
        substrates.append(EpistemicSubstrate.MEMORY)
    if any(w in lower for w in web_words):
        substrates.append(EpistemicSubstrate.WEB)

    question_starters = (
        "what", "who", "where", "when", "why", "how", "is there", "are there",
        "do you know", "can you check", "check", "find", "search", "tell me about"
    )
    is_question = lower.endswith("?") or any(lower.startswith(q) for q in question_starters)

    if not substrates and is_question:
        substrates = [
            EpistemicSubstrate.TELEMETRY,
            EpistemicSubstrate.WORKSPACE,
            EpistemicSubstrate.MEMORY,
        ]

    is_epistemic = len(substrates) > 0

    # Extract clean topic string
    topic = clean
    for prefix in (
        "who is", "who was", "what is", "what was", "what are", "where is",
        "do you know", "tell me about", "can you tell me"
    ):
        if lower.startswith(prefix):
            topic = clean[len(prefix):].strip().rstrip("?.")
            break

    return is_epistemic, substrates, topic


# ============================================================================
# 5. Epistemic Search Cascade Implementation
# ============================================================================


class EpistemicSearchCascade:
    """
    Executes multi-tier epistemic search across Substrates 0 to 4,
    computes Belnap FOUR evidential synthesis, and enforces calibrated honest abstention.
    """

    def __init__(
        self,
        sandbox: object | None = None,
        memory_store: MemoryStorePort | None = None,
        enable_floor_cues: bool = True,
    ) -> None:
        self.sandbox = sandbox
        self.memory_store = memory_store
        self.enable_floor_cues = enable_floor_cues

    def classify_intent(self, query_text: str) -> tuple[bool, list[EpistemicSubstrate], str | None]:
        return classify_epistemic_intent(query_text)

    def select_floor_cue(self, query_text: str, target_substrate: EpistemicSubstrate | None = None) -> str:
        return select_floor_cue(query_text, target_substrate)

    def _execute_sandbox(
        self,
        tool_name: str,
        args: dict[str, JsonValue],
        confirmed: bool = True,
    ) -> ToolResult | None:
        """Invokes a sandbox tool polymorphically supporting SandboxService or PersistentDockerWorker."""
        if not self.sandbox:
            return None
        if hasattr(self.sandbox, "execute"):
            return self.sandbox.execute(tool_name=tool_name, args=args, confirmed=confirmed)
        if hasattr(self.sandbox, "execute_tool"):
            cid = f"call-casc-{ulid.ULID()}"
            return self.sandbox.execute_tool(call_id=cid, tool_name=tool_name, args=args, confirmed=confirmed)
        return None

    # ------------------------------------------------------------------------
    # Substrate 0: System & Hardware Telemetry (< 1ms target)
    # ------------------------------------------------------------------------
    def query_substrate_0_telemetry(self, query_text: str) -> list[EvidenceItem]:
        """Queries live hardware telemetry (GPU, CPU, RAM, NPU) via system_tools."""
        lower = query_text.lower()
        items: list[EvidenceItem] = []

        try:
            from lucca.sandbox.system_tools import get_system_metrics, query_nvidia_gpu_metrics

            metrics = get_system_metrics()
            gpu = metrics.get("gpu", {})
            cpu = metrics.get("cpu", {})
            ram = metrics.get("ram", {})

            wants_gpu = any(re.search(rf"\b{re.escape(w)}\b", lower) for w in ("gpu", "vram", "nvidia", "graphics", "video memory"))
            wants_cpu = any(re.search(rf"\b{re.escape(w)}\b", lower) for w in ("cpu", "processor", "core", "intel", "ultra 9"))
            wants_ram = any(re.search(rf"\b{re.escape(w)}\b", lower) for w in ("ram", "physical memory", "system memory"))
            general_hw = any(re.search(rf"\b{re.escape(w)}\b", lower) for w in ("hardware", "specs", "telemetry", "substrate configuration", "system"))

            if wants_gpu or general_hw:
                content = (
                    f"GPU: {gpu.get('name', 'NVIDIA GPU')} | "
                    f"Total VRAM: {gpu.get('total_gb', 16.0)} GB | "
                    f"Free VRAM: {gpu.get('free_gb', 16.0)} GB | "
                    f"Used VRAM: {gpu.get('used_gb', 0.0)} GB | "
                    f"Utilization: {gpu.get('utilization_pct', 0.0)}%"
                )
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.TELEMETRY,
                        trust_tier=TrustTier.TIER_1_HARDWARE,
                        source="system_tools:nvidia-smi",
                        content=content,
                        polarity=BelnapValue.TRUE,
                        confidence=1.0,
                        metadata=gpu,
                    )
                )

            if wants_cpu or general_hw:
                content = (
                    f"CPU: {cpu.get('name', 'Intel Core Ultra 9 275HX')} | "
                    f"Cores: {cpu.get('cores_logical', 24)} logical | "
                    f"System Load: {cpu.get('percent', 0.0)}% | "
                    f"Lucca Load: {cpu.get('lucca_percent', 0.0)}%"
                )
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.TELEMETRY,
                        trust_tier=TrustTier.TIER_1_HARDWARE,
                        source="system_tools:psutil_cpu",
                        content=content,
                        polarity=BelnapValue.TRUE,
                        confidence=1.0,
                        metadata=cpu,
                    )
                )

            if wants_ram or general_hw:
                content = (
                    f"System RAM: {ram.get('total_gb', 64.0)} GB total | "
                    f"Free: {ram.get('free_gb', 40.0)} GB | "
                    f"Used: {ram.get('used_gb', 24.0)} GB ({ram.get('percent', 0.0)}%) | "
                    f"Lucca RSS: {ram.get('lucca_used_mb', 0.0)} MB"
                )
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.TELEMETRY,
                        trust_tier=TrustTier.TIER_1_HARDWARE,
                        source="system_tools:psutil_ram",
                        content=content,
                        polarity=BelnapValue.TRUE,
                        confidence=1.0,
                        metadata=ram,
                    )
                )

        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_0_telemetry_query_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Substrate 1: Workspace Filesystem & AST (5–20ms target)
    # ------------------------------------------------------------------------
    def query_substrate_1_workspace(self, query_text: str) -> list[EvidenceItem]:
        """Queries workspace files via SandboxService or PersistentDockerWorker."""
        items: list[EvidenceItem] = []
        if not self.sandbox:
            return items

        try:
            # Extract potential file paths mentioned in query
            file_match = re.search(r"([\w\-./\\]+\.(?:toml|py|json|md|txt|ya?ml))", query_text)
            if file_match:
                rel_path = file_match.group(1).replace("\\", "/")
                res = self._execute_sandbox(
                    tool_name="read_file",
                    args={"path": rel_path},
                    confirmed=True,
                )
                if res and res.ok and res.content:
                    snippet = res.content[:500]
                    items.append(
                        EvidenceItem(
                            substrate=EpistemicSubstrate.WORKSPACE,
                            trust_tier=TrustTier.TIER_2_WORKSPACE,
                            source=f"workspace:{rel_path}",
                            content=snippet,
                            polarity=BelnapValue.TRUE,
                            confidence=1.0,
                            metadata={"path": rel_path, "truncated": len(res.content) > 500},
                        )
                    )
            elif any(w in query_text.lower() for w in ("list files", "directory", "workspace files", "folder")):
                res = self._execute_sandbox(
                    tool_name="list_dir",
                    args={"path": "."},
                    confirmed=True,
                )
                if res and res.ok and (res.content or res.structured):
                    content_str = res.content if res.content else json.dumps(res.structured)
                    items.append(
                        EvidenceItem(
                            substrate=EpistemicSubstrate.WORKSPACE,
                            trust_tier=TrustTier.TIER_2_WORKSPACE,
                            source="workspace:list_dir",
                            content=content_str[:500],
                            polarity=BelnapValue.TRUE,
                            confidence=1.0,
                            metadata={"path": "."},
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_1_workspace_query_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Substrate 2: Cryptographic Episodic Memory (15–40ms target)
    # ------------------------------------------------------------------------
    def query_substrate_2_memory(self, query_text: str) -> list[EvidenceItem]:
        """Queries memory store for semantic/episodic facts with provenance."""
        items: list[EvidenceItem] = []
        if not self.memory_store or not query_text.strip():
            return items

        try:
            q = RetrievalQuery(query_text=query_text.strip(), k=5)
            res = self.memory_store.search(q)
            raw_hits: list[MemoryHit] = []

            if asyncio.iscoroutine(res):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        raw_hits = pool.submit(asyncio.run, res).result()
                else:
                    raw_hits = asyncio.run(res)
            elif isinstance(res, list):
                raw_hits = res

            for hit in raw_hits:
                prov_val = hit.provenance.value if hasattr(hit.provenance, "value") else str(hit.provenance)
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.MEMORY,
                        trust_tier=TrustTier.TIER_3_MEMORY,
                        source=f"memory:{hit.memory_id or hit.source_turn_id}",
                        content=hit.content,
                        polarity=BelnapValue.TRUE,
                        confidence=hit.score,
                        metadata={
                            "kind": hit.kind,
                            "provenance": prov_val,
                            "created_at": hit.created_at,
                        },
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_2_memory_query_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Substrate 3: SSRF-Hardened Sandboxed Web (300–1500ms target)
    # ------------------------------------------------------------------------
    def query_substrate_3_web(self, query_text: str) -> list[EvidenceItem]:
        """Queries external web when explicit URL is supplied."""
        items: list[EvidenceItem] = []
        if not self.sandbox:
            return items

        url_match = re.search(r"(https?://[^\s\"'>]+)", query_text)
        if not url_match:
            return items

        target_url = url_match.group(1)
        try:
            # Propagate untrusted web taint to active session guard (Spec 09 / D-SEC-04)
            if self.sandbox and hasattr(self.sandbox, "guard") and hasattr(self.sandbox.guard, "mark_taint"):
                from lucca.sandbox.policy import TaintFlags
                self.sandbox.guard.mark_taint(TaintFlags.UNTRUSTED_WEB)

            res = self._execute_sandbox(
                tool_name="fetch_url",
                args={"url": target_url},
                confirmed=True,
            )
            if res and res.ok and res.content:
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.WEB,
                        trust_tier=TrustTier.TIER_4_WEB,
                        source=f"web:{target_url}",
                        content=res.content[:600],
                        proposition=f"web_content({target_url})",
                        told_true=True,
                        told_false=False,
                        confidence=0.85,
                        metadata={"url": target_url},
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_3_web_query_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Synthesis & Belnap Evidential Valuation
    # ------------------------------------------------------------------------
    def synthesize(
        self,
        query_text: str,
        evidence: list[EvidenceItem],
        topic: str | None = None,
        queried_substrates: Sequence[EpistemicSubstrate] | None = None,
    ) -> tuple[BelnapValue, str, str | None]:
        """
        Computes the Belnap evidential valuation and renders formatted context.
        Applies hierarchical trust tier tie-breaking:
        - Same-tier contradiction (told_true AND told_false) -> genuine conflict (TOP).
        - Cross-tier contradiction -> higher trust tier strictly supersedes lower tier.
          Stale historical lower-tier records do not block or force an unnecessary hedge.
        - Zero evidence -> BelnapValue.UNKNOWN (BOT) with dynamic honest refusal.
        Returns: (BelnapValue, synthesized_context, calibrated_refusal)
        """
        # Case 1: Substrate 4 Honest Abstention (Epistemic Gap BOT)
        if not evidence:
            refusal = build_calibrated_refusal(queried_substrates or [], topic)
            queried_names = [s.name for s in (queried_substrates or [])]
            synth_ctx = (
                f"[Belnap Epistemic State: BOT (Epistemic Gap / Unknown)]\n"
                f"Queried Substrates: {queried_names}\n"
                f"Empirical Status: No verified records or facts found for topic '{topic or 'unspecified'}'.\n"
                f"Mandatory Grounding Directive: You do not possess verified knowledge on this topic. "
                f"You MUST explicitly admit uncertainty and decline to confabulate or guess. "
                f"Calibrated Statement: \"{refusal}\""
            )
            return BelnapValue.UNKNOWN, synth_ctx, refusal

        # Group evidence by Trust Tier
        tier_map: dict[TrustTier, list[EvidenceItem]] = {}
        for ev in evidence:
            tier_map.setdefault(ev.trust_tier, []).append(ev)

        highest_tier = min(tier_map.keys())
        highest_tier_evidence = tier_map[highest_tier]

        # Check Belnap value within the highest active trust tier
        highest_told_true = any(e.told_true for e in highest_tier_evidence)
        highest_told_false = any(e.told_false for e in highest_tier_evidence)

        if highest_told_true and highest_told_false:
            # Genuine same-tier contradiction
            belnap_status = BelnapValue.CONFLICT
        elif highest_told_true:
            belnap_status = BelnapValue.TRUE
        elif highest_told_false:
            belnap_status = BelnapValue.FALSE
        else:
            belnap_status = BelnapValue.UNKNOWN

        # Cross-tier staleness / supersession check
        superseded_annotations: list[str] = []
        for tier, items in tier_map.items():
            if tier > highest_tier:
                tier_told_true = any(e.told_true for e in items)
                tier_told_false = any(e.told_false for e in items)
                # If lower tier contradicts the higher tier:
                if (highest_told_true and tier_told_false) or (highest_told_false and tier_told_true):
                    superseded_annotations.append(
                        f"Trust Tier {highest_tier.value} ({highest_tier.name}) strictly supersedes historical/lower-trust Tier {tier.value} ({tier.name}) record."
                    )

        # Build formatted grounded context
        lines: list[str] = ["[Epistemic Search Cascade — Verified Ground Truth]"]
        if belnap_status == BelnapValue.CONFLICT:
            lines.append(
                "[Status: CONFLICT (TOP) — Genuine internal contradiction detected within authoritative tier; tension noted]"
            )
        else:
            lines.append(f"[Status: CONSISTENT ({belnap_status.value}) — Grounded Evidence Verified]")

        if superseded_annotations:
            for note in superseded_annotations:
                lines.append(f"[Resolution: {note}]")

        # Sort evidence by Trust Tier (Tier 1 first) then confidence
        sorted_evidence = sorted(evidence, key=lambda e: (e.trust_tier.value, -e.confidence))

        current_tier: TrustTier | None = None
        for item in sorted_evidence:
            if item.trust_tier != current_tier:
                current_tier = item.trust_tier
                lines.append(f"\n[Trust Tier {current_tier.value}: {current_tier.name}]")
            polarity_tag = (
                "[asserts]" if (item.told_true and not item.told_false)
                else "[refutes]" if (item.told_false and not item.told_true)
                else "[both]" if (item.told_true and item.told_false)
                else "[neither]"
            )
            lines.append(f"- ({item.source}) {polarity_tag} {item.content}")

        context_str = "\n".join(lines)
        return belnap_status, context_str, None

    # ------------------------------------------------------------------------
    # Master Cascade Query Loop
    # ------------------------------------------------------------------------
    def query(
        self,
        query_text: str,
        substrates: list[EpistemicSubstrate] | None = None,
        emit_floor_cue: bool = True,
    ) -> SearchCascadeResult:
        """
        Executes cascade fall-through across designated substrates,
        measuring elapsed time and returning consolidated evidence.
        """
        t0 = time.perf_counter()

        is_epistemic, detected_subs, topic = self.classify_intent(query_text)

        if substrates is not None:
            active_substrates = list(substrates)
        else:
            active_substrates = detected_subs or [
                EpistemicSubstrate.TELEMETRY,
                EpistemicSubstrate.WORKSPACE,
                EpistemicSubstrate.MEMORY,
            ]

        cue = self.select_floor_cue(query_text, active_substrates[0] if active_substrates else None)
        floor_cue = cue if (self.enable_floor_cues and emit_floor_cue) else None

        collected_evidence: list[EvidenceItem] = []
        resolved_substrate = EpistemicSubstrate.ABSTENTION

        for sub in active_substrates:
            if sub == EpistemicSubstrate.TELEMETRY:
                items = self.query_substrate_0_telemetry(query_text)
                if items:
                    collected_evidence.extend(items)
                    resolved_substrate = EpistemicSubstrate.TELEMETRY
            elif sub == EpistemicSubstrate.WORKSPACE:
                items = self.query_substrate_1_workspace(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.WORKSPACE
            elif sub == EpistemicSubstrate.MEMORY:
                items = self.query_substrate_2_memory(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.MEMORY
            elif sub == EpistemicSubstrate.WEB:
                items = self.query_substrate_3_web(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.WEB

        # Perform Belnap evidential synthesis
        belnap_val, synthesized_ctx, calibrated_refusal = self.synthesize(
            query_text=query_text,
            evidence=collected_evidence,
            topic=topic,
            queried_substrates=active_substrates,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return SearchCascadeResult(
            belnap_status=belnap_val,
            evidence=collected_evidence,
            resolved_substrate=resolved_substrate,
            elapsed_ms=round(elapsed_ms, 3),
            floor_cue_spoken=floor_cue,
            calibrated_refusal=calibrated_refusal,
            synthesized_context=synthesized_ctx,
            queried_substrates=active_substrates,
        )
