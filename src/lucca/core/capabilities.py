"""
Project Lucca — Unified Dynamic Capability Registry & Tool Manifest
Spec 09 §6, Spec 10 §4, Milestone 4 Architecture
3-Class Tool Taxonomy (Spec 1.1.2 §2, T1.1–T1.2, §0.0 C1–C3)
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Final

import structlog
from pydantic import JsonValue

from lucca.core.config import get_config, get_resource_path
from lucca.core.schemas import (
    FACT_PREDICATES,
    Risk,
    ToolDefinition,
    ToolFunctionSchema,
    ToolParameter,
    ToolSchema,
)

if TYPE_CHECKING:
    from lucca.reasoning.lifecycle import RuleLifecycleManager

logger = structlog.get_logger(__name__)

# Native Tool Registry Cap (Spec 1.1.2 §2.4, T1.6: expect exactly 9 at T1).
# Raised 16 -> 18 by WO-9 A13/A14: launch_app (F14) and self_history_search
# (F18) are now advertised; both are confirmation-free/gated as marked.
MAX_REGISTRY_TOOLS: Final[int] = 18


def _predicate_menu() -> str:
    """Comma-joined closed fact-predicate menu, generated from the canonical
    FACT_PREDICATES set in core.schemas so manifest text can never drift from
    the ProvenanceGate's enforcement list (WO-9 A2)."""
    return ", ".join(sorted(FACT_PREDICATES))


def get_default_native_tools() -> dict[str, ToolSchema]:
    """Returns the normative 9 native tools with 3-class target taxonomy (T1.1, T1.2, §0.0 C1)."""
    return {
        "read_file": ToolSchema(
            name="read_file",
            description="Read a file from the user workspace",
            parameters={
                "rel_path": ToolParameter(
                    type="string", description="Relative path under workspace", required=True
                ),
                "max_bytes": ToolParameter(
                    type="integer", description="Maximum bytes to read", required=False
                ),
            },
            risk=Risk.READ,
            target="self",
        ),
        "write_file": ToolSchema(
            name="write_file",
            description="Write or overwrite a file in the workspace",
            parameters={
                "rel_path": ToolParameter(
                    type="string", description="Relative path under workspace", required=True
                ),
                "content": ToolParameter(
                    type="string", description="File text content", required=True
                ),
                "mode": ToolParameter(
                    type="string", description="Write mode (write or append)", required=False
                ),
            },
            risk=Risk.WRITE,
            target="self",
        ),
        "search_web": ToolSchema(
            name="search_web",
            description="Search the web for real-time information and public records",
            parameters={
                "query": ToolParameter(
                    type="string", description="Search query terms", required=True
                ),
                "max_results": ToolParameter(
                    type="integer", description="Maximum search results", required=False
                ),
            },
            risk=Risk.NETWORK,
            target="self",
        ),
        "fetch_url": ToolSchema(
            name="fetch_url",
            description="Retrieve and read text content from a specific web URL",
            parameters={
                "url": ToolParameter(type="string", description="Web URL to fetch", required=True),
                "render": ToolParameter(
                    type="boolean", description="Whether to render JavaScript", required=False
                ),
            },
            risk=Risk.NETWORK,
            target="self",
        ),
        "query_capabilities": ToolSchema(
            name="query_capabilities",
            description=("Retrieve live system metrics or query installed workspace tools"),
            parameters={
                "category": ToolParameter(
                    type="string",
                    description="Capability category to query (all, tools, hardware, etc.)",
                    required=False,
                )
            },
            risk=Risk.READ,
            target="host_readonly",
        ),
        "list_dir": ToolSchema(
            name="list_dir",
            description="List files and directories in the workspace",
            parameters={
                "rel_path": ToolParameter(
                    type="string",
                    description="Relative directory path under workspace",
                    required=False,
                ),
                "recursive": ToolParameter(
                    type="boolean", description="Whether to list recursively", required=False
                ),
            },
            risk=Risk.READ,
            target="self",
        ),
        "search_text": ToolSchema(
            name="search_text",
            description="Search for text or regex pattern within workspace files",
            parameters={
                "pattern": ToolParameter(
                    type="string", description="Text or regex pattern to search", required=True
                ),
                "rel_path": ToolParameter(
                    type="string",
                    description="Directory path under workspace to search",
                    required=False,
                ),
                "max_hits": ToolParameter(
                    type="integer", description="Maximum matching hits to return", required=False
                ),
            },
            risk=Risk.READ,
            target="self",
        ),
        "run_python": ToolSchema(
            name="run_python",
            description="Execute deterministic Python code in an isolated sandbox",
            parameters={
                "code": ToolParameter(
                    type="string", description="Python code to execute", required=True
                ),
                "timeout": ToolParameter(
                    type="integer", description="Execution timeout in seconds", required=False
                ),
            },
            risk=Risk.WRITE,
            target="self",
        ),
        "invoke_skill": ToolSchema(
            name="invoke_skill",
            description="Invoke an active MicroScheme skill by ID with arguments",
            parameters={
                "skill_id": ToolParameter(
                    type="string", description="Unique skill identifier", required=True
                ),
                "args": ToolParameter(
                    type="object", description="Skill argument dictionary", required=False
                ),
            },
            risk=Risk.READ,
            target="self",
        ),
        "memory_search": ToolSchema(
            name="memory_search",
            description="Search episodic and semantic memory for relevant facts",
            parameters={
                "query": ToolParameter(
                    type="string", description="Query string to search in memory", required=True
                ),
                "top_k": ToolParameter(
                    type="integer",
                    description="Maximum number of memory items to return (default 5)",
                    required=False,
                ),
            },
            risk=Risk.READ,
            target="self",
        ),
        "memory_commit": ToolSchema(
            name="memory_commit",
            description=(
                "Commit a fact the USER stated in this turn into long-term memory. "
                "Provide s (subject, e.g. 'user'), p (one of: "
                f"{_predicate_menu()}), o (the value), and quote: a VERBATIM excerpt "
                "of the user's own words containing the fact. The fact is only saved "
                "if the quote matches the user's actual words this turn; model-invented "
                "facts are refused."
            ),
            parameters={
                "s": ToolParameter(
                    type="string", description="Fact subject (usually 'user')", required=True
                ),
                "p": ToolParameter(
                    type="string",
                    description=(
                        f"Predicate from the closed list (one of: {_predicate_menu()})"
                    ),
                    required=True,
                ),
                "o": ToolParameter(
                    type="string", description="Fact value (e.g. 'Sean')", required=True
                ),
                "quote": ToolParameter(
                    type="string",
                    description="Verbatim quote from the user's words this turn",
                    required=True,
                ),
                "tags": ToolParameter(
                    type="array",
                    description="Optional tags or categories for the memory item",
                    required=False,
                ),
            },
            risk=Risk.WRITE,
            target="self",
        ),
        "note_write": ToolSchema(
            name="note_write",
            description="Write or append to a scratchpad note outside the user workspace",
            parameters={
                "name": ToolParameter(
                    type="string", description="Note identifier or filename", required=True
                ),
                "content": ToolParameter(
                    type="string", description="Text content to write to the note", required=True
                ),
                "append": ToolParameter(
                    type="boolean",
                    description="Whether to append to an existing note instead of overwriting",
                    required=False,
                ),
            },
            risk=Risk.WRITE,
            target="self",
        ),
        "note_read": ToolSchema(
            name="note_read",
            description="Read the contents of a scratchpad note outside the user workspace",
            parameters={
                "name": ToolParameter(
                    type="string", description="Note identifier or filename to read", required=True
                ),
            },
            risk=Risk.READ,
            target="self",
        ),
        "self_metrics": ToolSchema(
            name="self_metrics",
            description="Retrieve hardware telemetry across CPU, RAM, GPU, and NPU substrates",
            parameters={},
            risk=Risk.READ,
            target="self",
        ),
        "self_history_search": ToolSchema(
            name="self_history_search",
            description=(
                "Search your own action history: what you actually did, what "
                "failed, what was cancelled, beliefs you formed, and coherence "
                "breaches. Use this to answer 'did you actually do X?' from "
                "records instead of guessing."
            ),
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Keywords to match against your action history",
                    required=True,
                ),
            },
            risk=Risk.READ,
            target="self",
        ),
        "launch_app": ToolSchema(
            name="launch_app",
            description=(
                "Launch a whitelisted desktop application on the host. Requires "
                "explicit user confirmation before execution."
            ),
            parameters={
                "app_name": ToolParameter(
                    type="string",
                    description="Application name from the whitelist (e.g. calculator, notepad)",
                    required=True,
                ),
                "file": ToolParameter(
                    type="string",
                    description="Optional file to open with the application",
                    required=False,
                ),
                "url": ToolParameter(
                    type="string", description="Optional URL to open", required=False
                ),
            },
            risk=Risk.LAUNCH,
            target="shared",
        ),
        "sys_info": ToolSchema(
            name="sys_info",
            description="Inspect host OS version, hostname, uptime, and running processes",
            parameters={
                "filter_name": ToolParameter(
                    type="string", description="Optional process name filter", required=False
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Maximum number of processes to list (default 25)",
                    required=False,
                ),
            },
            risk=Risk.READ,
            target="host_readonly",
        ),
    }


def tool_schema_to_definition(schema: ToolSchema) -> ToolDefinition:
    """Converts internal ToolSchema to OpenAI-compatible ToolDefinition."""
    props: dict[str, JsonValue] = {}
    required_fields: list[str] = []
    for param_name, param in schema.parameters.items():
        props[param_name] = {
            "type": param.type,
            "description": param.description,
        }
        if param.required:
            required_fields.append(param_name)

    params: dict[str, JsonValue] = {
        "type": "object",
        "properties": props,
    }
    if required_fields:
        params["required"] = required_fields

    return ToolDefinition(
        type="function",
        function=ToolFunctionSchema(
            name=schema.name,
            description=schema.description,
            parameters=params,
        ),
    )


class CapabilityRegistry:
    """
    Authoritative Dynamic Capability Registry.
    Aggregates Tool Taxonomy, LISP Studio skills, and Sandbox execution.
    """

    def __init__(
        self,
        rule_engine: RuleLifecycleManager | None = None,
        config_path: Path | str | None = None,
        tools: dict[str, ToolSchema] | None = None,
    ) -> None:
        self.rule_engine = rule_engine
        self.config_path = Path(config_path) if config_path else None
        self._cached_apps: list[dict[str, str]] | None = None
        self._tools: dict[str, ToolSchema] = (
            dict(tools) if tools is not None else get_default_native_tools()
        )
        if len(self._tools) > MAX_REGISTRY_TOOLS:
            raise ValueError(f"Registry cap exceeded: {len(self._tools)} > {MAX_REGISTRY_TOOLS}")

    @property
    def tools(self) -> dict[str, ToolSchema]:
        return self._tools

    def get_tool(self, name: str) -> ToolSchema | None:
        return self._tools.get(name)

    def get_tools(self) -> list[ToolSchema]:
        """Returns registered native tools sorted alphabetically by name."""
        return [self._tools[k] for k in sorted(self._tools.keys())]

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Returns OpenAI ToolDefinitions sorted alphabetically by name."""
        return [tool_schema_to_definition(self._tools[k]) for k in sorted(self._tools.keys())]

    def get_whitelisted_apps(self, force_reload: bool = False) -> list[dict[str, str]]:
        """Loads approved applications from tool_whitelist.toml (vestigial, rollback only)."""
        if self._cached_apps is not None and not force_reload:
            return self._cached_apps

        if self.config_path:
            cfg_file = self.config_path
        else:
            try:
                cfg_file = get_resource_path("config/tool_whitelist.toml")
            except Exception:  # noqa: BLE001
                cfg = get_config()
                cfg_file = cfg.resolve_path("config") / "tool_whitelist.toml"

        apps: list[dict[str, str]] = []
        if cfg_file.exists():
            try:
                with open(cfg_file, "rb") as f:
                    data = tomllib.load(f)
                apps_table = data.get("apps", {})
                for key, entry in apps_table.items():
                    name = str(entry.get("name", key.replace("_", " ").title()))
                    path_str = str(entry.get("exe", ""))
                    tier = (
                        "Read-Only"
                        if "task" in key
                        else ("Network" if "browser" in key else "Trusted")
                    )
                    status = "Disabled" if entry.get("disabled", False) else "Active"
                    apps.append(
                        {
                            "key": key,
                            "name": name,
                            "path": path_str,
                            "tier": tier,
                            "status": status,
                        }
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("failed_loading_tool_whitelist", error=str(e))

        self._cached_apps = apps
        return apps

    def get_reasoning_pathways(self) -> dict[str, dict[str, JsonValue]]:
        """Retrieves active MicroScheme reasoning pathways (LISP Studio, Tab 4)."""
        pathways: dict[str, dict[str, JsonValue]] = {}
        if self.rule_engine and hasattr(self.rule_engine, "rules") and self.rule_engine.rules:
            for rule_id, rule in self.rule_engine.rules.items():
                status = str(getattr(rule, "status", "ACTIVE"))
                defn = getattr(rule, "definition", None)
                raw_priority = getattr(defn, "priority", 10) if defn else 10
                try:
                    priority = int(raw_priority)
                except (ValueError, TypeError):
                    priority = 10
                category = "Tools" if "calc" in rule_id else "Cognitive"
                pathways[rule_id] = {
                    "status": status,
                    "priority": priority,
                    "category": category,
                    "purpose": f"Compiled MicroScheme procedural skill: {rule_id}",
                }
        return pathways

    def get_capabilities_manifest(
        self,
        category: str = "all",
        workspace_root: str | Path = ".",
        whitelisted_apps: list[str] | None = None,
    ) -> dict[str, JsonValue]:
        """
        Builds the unified capabilities manifest for query_capabilities,
        dynamically reflecting live tools from get_tool_definitions() and pathways.
        """
        if whitelisted_apps is not None:
            active_app_keys = whitelisted_apps
        else:
            apps = self.get_whitelisted_apps()
            active_app_keys = [a["key"] for a in apps if a.get("status") != "Disabled"]

        pathways = self.get_reasoning_pathways()
        core_tools = [t.function.name for t in self.get_tool_definitions()]

        manifest: dict[str, JsonValue] = {
            "tools": core_tools,
            "whitelisted_apps": active_app_keys,
            "reasoning_pathways": pathways,
            "workspace": str(workspace_root),
            "memory_subsystem": "SQLite-vec episodic & semantic memory (data/memory.sqlite)",
            "hardware_substrates": {
                "dGPU": "NVIDIA GeForce RTX 5080 Laptop GPU (16 GB) - LLM llama-server",
                "NPU": "Intel AI Boost NPU (OpenVINO) - Whisper ASR & 384-D vector embeddings",
                "CPU": "Core Ultra 9 275HX - Orchestrator, ZeroMQ IPC, Kokoro TTS",
                "RAM": "16 GB Physical Host Memory",
            },
        }

        if category != "all" and category in manifest:
            return {category: manifest[category]}
        return manifest


def dispatch_invoke_skill(
    skill_id: str,
    args: dict[str, JsonValue] | None = None,
    rule_engine: RuleLifecycleManager | None = None,
    manifest_skill_ids: set[str] | list[str] | None = None,
) -> tuple[bool, str, dict[str, JsonValue] | None]:
    """
    Executes invoke_skill dispatch contract (T1.2):
    1. Resolve skill_id in rule registry. Not found -> error 'unknown_skill'.
    2. Rule must be ACTIVE and have expose_as_tool: true. Otherwise -> 'skill_not_exposed'.
    3. skill_id must appear in current turn's category manifest.
       Otherwise -> 'skill_not_in_manifest'.
    4. Returns (ok, message/reason, structured_payload).
    """
    if args is None:
        args = {}

    if rule_engine is None or skill_id not in getattr(rule_engine, "rules", {}):
        return False, "unknown_skill", {"error": "unknown_skill", "skill_id": skill_id}

    rule_entry = rule_engine.rules[skill_id]
    status = getattr(rule_entry, "status", None)
    expose_as_tool = getattr(rule_entry, "expose_as_tool", False)
    if not expose_as_tool and hasattr(rule_entry, "definition"):
        meta = getattr(rule_entry.definition, "metadata", {})
        if isinstance(meta, dict):
            expose_as_tool = bool(meta.get("expose_as_tool", False))

    if status != "ACTIVE" or not expose_as_tool:
        return False, "skill_not_exposed", {"error": "skill_not_exposed", "skill_id": skill_id}

    if manifest_skill_ids is not None:
        manifest_set = set(manifest_skill_ids)
        if skill_id not in manifest_set:
            return (
                False,
                "skill_not_in_manifest",
                {"error": "skill_not_in_manifest", "skill_id": skill_id},
            )

    return True, f"Skill '{skill_id}' dispatched", {"skill_id": skill_id, "args": args}


# Singleton instance
_GLOBAL_REGISTRY: CapabilityRegistry | None = None


def get_capability_registry(rule_engine: RuleLifecycleManager | None = None) -> CapabilityRegistry:
    global _GLOBAL_REGISTRY  # noqa: PLW0603
    if _GLOBAL_REGISTRY is None or rule_engine is not None:
        _GLOBAL_REGISTRY = CapabilityRegistry(rule_engine=rule_engine)
    return _GLOBAL_REGISTRY
