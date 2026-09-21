"""
Project Lucca — Central Configuration (pydantic-settings)
Spec 11 §1 (`lucca.core.config`)
"""

import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class LLMSettings(BaseModel):
    """
    Single source of truth for the neural brain. Nothing else in the runtime may
    hard-code a model name, server binary, or chat template — derive from here.
    Env override: LUCCA_LLM__<FIELD> (e.g. LUCCA_LLM__MODEL, LUCCA_LLM__CHAT_TEMPLATE_FILE=).
    """

    mode: Literal["audio", "transcript"] = "transcript"
    host: str = "127.0.0.1"
    port: int = 8080
    ctx: int = 16384
    kv_type: str = "q8_0"
    max_tokens: int = 512
    temperature: float = 0.6
    # Reasoning-model control (reasoning-model templates honour
    # chat_template_kwargs.enable_thinking). None = omit the kwarg (template default).
    # Companion tiers (ACT_THEN_NARRATE / FULL_LOOP) must run with False to keep
    # TTFT inside the 650-850 ms budget; see docs/audit/evidence/BRAIN_BAKEOFF_2026-09-21.md.
    # Templates without a thinking channel ignore the kwarg harmlessly.
    enable_thinking: bool | None = False
    model: str = "llm/Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf"
    mmproj: str = "llm/mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf"
    text_model: str = "llm/Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf"
    # llama-server binary, relative to LUCCA_HOME or absolute. Forked builds
    # (e.g. PrismML ternary kernels) are selected here, never by code.
    server_bin: str = "app/llama-server/llama-server.exe"
    # Chat template selection. Precedence: chat_template_file > chat_template > GGUF-embedded.
    # Relative paths resolve against LUCCA_HOME then the repo root. Blank/None = embedded.
    chat_template_file: str | None = "templates/mistral_nemo.jinja"
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
    key: str = "alt-gr"
    mode: Literal["hold", "toggle"] = "hold"
    max_seconds: float = 29.5
    swallow: bool = False


class MemorySettings(BaseModel):
    k: int = 8
    memory_tokens: int = 600
    audio_retention_days: int = 7
    backup_daily: bool = True


class RouterSettings(BaseModel):
    version: Literal["heuristic", "classifier"] = "heuristic"


class RulesSettings(BaseModel):
    gas_limit: int = 1000
    timeout_ms: int = 20
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


@lru_cache
def get_config() -> LuccaConfig:
    return LuccaConfig()


def get_resource_path(relative_path: str | Path) -> Path:
    """
    Resolves bundled resource path with support for PyInstaller frozen mode,
    workstation installation (C:/ProjectLucca), repo root, and local working directory.
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

    # 2. Workstation installation directory
    cfg: LuccaConfig = get_config()
    home_p: Path = cfg.home_dir / rel
    if home_p.exists():
        return home_p

    # 3. Source repository root
    repo_root: Path = Path(__file__).resolve().parents[3]
    repo_p: Path = repo_root / rel
    if repo_p.exists():
        return repo_p

    # 4. Current working directory fallback
    cwd_p: Path = Path.cwd() / rel
    if cwd_p.exists():
        return cwd_p

    # Fallback to repo or home
    return home_p if home_p.parent.exists() else repo_p
