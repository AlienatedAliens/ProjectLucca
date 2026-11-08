"""
Project Lucca — Epistemic Cascade Substrate Query Adapters (WO-43 Phase 3.3)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §3
"""

from __future__ import annotations

import platform
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import structlog
import ulid
from pydantic import JsonValue

from lucca.core.cascade_intent import _extract_target_entity, extract_clean_topic
from lucca.core.schemas import (
    MemoryHit,
    RetrievalQuery,
    ToolResult,
)
from lucca.reasoning.recall import tokenize_query
from lucca.speech.engines import ENGINE_CATALOG, parse_engine_from_spec

if TYPE_CHECKING:
    from lucca.core.cascade import EpistemicSubstrate, EvidenceItem, TrustTier
    from lucca.ports import MemoryStorePort, SemanticVerifierPort

logger = structlog.get_logger(__name__)


def _cascade_types() -> tuple[type[EpistemicSubstrate], type[TrustTier], type[EvidenceItem]]:
    from lucca.core.cascade import EpistemicSubstrate, EvidenceItem, TrustTier  # noqa: PLC0415

    return EpistemicSubstrate, TrustTier, EvidenceItem


class CascadeSubstrateAdapters:
    """Mixin/adapter class implementing Substrate 0..7 query backends for EpistemicSearchCascade."""

    sandbox: object | None
    memory_store: MemoryStorePort | None
    verifier: SemanticVerifierPort | None

    def _evaluate_polarity(self, content: str, query_text: str = "") -> tuple[bool, bool]:
        raise NotImplementedError

    def _annotate_active_memory_conflicts(self, items: list[EvidenceItem]) -> None:
        raise NotImplementedError

    def _execute_sandbox(
        self,
        tool_name: str,
        args: dict[str, JsonValue],
        confirmed: bool = True,
    ) -> ToolResult | None:
        """Invokes a sandbox tool polymorphically (SandboxService or PersistentDockerWorker)."""
        if not self.sandbox:
            return None
        if hasattr(self.sandbox, "execute"):
            res = self.sandbox.execute(tool_name=tool_name, args=args, confirmed=confirmed)
            return res if isinstance(res, ToolResult) else None
        if hasattr(self.sandbox, "execute_tool"):
            cid = f"call-casc-{ulid.ULID()}"
            res = self.sandbox.execute_tool(
                call_id=cid, tool_name=tool_name, args=args, confirmed=confirmed
            )
            return res if isinstance(res, ToolResult) else None
        return None

    # ------------------------------------------------------------------------
    # Substrate SELF: Axiomatic Persona & Self-Model (0ms, Tier 0)
    # ------------------------------------------------------------------------
    def query_substrate_self(self, query_text: str) -> list[EvidenceItem]:
        """
        Queries live persona, identity, and runtime truth (Substrate SELF - Axiomatic Tier 0).

        Runtime facts (which LLM / ASR / TTS are loaded) are read from LuccaConfig at
        query time, never hard-coded, so a brain swap is a config change and Lucca's
        self-description stays truthful.
        """
        _Sub, _Tier, _EvItem = _cascade_types()
        # Lazy imports: brain.prompt_builder / core.config import the cascade indirectly
        # (orchestrator -> cascade); importing at module top would form a cycle.
        from lucca.brain.prompt_builder import get_persona_config  # noqa: PLC0415
        from lucca.core.config import get_config  # noqa: PLC0415

        try:
            cfg = get_persona_config()
            rt = get_config()
            now_local = datetime.now().astimezone()
            time_str = now_local.strftime("%A, %B %d, %Y, %I:%M %p (%Z, UTC%z)")
            active_voice = cfg.voice or rt.tts.voice
            eng_id, _ = parse_engine_from_spec(str(active_voice))
            eng_desc = ENGINE_CATALOG.get(eng_id)
            eng_name = eng_desc.name if eng_desc else "Kokoro-82M"
            tts_info = f"speech synthesis '{eng_name}' (voice: '{active_voice}')"
            mmproj_raw = getattr(rt.llm, "mmproj", None)
            mmproj_name = Path(str(mmproj_raw)).name if mmproj_raw else "sovereign-ocr"
            vision_info = (
                f"; multimodal vision projector '{mmproj_name}' active (mode: {rt.llm.mode})"
                if (rt.llm.mode == "vision" or mmproj_raw)
                else ""
            )
            asr_name = Path(rt.asr.model).name
            content = (
                f"Agent Identity: Lucca, local AI engineer companion. "
                f"Current Local Time: {time_str}. "
                f"Archetype: {cfg.archetype}. Voice: {active_voice}. "
                f"Local Runtime: language model '{rt.llm.model_display_name()}' served by "
                f"llama-server on the dGPU (context {rt.llm.ctx} tokens){vision_info}; "
                f"speech recognition '{asr_name}' on the dGPU (CUDA float16, CPU fallback); "
                f"{tts_info}. "
                f"Host Workstation: {platform.node()} ({platform.platform()}). "
                f"Core Purpose: Pair-programming, systems debugging, and desktop automation. "
                f"Created locally for this workstation. "
                f"Admits uncertainty: {cfg.admits_uncertainty}."
            )
        except Exception as exc:  # noqa: BLE001 — degrade to static identity, never crash a turn
            logger.warning("cascade_self_substrate_fallback", error=str(exc))
            content = (
                "Lucca: local AI engineer companion for pair programming and systems engineering."
            )

        return [
            _EvItem(
                substrate=_Sub.SELF,
                trust_tier=_Tier.TIER_0_AXIOMATIC,
                source="config/persona.toml",
                content=content,
                told_true=True,
                told_false=False,
                confidence=1.0,
            )
        ]

    # ------------------------------------------------------------------------
    # Substrate CAPABILITIES: Authoritative Capability Registry (0ms, Tier 0)
    # ------------------------------------------------------------------------
    def query_substrate_capabilities(self, query_text: str) -> list[EvidenceItem]:
        """Queries registered capabilities and tools (Substrate CAPABILITIES, Tier 0).

        The tool list is always derived from the live registry. If the registry cannot be
        read, this substrate returns **no evidence** rather than a hard-coded list — a stale
        list stamped TIER_0 / confidence 1.0 would itself be a confabulated self-description.
        """
        _Sub, _Tier, _EvItem = _cascade_types()
        try:
            # Lazy import: capabilities imports the orchestrator's schemas; avoid a cycle.
            from lucca.core.capabilities import get_capability_registry  # noqa: PLC0415

            reg = get_capability_registry()
            apps = [a["key"] for a in reg.get_whitelisted_apps() if a.get("status") != "Disabled"]
            pathways = list(reg.get_reasoning_pathways().keys())
            tools = [t.function.name for t in reg.get_tool_definitions()]
            content = (
                f"Available Core Tools: {', '.join(tools)}. "
                f"Whitelisted Desktop Applications (Tool Studio): {', '.join(apps)}. "
                f"Active MicroScheme Reasoning Pathways (LISP Studio): {', '.join(pathways)}."
            )
        except Exception as exc:  # noqa: BLE001 — registry failure must yield abstention, not a crash
            logger.warning("cascade_capabilities_substrate_unavailable", error=str(exc))
            return []

        return [
            _EvItem(
                substrate=_Sub.CAPABILITIES,
                trust_tier=_Tier.TIER_0_AXIOMATIC,
                source="CapabilityRegistry",
                content=content,
                told_true=True,
                told_false=False,
                confidence=1.0,
            )
        ]

    # ------------------------------------------------------------------------
    # Substrate 0: System & Hardware Telemetry (< 1ms target)
    # ------------------------------------------------------------------------
    def query_substrate_0_telemetry(self, query_text: str) -> list[EvidenceItem]:
        """Queries live hardware telemetry (GPU, CPU, RAM, NPU, Time, Location) via system_tools."""
        _Sub, _Tier, _EvItem = _cascade_types()
        lower = query_text.lower()
        items: list[EvidenceItem] = []

        try:
            # Lazy import: system_tools pulls pynvml/psutil; keep cascade import cheap.
            from lucca.sandbox.system_tools import get_system_metrics  # noqa: PLC0415

            metrics = get_system_metrics()
            raw_gpu = metrics.get("gpu")
            gpu: dict[str, JsonValue] = raw_gpu if isinstance(raw_gpu, dict) else {}
            raw_cpu = metrics.get("cpu")
            cpu: dict[str, JsonValue] = raw_cpu if isinstance(raw_cpu, dict) else {}
            raw_ram = metrics.get("ram")
            ram: dict[str, JsonValue] = raw_ram if isinstance(raw_ram, dict) else {}

            wants_gpu = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("gpu", "vram", "nvidia", "graphics", "video memory")
            )
            wants_cpu = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("cpu", "processor", "core", "intel", "ultra 9")
            )
            wants_ram = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("ram", "physical memory", "system memory")
            )
            is_clock_freq = bool(
                re.search(r"\b(?:core|gpu|cpu|bus|memory)\s+clock\b", lower)
                or re.search(r"\bclock\s+(?:speed|rate|freq|frequency|multiplier)\b", lower)
            )
            wants_time = not is_clock_freq and any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in (
                    "what time",
                    "current time",
                    "local time",
                    "exact time",
                    "time is it",
                    "today",
                    "what day",
                    "what month",
                    "what year",
                    "wall clock",
                    "system clock",
                    "clock",
                )
            )
            wants_location = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in (
                    "location",
                    "where",
                    "located",
                    "ip",
                    "network",
                    "city",
                    "country",
                    "place",
                )
            )
            general_hw = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("hardware", "specs", "telemetry", "substrate configuration", "system")
            )

            timezone_inquiry = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in (
                    "timezone",
                    "time zone",
                    "timezones",
                    "time zones",
                    "utc offset",
                    "gmt offset",
                    "daylight saving",
                    "daylight savings",
                    "daylight-saving",
                    "dst",
                    "standard time",
                    "awst",
                    "aest",
                    "acst",
                    "pst",
                    "pdt",
                    "est",
                    "edt",
                    "cst",
                    "cdt",
                    "mst",
                    "mdt",
                    "sgt",
                    "jst",
                    "gmt",
                    "utc",
                )
            )
            wants_time = wants_time or timezone_inquiry

            if wants_time or general_hw:
                from lucca.sandbox.service import resolve_target_timezone  # noqa: PLC0415

                target_tz = resolve_target_timezone(query_text)
                if target_tz is not None:
                    now_tz = datetime.now(target_tz)
                    iana_name = target_tz.key
                    tz_abbr = now_tz.strftime("%Z")
                    utc_offset = now_tz.strftime("%z")
                    tz_dst = now_tz.dst()
                    is_dst = bool(tz_dst is not None and tz_dst.total_seconds() != 0)
                    time_str = now_tz.strftime("%A, %B %d, %Y, %I:%M:%S %p (%Z, UTC%z)")
                    content = (
                        f"Grounded Timezone: {iana_name} ({tz_abbr}, UTC{utc_offset}) | "
                        f"DST Active: {is_dst} | Time: {time_str}"
                    )
                    items.append(
                        _EvItem(
                            substrate=_Sub.TELEMETRY,
                            trust_tier=_Tier.TIER_1_HARDWARE,
                            source="system_tools:zoneinfo",
                            content=content,
                            told_true=True,
                            told_false=False,
                            confidence=1.0,
                            metadata={
                                "iana_name": iana_name,
                                "abbreviation": tz_abbr,
                                "utc_offset": utc_offset,
                                "is_dst": is_dst,
                                "local_time": time_str,
                            },
                        )
                    )
                else:
                    now_local = datetime.now().astimezone()
                    time_str = now_local.strftime("%A, %B %d, %Y, %I:%M %p (%Z, UTC%z)")
                    iana_name = (
                        getattr(now_local.tzinfo, "key", None) or now_local.tzname() or "UTC"
                    )
                    tz_abbr = now_local.strftime("%Z")
                    utc_offset = now_local.strftime("%z")
                    local_dst = now_local.dst()
                    is_dst = bool(local_dst is not None and local_dst.total_seconds() != 0)
                    content = (
                        f"Host Local Time: {time_str} | Timezone: {iana_name} "
                        f"({tz_abbr}, UTC{utc_offset}) | DST: {is_dst}"
                    )
                    items.append(
                        _EvItem(
                            substrate=_Sub.TELEMETRY,
                            trust_tier=_Tier.TIER_1_HARDWARE,
                            source="system_tools:local_clock",
                            content=content,
                            told_true=True,
                            told_false=False,
                            confidence=1.0,
                            metadata={
                                "timestamp": metrics.get("timestamp"),
                                "iana_name": iana_name,
                                "abbreviation": tz_abbr,
                                "utc_offset": utc_offset,
                                "is_dst": is_dst,
                            },
                        )
                    )

            if wants_location:
                from lucca.sandbox.service import get_host_network_and_location  # noqa: PLC0415

                net_geo = get_host_network_and_location()
                if net_geo.get("public_ip"):
                    city = net_geo.get("city")
                    region = net_geo.get("region")
                    loc_content = (
                        f"Physical Host Geolocation: {city}, {region}, "
                        f"{net_geo.get('country')} (Coordinates: {net_geo.get('coordinates')}, "
                        f"ISP: {net_geo.get('isp')}, Public IP: {net_geo.get('public_ip')})"
                    )
                else:
                    raw_lips = net_geo.get("local_ips")
                    lips_list = raw_lips if isinstance(raw_lips, list) else []
                    local_ips = ", ".join(str(x) for x in lips_list) or "local only"
                    loc_content = f"Host Network: Local IPs [{local_ips}]"

                items.append(
                    _EvItem(
                        substrate=_Sub.TELEMETRY,
                        trust_tier=_Tier.TIER_1_HARDWARE,
                        source="system_tools:network_geo",
                        content=loc_content,
                        told_true=True,
                        told_false=False,
                        confidence=1.0,
                        metadata=net_geo,
                    )
                )

            if wants_gpu or general_hw:
                content = (
                    f"GPU: {gpu.get('name', 'NVIDIA GPU')} | "
                    f"Total VRAM: {gpu.get('total_gb', 16.0)} GB | "
                    f"Free VRAM: {gpu.get('free_gb', 16.0)} GB | "
                    f"Used VRAM: {gpu.get('used_gb', 0.0)} GB | "
                    f"Utilization: {gpu.get('utilization_pct', 0.0)}%"
                )
                items.append(
                    _EvItem(
                        substrate=_Sub.TELEMETRY,
                        trust_tier=_Tier.TIER_1_HARDWARE,
                        source="system_tools:nvidia-smi",
                        content=content,
                        told_true=True,
                        told_false=False,
                        confidence=1.0,
                        metadata=gpu,
                    )
                )

            if wants_cpu or general_hw:
                content = (
                    f"CPU: {cpu.get('name', 'Host Multi-Core CPU')} | "
                    f"Cores: {cpu.get('cores_logical', 24)} logical | "
                    f"System Load: {cpu.get('percent', 0.0)}% | "
                    f"Lucca Load: {cpu.get('lucca_percent', 0.0)}%"
                )
                items.append(
                    _EvItem(
                        substrate=_Sub.TELEMETRY,
                        trust_tier=_Tier.TIER_1_HARDWARE,
                        source="system_tools:psutil_cpu",
                        content=content,
                        told_true=True,
                        told_false=False,
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
                    _EvItem(
                        substrate=_Sub.TELEMETRY,
                        trust_tier=_Tier.TIER_1_HARDWARE,
                        source="system_tools:psutil_ram",
                        content=content,
                        told_true=True,
                        told_false=False,
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
        _Sub, _Tier, _EvItem = _cascade_types()
        items: list[EvidenceItem] = []
        if not self.sandbox:
            return items

        try:
            lower = query_text.lower()

            # 1. Inbox inquiries
            if any(w in lower for w in ("inbox", "drop folder", "incoming")):
                res = self._execute_sandbox(
                    tool_name="list_dir",
                    args={"path": "inbox"},
                    confirmed=True,
                )
                if res and res.ok:
                    raw_entries = (
                        res.structured.get("entries")
                        if isinstance(res.structured, dict)
                        else None
                    )
                    entries = raw_entries if isinstance(raw_entries, list) else []
                    names = [str(e.get("name", "")) for e in entries if isinstance(e, dict)]
                    names_json: list[JsonValue] = list(names)
                    if names:
                        content_str = (
                            f"Inbox drop folder contains {len(names)} file(s) waiting "
                            f"to be imported: {', '.join(names)}. (Location: host inbox/)"
                        )
                    else:
                        content_str = "Inbox drop folder is currently empty (0 files waiting)."
                    items.append(
                        _EvItem(
                            substrate=_Sub.WORKSPACE,
                            trust_tier=_Tier.TIER_2_WORKSPACE,
                            source="workspace:inbox",
                            content=content_str,
                            told_true=True,
                            told_false=False,
                            confidence=1.0,
                            metadata={"path": "inbox", "files": names_json, "count": len(names)},
                        )
                    )
                return items

            # 2. Specific file read inquiries (e.g. "Read config/persona.toml in the workspace")
            file_match = re.search(
                r"([\w\-./\\]+\.(?:toml|py|json|md|txt|ya?ml|url))", query_text
            )
            is_explicit_listing = any(
                w in lower for w in ("list files", "directory", "folder", "all files", "what files")
            )
            if file_match and not is_explicit_listing:
                rel_path = file_match.group(1).replace("\\", "/")
                res = self._execute_sandbox(
                    tool_name="read_file",
                    args={"path": rel_path},
                    confirmed=True,
                )
                if res and res.ok and res.content:
                    snippet = res.content[:500]
                    items.append(
                        _EvItem(
                            substrate=_Sub.WORKSPACE,
                            trust_tier=_Tier.TIER_2_WORKSPACE,
                            source=f"workspace:{rel_path}",
                            content=snippet,
                            told_true=True,
                            told_false=False,
                            confidence=1.0,
                            metadata={"path": rel_path, "truncated": len(res.content) > 500},
                        )
                    )
                return items

            # 3. General workspace file listing inquiries
            is_workspace_listing = (
                any(
                    w in lower
                    for w in (
                        "list files",
                        "directory",
                        "workspace files",
                        "folder",
                        "files at all",
                        "any files",
                        "what files",
                        "have any files",
                        "do you have files",
                        "files do you have",
                        "in your workspace",
                        "in the workspace",
                        "files in workspace",
                        "show files",
                        "show me files",
                        "contents of workspace",
                        "what's in your workspace",
                        "what is in your workspace",
                        "all files",
                    )
                )
                or ("files" in lower and "workspace" in lower)
                or (
                    "files" in lower
                    and any(v in lower for v in ("have", "see", "show", "list", "any"))
                )
            )

            if is_workspace_listing:
                res = self._execute_sandbox(
                    tool_name="list_dir",
                    args={"path": "."},
                    confirmed=True,
                )
                if res and res.ok:
                    raw_entries = (
                        res.structured.get("entries")
                        if isinstance(res.structured, dict)
                        else None
                    )
                    entries = raw_entries if isinstance(raw_entries, list) else []
                    names = [str(e.get("name", "")) for e in entries if isinstance(e, dict)]
                    names_json = list(names)
                    if names:
                        content_str = (
                            f"Workspace directory contains {len(names)} item(s): "
                            f"{', '.join(names)}."
                        )
                    else:
                        content_str = "Workspace directory is currently empty (0 files)."
                    items.append(
                        _EvItem(
                            substrate=_Sub.WORKSPACE,
                            trust_tier=_Tier.TIER_2_WORKSPACE,
                            source="workspace:list_dir",
                            content=content_str,
                            told_true=True,
                            told_false=False,
                            confidence=1.0,
                            metadata={"path": ".", "files": names_json, "count": len(names)},
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_1_workspace_query_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Substrate 2: Cryptographic Episodic Memory (15–40ms target)
    # ------------------------------------------------------------------------
    def query_substrate_2_memory(
        self,
        query_text: str,
        temporal_anchor: tuple[float, float] | None = None,
        temporal_relation: Literal["before", "after", "during", "overlaps"] | None = None,
        temporal_clock: Literal["created_at", "valid_time"] = "created_at",
    ) -> list[EvidenceItem]:
        """Queries memory store for semantic/episodic facts with provenance."""
        _Sub, _Tier, _EvItem = _cascade_types()
        items: list[EvidenceItem] = []
        if not self.memory_store or not query_text.strip():
            return items

        self._last_recollections: list[str] = []
        try:
            q = RetrievalQuery(
                query_text=query_text.strip(),
                k=8,
                include_superseded=True,
                temporal_anchor=temporal_anchor,
                temporal_relation=temporal_relation,
                temporal_clock=temporal_clock,
            )
            res = self.memory_store.search(q)
            raw_hits: list[MemoryHit] = res if isinstance(res, list) else []

            for hit in raw_hits:
                # Invariant D-MEM-04: Non-grounding rows MUST NOT enter Belnap evidence fusion!
                if not getattr(hit, "grounding_eligible", True):
                    self._last_recollections.append(f'[{hit.provenance.value}] "{hit.content}"')
                    continue

                prov_val = (
                    hit.provenance.value
                    if hasattr(hit.provenance, "value")
                    else str(hit.provenance)
                )
                is_sup = hit.valid_to is not None or bool(getattr(hit, "superseded_by", None))
                told_true, told_false = self._evaluate_polarity(hit.content, query_text)
                w_pos = 1 if told_true else 0
                w_neg = 1 if told_false else 0
                items.append(
                    _EvItem(
                        substrate=_Sub.MEMORY,
                        trust_tier=_Tier.TIER_3_MEMORY,
                        source=f"memory:{hit.memory_id or hit.source_turn_id}",
                        content=hit.content,
                        told_true=told_true,
                        told_false=told_false,
                        positive_evidence=w_pos,
                        negative_evidence=w_neg,
                        confidence=hit.score,
                        metadata={
                            "kind": hit.kind,
                            "provenance": prov_val,
                            "created_at": hit.created_at,
                            "valid_from": getattr(hit, "valid_from", hit.created_at),
                            "valid_to": getattr(hit, "valid_to", None),
                            "superseded_by": getattr(hit, "superseded_by", None),
                            "is_superseded": is_sup,
                            "confidence": getattr(hit, "confidence", None),
                        },
                    )
                )

            # Evaluate pairwise consistency across active (non-superseded) memory items
            self._annotate_active_memory_conflicts(items)
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_2_memory_query_error", error=str(exc))

        return items

    def query_substrate_self_history(self, query_text: str) -> list[EvidenceItem]:
        """
        Queries self-history (Substrate 7: SELF_HISTORY, Tier 1).
        Entailed by execution_triples ∪ ASSISTANT_ACTION ∪ ASSISTANT_UTTERANCE ∪ COHERENCE_BREACH.
        Abstains (returns empty list) if the record is empty.
        """
        _Sub, _Tier, _EvItem = _cascade_types()
        items: list[EvidenceItem] = []
        db = getattr(self.memory_store, "db", None)
        if not db or not query_text.strip():
            return items

        try:
            tokens = tokenize_query(query_text)
            candidates: list[tuple[float, float, EvidenceItem]] = []

            import lucca.core.cascade as _casc  # noqa: PLC0415

            episodes = _casc.recall_past_episodes(db, query_text, limit=10)
            for ep in episodes:
                ev = _EvItem(
                    substrate=_Sub.SELF_HISTORY,
                    trust_tier=_Tier.TIER_1_HARDWARE,
                    source=f"history:{ep.source}:{ep.record_id}",
                    content=ep.summary,
                    told_true=True,
                    told_false=False,
                    confidence=min(1.0, ep.match_score / max(1, ep.tokens_total)),
                    metadata={
                        "match_score": ep.match_score,
                        "tokens_total": ep.tokens_total,
                        **ep.payload,
                    },
                )
                items.append(ev)
                candidates.append((float(ep.match_score), ep.ts, ev))

            with db.read_cursor() as cur:
                # 2. Query memories for autobiographical classes
                cur.execute(
                    """
                    SELECT m.memory_id, m.content, p.provenance, p.trace_id,
                           m.created_at, m.superseded_by, p.grounding_eligible
                    FROM memories m
                    JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                    WHERE p.provenance IN (
                        'ASSISTANT_ACTION', 'ASSISTANT_UTTERANCE',
                        'COHERENCE_BREACH', 'ASSISTANT_BELIEF'
                    )
                    ORDER BY m.created_at DESC LIMIT 100
                    """
                )
                mem_rows = cur.fetchall()
                for mid, content, prov, tr_id, cat_ts, sup_by, gr_elig in mem_rows:
                    content_str = str(content)
                    is_wrong_query = "wrong" in query_text.lower() or "error" in query_text.lower()
                    if is_wrong_query and (prov == "COHERENCE_BREACH" or sup_by is not None):
                        told_true, told_false = self._evaluate_polarity(content_str, query_text)
                        candidates.append(
                            (
                                10.0,  # Highest priority for explicit error/breach retrospection
                                float(cat_ts),
                                _EvItem(
                                    substrate=_Sub.SELF_HISTORY,
                                    trust_tier=_Tier.TIER_1_HARDWARE,
                                    source=f"history:breach:{mid}",
                                    content=(
                                        f"Historical revision / breach: {content_str} "
                                        f"(superseded_by={sup_by})"
                                    ),
                                    told_true=told_true,
                                    told_false=told_false,
                                    confidence=1.0,
                                    metadata={"provenance": str(prov), "superseded_by": sup_by},
                                ),
                            )
                        )
                    elif not is_wrong_query and tokens:
                        score = sum(1 for t in tokens if t in content_str.lower())
                        if score > 0:
                            told_true, told_false = self._evaluate_polarity(content_str, query_text)
                            candidates.append(
                                (
                                    float(score),
                                    float(cat_ts),
                                    _EvItem(
                                        substrate=_Sub.SELF_HISTORY,
                                        trust_tier=_Tier.TIER_1_HARDWARE,
                                        source=f"history:{str(prov).lower()}:{mid}",
                                        content=content_str,
                                        told_true=told_true,
                                        told_false=told_false,
                                        confidence=1.0,
                                        metadata={
                                            "provenance": str(prov),
                                            "trace_id": str(tr_id),
                                            "grounding_eligible": int(gr_elig),
                                        },
                                    ),
                                )
                            )

                # Sort by (match_score DESC, created_at DESC) and cap at 5 items
                candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
                seen_sources: set[str] = set()
                deduped: list[EvidenceItem] = []
                for _, _, item in candidates:
                    if item.source not in seen_sources:
                        seen_sources.add(item.source)
                        deduped.append(item)
                    if len(deduped) >= 5:
                        break
                return deduped
        except Exception as exc:  # noqa: BLE001
            logger.debug("self_history_recall_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Substrate 3: SSRF-Hardened Sandboxed Web (300–1500ms target)
    # ------------------------------------------------------------------------
    def query_substrate_3_web(self, query_text: str) -> list[EvidenceItem]:
        """Queries external web when explicit URL is supplied or via web search fallback."""
        _Sub, _Tier, _EvItem = _cascade_types()
        items: list[EvidenceItem] = []
        if not self.sandbox:
            return items

        url_match = re.search(r"(https?://[^\s\"'>]+)", query_text)
        if url_match:
            target_url = url_match.group(1)
            try:
                # Propagate untrusted web taint to active session guard (Spec 09 / D-SEC-04)
                if (
                    self.sandbox
                    and hasattr(self.sandbox, "guard")
                    and hasattr(self.sandbox.guard, "mark_taint")
                ):
                    # Lazy import: avoids a sandbox <-> core import cycle.
                    from lucca.sandbox.policy import TaintFlags  # noqa: PLC0415

                    self.sandbox.guard.mark_taint(TaintFlags.UNTRUSTED_WEB)

                res = self._execute_sandbox(
                    tool_name="fetch_url",
                    args={"url": target_url},
                    confirmed=True,
                )
                if res and res.ok and res.content:
                    told_true, told_false = self._evaluate_polarity(res.content[:600], query_text)
                    items.append(
                        _EvItem(
                            substrate=_Sub.WEB,
                            trust_tier=_Tier.TIER_4_WEB,
                            source=f"web:{target_url}",
                            content=res.content[:600],
                            proposition=f"web_content({target_url})",
                            told_true=told_true,
                            told_false=told_false,
                            confidence=0.85,
                            metadata={"url": target_url},
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("substrate_3_web_query_error", error=str(exc))
            return items

        # Fallback to search_web when no explicit URL is supplied
        try:
            if (
                self.sandbox
                and hasattr(self.sandbox, "guard")
                and hasattr(self.sandbox.guard, "mark_taint")
            ):
                from lucca.sandbox.policy import TaintFlags  # noqa: PLC0415

                self.sandbox.guard.mark_taint(TaintFlags.UNTRUSTED_WEB)

            topic = extract_clean_topic(query_text)
            search_query = topic if topic and topic != "that" else query_text
            target_entity = _extract_target_entity(query_text)

            search_args: dict[str, JsonValue] = {"query": search_query}
            if target_entity:
                search_args["target_entity"] = target_entity

            res = self._execute_sandbox(
                tool_name="search_web",
                args=search_args,
                confirmed=True,
            )
            if res and res.ok and res.content:
                told_true, told_false = self._evaluate_polarity(res.content[:1500], query_text)
                items.append(
                    _EvItem(
                        substrate=_Sub.WEB,
                        trust_tier=_Tier.TIER_4_WEB,
                        source=f"web_search:{search_query}",
                        content=res.content[:1500],
                        proposition=f"web_search_results({search_query})",
                        told_true=told_true,
                        told_false=told_false,
                        confidence=0.85,
                        metadata=(
                            res.structured
                            if isinstance(res.structured, dict)
                            else {"query": search_query}
                        ),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_3_web_search_error", error=str(exc))

        return items
