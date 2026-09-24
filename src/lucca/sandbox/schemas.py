"""
Project Lucca — Sandbox Tool Request Validation Schemas
Proposal F / D-SEC-04 (Zero-Any Compliant)
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LaunchAppArgs(BaseModel):
    app_name: str = Field(min_length=1)
    file: str | None = None
    url: str | None = None


class ReadFileArgs(BaseModel):
    path: str = Field(min_length=1)
    max_bytes: int = Field(default=262144, ge=1, le=10485760)

    @model_validator(mode="before")
    @classmethod
    def _coerce_path(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("path"):
            for alt in ("rel_path", "filename", "file_path", "filepath", "target"):
                if data.get(alt):
                    data["path"] = str(data[alt])
                    break
        return data


class WriteFileArgs(BaseModel):
    path: str = Field(min_length=1)
    content: str
    mode: Literal["create", "overwrite", "append"] = "create"

    @model_validator(mode="before")
    @classmethod
    def _coerce_path(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("path"):
            for alt in ("rel_path", "filename", "file_path", "filepath", "target"):
                if data.get(alt):
                    data["path"] = str(data[alt])
                    break
        return data


class DeleteFileArgs(BaseModel):
    path: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _coerce_path(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("path"):
            for alt in ("rel_path", "filename", "file_path", "filepath", "target"):
                if data.get(alt):
                    data["path"] = str(data[alt])
                    break
        return data


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
    query: str = Field(default="", min_length=0)
    queries: list[str] | None = None
    max_results: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="before")
    @classmethod
    def _coerce_queries(cls, data: object) -> object:
        if isinstance(data, dict):
            if not data.get("query") and data.get("queries"):
                qs = data["queries"]
                if isinstance(qs, list) and qs:
                    data["query"] = str(qs[0])
                elif isinstance(qs, str):
                    data["query"] = qs
        return data


class MemorySearchArgs(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class MemoryCommitArgs(BaseModel):
    """WO-9 A2 (ADR-010): grounded memory_commit.

    The model supplies a fact CANDIDATE (s, p, o) plus a verbatim quote it
    claims to come from the user's own words this turn. The dispatcher never
    stores model-authored prose: the candidate is validated against the
    current-turn USER_EXPLICIT transcript by FactExtractor (verbatim quote
    grounding) and signed USER_DERIVED, or refused with an honest error.
    """

    s: str = Field(min_length=1, description="Fact subject (e.g. 'user')")
    p: str = Field(
        min_length=2,
        max_length=41,
        description="Predicate slug (lowercase snake_case, 2-41 chars)",
    )
    o: str = Field(min_length=1, description="Fact object (e.g. 'Sean')")
    quote: str = Field(min_length=1, description="Verbatim quote from the user's words")
    content: str = Field(default="", description="Deprecated: unused by the grounded dispatcher")
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


class CalcMathArgs(BaseModel):
    expr: str = Field(min_length=1, description="Mathematical expression to evaluate")
