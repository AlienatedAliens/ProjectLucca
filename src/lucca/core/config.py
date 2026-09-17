"""
Project Lucca — Central System Configuration
"""

import os
from pathlib import Path
from pydantic import BaseModel, Field

class LuccaConfig(BaseModel):
    # Base Directories
    project_root: Path = Field(default=Path("C:/projects/ProjectLucca"))
    var_dir: Path = Field(default=Path("C:/projects/ProjectLucca/var"))
    cache_dir: Path = Field(default=Path("C:/projects/ProjectLucca/var/cache"))
    
    # Subsystem Endpoints
    vllm_base_url: str = Field(default=os.getenv("LUCCA_VLLM_URL", "http://localhost:8000/v1"))
    vllm_model_name: str = Field(default=os.getenv("LUCCA_VLLM_MODEL", "fixie-ai/ultravox-v0_5-llama-3_1-8b"))
    
    # Hardware Targets
    openvino_device: str = Field(default=os.getenv("LUCCA_OPENVINO_DEVICE", "NPU"))
    wsl_memory_clamp_mb: int = Field(default=4608)
    max_gpu_memory_utilization: float = Field(default=0.62)
    
    # Audio Specs
    audio_sample_rate: int = Field(default=24000)
    audio_channels: int = Field(default=1)
    
    # Security Keys
    hmac_secret_key: str = Field(default=os.getenv("LUCCA_HMAC_SECRET_KEY", "insecure_dev_key_change_in_prod"))

def get_config() -> LuccaConfig:
    return LuccaConfig()
