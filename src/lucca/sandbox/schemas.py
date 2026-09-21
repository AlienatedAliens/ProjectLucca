"""
Project Lucca — Sandbox Tool Request Validation Schemas
Proposal F / D-SEC-04 (Zero-Any Compliant)
"""

from typing import Literal

from pydantic import BaseModel, Field


class LaunchAppArgs(BaseModel):
    app_name: str = Field(min_length=1)
    file: str | None = None
    url: str | None = None


class ReadFileArgs(BaseModel):
    path: str = Field(min_length=1)
    max_bytes: int = Field(default=262144, ge=1, le=10485760)


class WriteFileArgs(BaseModel):
    path: str = Field(min_length=1)
    content: str
    mode: Literal["create", "overwrite", "append"] = "create"


class DeleteFileArgs(BaseModel):
    path: str = Field(min_length=1)


class ListDirArgs(BaseModel):
    path: str = Field(default="")
    recursive: bool = False


class SearchTextArgs(BaseModel):
    pattern: str = Field(min_length=1)
    path: str = Field(default="")
    max_hits: int = Field(default=200, ge=1, le=2000)


class RunPythonArgs(BaseModel):
    code: str = Field(min_length=1)
    timeout: int = Field(default=10, ge=1, le=60)


class FetchUrlArgs(BaseModel):
    url: str = Field(min_length=1)
    render: bool = False
    max_chars: int = Field(default=20000, ge=100, le=100000)


class SearchWebArgs(BaseModel):
    query: str = Field(min_length=1)
    max_results: int = Field(default=5, ge=1, le=20)


class MemorySearchArgs(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class MemoryCommitArgs(BaseModel):
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class NoteWriteArgs(BaseModel):
    name: str = Field(min_length=1)
    content: str
    append: bool = False


class NoteReadArgs(BaseModel):
    name: str = Field(min_length=1)


class SysInfoArgs(BaseModel):
    filter_name: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
