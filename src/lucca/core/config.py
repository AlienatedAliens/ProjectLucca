"""
Project Lucca — Central Configuration (pydantic-settings)
Spec 11 §1 (`lucca.core.config`)
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    mode: Literal["audio", "transcript"] = "audio"
    host: str = "127.0.0.1"
    port: int = 8080
    ctx: int = 8192
    kv_type: str = "q8_0"
    max_tokens: int = 512
    temperature: float = 0.6
    model: str = "llm/ultravox-v0_5-llama-3_1-8b-Q6_K.gguf"
    mmproj: str = "llm/mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf"
    text_model: str = ""


DeviceType = Literal["NPU", "GPU", "CPU"]


def _default_device_ladder() -> list[DeviceType]:
    return ["NPU", "GPU", "CPU"]


class ASRSettings(BaseModel):
    model: str = "asr/whisper-large-v3-turbo-ov"
    device_ladder: list[DeviceType] = Field(default_factory=_default_device_ladder)
    lowconf_logprob: float = -0.5


class TTSSettings(BaseModel):
    model: str = "tts/kokoro-v1"
    voice: str = "af_bella"
    speed: float = 1.05
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
    key: str = "right ctrl"
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
        env_prefix="LUCCA_", env_nested_delimiter="__", extra="ignore"
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
