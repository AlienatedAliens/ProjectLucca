"""
Project Lucca — Central Configuration (pydantic-settings)
Spec 11 §1 (`lucca.core.config`)
"""

import logging
import os
import re
import sys
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_QUANT_TOKEN = re.compile(r"^(?:IQ|PQ|TQ|Q)\d[\w]*$", re.IGNORECASE)


class EnvSettings(BaseModel):
    mode: Literal["prod", "dev"] = "prod"


class PathsSettings(BaseModel):
    models: str = "models"
    data: str = "data"
    workspace: str = "workspace"
    inbox: str = "inbox"
    logs: str = "logs"
    cache: str = "cache"
    tmp: str = "tmp"
    notes: str = "notes"


class LLMSettings(BaseModel):
    """
    Single source of truth for the neural brain. Nothing else in the runtime may
    hard-code a model name, server binary, or chat template — derive from here.
    Env override: LUCCA_LLM__<FIELD> (e.g. LUCCA_LLM__MODEL, LUCCA_LLM__CHAT_TEMPLATE_FILE=).
    """

    mode: Literal["audio", "transcript"] = "transcript"
    host: str = "127.0.0.1"
    port: int = 8080
    ctx: int = 32768
    kv_type: str = "q8_0"
    # RAM budget for the llama-server prompt prefix cache (--cache-ram, MiB).
    # Bounded to 4 GiB: the 8 GiB default thrashed and crashed under the WO-8
    # battery workload (60 distinct low-similarity prompts). Production turns
    # share one ~3.8K-token prefix, so 4 GiB is ample headroom.
    cache_ram_mib: int = 4096
    max_tokens: int = 2048
    temperature: float = 0.6
    # Reasoning-model control (reasoning-model templates honour
    # chat_template_kwargs.enable_thinking). None = omit the kwarg (template default).
    # Companion tiers (ACT_THEN_NARRATE / FULL_LOOP) must run with False to keep
    # TTFT inside the 650-850 ms budget; see docs/audit/evidence/BRAIN_BAKEOFF_2026-09-21.md.
    # Templates without a thinking channel ignore the kwarg harmlessly.
    enable_thinking: bool | None = False
    narration_prefer_digits: bool = True
    # Canonical brain per D-BRAIN-05 v2 (GGUF-embedded chat template via
    # --jinja). The previous brain is deprecated and retained for rollback only.
    model: str = "llm/gemma-4-12b-heretic-Q6_K.gguf"
    mmproj: str = "llm/mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf"
    text_model: str = "llm/gemma-4-12b-heretic-Q6_K.gguf"
    # llama-server binary, relative to LUCCA_HOME or absolute. Forked builds
    # (e.g. PrismML ternary kernels) are selected here, never by code.
    server_bin: str = "app/llama-server/llama-server.exe"
    # Chat template selection. Precedence: chat_template_file > chat_template > GGUF-embedded.
    # Relative paths resolve against LUCCA_HOME then the repo root. Blank/None = embedded.
    # Default None: the canonical brain uses its GGUF-embedded template (D-BRAIN-05 v2).
    chat_template_file: str | None = None
    chat_template: str | None = None
    # Human-readable brain name for self-awareness prompts. None = derived from filename.
    display_name: str | None = None

    @field_validator("chat_template_file", "chat_template", "display_name", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and (not v.strip() or v.strip().lower() in ("none", "null")):
            return None
        return v

    def model_display_name(self) -> str:
        """
        Friendly brain name derived from the GGUF filename unless display_name is set.
        Used by persona/self-awareness prompts so the brain never has to be named in code.
        """
        if self.display_name:
            return self.display_name
        stem = Path(self.model).name
        if stem.lower().endswith(".gguf"):
            stem = stem[:-5]
        tokens = [t for t in re.split(r"[-.]", stem) if t]
        quant = tokens.pop() if tokens and _QUANT_TOKEN.match(tokens[-1]) else None
        name = " ".join(tokens).replace("_", " ").strip() or stem
        return f"{name} ({quant})" if quant else name


DeviceType = Literal["NPU", "GPU", "CPU"]


def _default_device_ladder() -> list[DeviceType]:
    return ["NPU", "GPU", "CPU"]


class ASRSettings(BaseModel):
    model: str = "asr/whisper-large-v3-turbo-ov"
    device_ladder: list[DeviceType] = Field(default_factory=_default_device_ladder)
    lowconf_logprob: float = -0.5


class TTSSettings(BaseModel):
    model: str = "tts/kokoro-v1"
    voice: str = "genki_heroine"
    speed: float = 1.10
    device_ladder: list[DeviceType] = Field(default_factory=_default_device_ladder)
    speak_code: bool = False
    speak_urls: bool = False


class AudioSettings(BaseModel):
    capture_device: str = ""
    playback_device: str = ""
    capture_rate: int = 16000
    playback_rate: int = 24000
    exclusive: bool = False
    jitter_ms: int = 60


class PTTSettings(BaseModel):
    key: str = "alt_gr"
    mode: Literal["hold", "toggle"] = "hold"
    max_seconds: float = 29.5
    swallow: bool = False


class MemorySettings(BaseModel):
    k: int = 8
    memory_tokens: int = 600
    audio_retention_days: int = 7
    backup_daily: bool = True
    form_beliefs: bool = True
    rollup_hour_local: int = 3


class RouterSettings(BaseModel):
    version: Literal["heuristic", "classifier"] = "heuristic"


class RulesSettings(BaseModel):
    gas_limit: int = 1000
    timeout_ms: int = 25
    promote_min_clusters: int = 5


class ReflectionSettings(BaseModel):
    enabled: bool = True
    idle_seconds: int = 60
    min_new_decisions: int = 10
    min_interval_minutes: int = 10


class SandboxSettings(BaseModel):
    wsl_distro: str = "Ubuntu"
    file_mem_mb: int = 768
    web_mem_mb: int = 512
    allow_render: bool = False


class IPCSettings(BaseModel):
    ctl_port: int = 47001
    bus_port: int = 47002
    ingest_port: int = 47003


class UISettings(BaseModel):
    enabled: bool = True
    fps_active: int = 30
    fps_idle: int = 5


class LogSettings(BaseModel):
    level: str = "INFO"
    json_format: bool = Field(default=True, alias="json")
    retention_days: int = 30
    decision_retention_files: int = 14


class LuccaConfig(BaseSettings):
    """
    Unified Application Configuration
    Precedence: CLI flags -> Env vars (LUCCA_*) -> lucca.toml -> .env -> defaults
    """

    model_config = SettingsConfigDict(
        env_prefix="LUCCA_",
        env_nested_delimiter="__",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    env: EnvSettings = Field(default_factory=EnvSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    asr: ASRSettings = Field(default_factory=ASRSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    ptt: PTTSettings = Field(default_factory=PTTSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    router: RouterSettings = Field(default_factory=RouterSettings)
    rules: RulesSettings = Field(default_factory=RulesSettings)
    reflection: ReflectionSettings = Field(default_factory=ReflectionSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    ipc: IPCSettings = Field(default_factory=IPCSettings)
    ui: UISettings = Field(default_factory=UISettings)
    log: LogSettings = Field(default_factory=LogSettings)

    master_key: str | None = Field(default=None, alias="LUCCA_MASTER_KEY")

    @property
    def home_dir(self) -> Path:
        """Determines canonical LUCCA_HOME directory."""
        custom_home = os.getenv("LUCCA_HOME")
        if custom_home:
            return Path(custom_home).resolve()
        if Path("C:/ProjectLucca/app/llama-server/llama-server.exe").exists():
            return Path("C:/ProjectLucca").resolve()
        if self.env.mode == "dev":
            # Repo-local directory for testing
            return (Path(__file__).parent.parent.parent.parent / ".lucca_home").resolve()
        return Path("C:/ProjectLucca").resolve()

    def resolve_path(self, subpath_name: str) -> Path:
        """Resolves a directory path relative to LUCCA_HOME."""
        rel = getattr(self.paths, subpath_name, subpath_name)
        p = self.home_dir / rel
        return p


# WO-10.6 (F20): behavioural heuristics live in config/heuristics.toml with
# these code defaults as fallback. Security invariants (closed predicates,
# MEMORY_ELIGIBLE) deliberately stay code-resident — they are the trust
# boundary, not tuning knobs.
DEFAULT_FOLLOW_UP_PATTERNS: Final[tuple[str, ...]] = (
    "tell me more",
    "more about",
    "what else",
    "who is",
    "what about",
    "are you sure",
    "what are your sources",
    "cite your sources",
    "where did you get that",
    "all of this is wrong",
    "elaborate",
    "yes",
    "yeah",
    "yep",
    "sure",
    "okay",
    "ok",
    "do it",
    "please do",
    "go ahead",
    "where is",
    "where was",
    "where are",
    "who was",
    "facts about",
    "how about",
    "spelled",
    "spelling",
    "search",
)

DEFAULT_SEARCH_CATEGORY_KEYWORDS: Final[tuple[str, ...]] = (
    "suburb",
    "judge",
    "court",
    "station",
    "school",
    "hospital",
    "city",
    "province",
    "victoria",
    "australia",
    "philippines",
    "manila",
)

DEFAULT_CELEBRATION_MARKERS: Final[tuple[str, ...]] = (
    "crushed it",
    "we did it",
    "nailed it",
    "nailed",
    "perfect!",
    "boom!",
    "worked like a charm",
    "easy peasy",
    "piece of cake",
)


_HEURISTICS_CACHE: Final[dict[str, tuple[str, ...]]] = {}


def load_heuristics(name: str) -> tuple[str, ...]:
    """Loads a named heuristic list from config/heuristics.toml, falling back
    to the code defaults. Results are cached per name for the process lifetime
    (restart to pick up config edits)."""
    if name in _HEURISTICS_CACHE:
        return _HEURISTICS_CACHE[name]
    defaults = {
        "follow_up_patterns": DEFAULT_FOLLOW_UP_PATTERNS,
        "search_category_keywords": DEFAULT_SEARCH_CATEGORY_KEYWORDS,
        "celebration_markers": DEFAULT_CELEBRATION_MARKERS,
    }.get(name, ())
    loaded: tuple[str, ...] = defaults
    try:
        cfg = get_config()
        path = cfg.resolve_path("config") / "heuristics.toml"
        if path.exists():
            with open(path, "rb") as f:
                data = tomllib.load(f)
            values = data.get(name)
            if isinstance(values, list) and values:
                loaded = tuple(str(v) for v in values)
    except Exception as exc:  # noqa: BLE001
        logger.debug("heuristics_load_failed", extra={"error": str(exc)})
    _HEURISTICS_CACHE[name] = loaded
    return loaded


@lru_cache
def get_config() -> LuccaConfig:
    return LuccaConfig()


def get_resource_path(relative_path: str | Path) -> Path:
    """
    Resolves bundled resource path with support for PyInstaller frozen mode,
    source repository root, workstation installation (C:/ProjectLucca), and local working directory.
    When running from source, the development repository is authoritative to prevent
    stale workstation installation files from shadowing active changes.
    Enforces strict zero-Any typing.
    """
    rel: Path = Path(relative_path)
    # 1. PyInstaller frozen runtime temporary directory
    if hasattr(sys, "_MEIPASS"):
        meipass_base: str = str(getattr(sys, "_MEIPASS", ""))
        if meipass_base:
            meipass_p: Path = Path(meipass_base) / rel
            if meipass_p.exists():
                return meipass_p

    # 2. Source repository root (authoritative when running in development)
    repo_root: Path = Path(__file__).resolve().parents[3]
    repo_p: Path = repo_root / rel
    if repo_p.exists():
        return repo_p

    # 3. Workstation installation directory (C:/ProjectLucca)
    cfg: LuccaConfig = get_config()
    home_p: Path = cfg.home_dir / rel
    if home_p.exists():
        return home_p

    # 4. Current working directory fallback
    cwd_p: Path = Path.cwd() / rel
    if cwd_p.exists():
        return cwd_p

    # Fallback to repo or home
    return repo_p if repo_p.parent.exists() else home_p
