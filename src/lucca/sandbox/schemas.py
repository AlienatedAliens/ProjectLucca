"""
Project Lucca — Sandbox Tool Request Validation Schemas
Proposal F / D-SEC-04 (Zero-Any Compliant)
"""

from typing import Literal

from pydantic import BaseModel, Field, JsonValue, model_validator


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
        if isinstance(data, dict):
            if not data.get("path"):
                for alt in ("rel_path", "filename", "file_path", "filepath", "target"):
                    if data.get(alt):
                        data["path"] = str(data[alt])
                        break
            if data.get("mode") == "write":
                data["mode"] = "overwrite"
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

    @model_validator(mode="before")
    @classmethod
    def _coerce_path(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("path"):
            for alt in ("rel_path", "directory", "dir", "target"):
                if data.get(alt):
                    data["path"] = str(data[alt])
                    break
        return data


class SearchTextArgs(BaseModel):
    pattern: str = Field(min_length=1)
    path: str = Field(default="")
    max_hits: int = Field(default=200, ge=1, le=2000)

    @model_validator(mode="before")
    @classmethod
    def _coerce_path(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("path"):
            for alt in ("rel_path", "directory", "dir", "target"):
                if data.get(alt):
                    data["path"] = str(data[alt])
                    break
        return data


class RunPythonArgs(BaseModel):
    code: str = Field(min_length=1)
    timeout_s: int = Field(default=15, ge=1, le=60)
    max_output_bytes: int = Field(default=65536, ge=1, le=262144)
    name: str | None = Field(default=None, max_length=60)

    @model_validator(mode="before")
    @classmethod
    def _coerce_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            if "timeout" in data and "timeout_s" not in data:
                data["timeout_s"] = data["timeout"]
        return data


class FetchUrlArgs(BaseModel):
    url: str = Field(min_length=1)
    render: bool = False
    max_chars: int = Field(default=20000, ge=100, le=100000)


class SearchWebArgs(BaseModel):
    query: str = Field(default="", min_length=0)
    queries: list[str] | None = None
    max_results: int = Field(default=5, ge=1, le=20)
    target_entity: str | None = None

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


class QueryCapabilitiesArgs(BaseModel):
    category: str = Field(default="all")


class InvokeSkillArgs(BaseModel):
    skill_id: str = Field(min_length=1)
    args: dict[str, JsonValue] | None = Field(default_factory=dict)


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


class SelfMetricsArgs(BaseModel):
    pass


class SelfHistorySearchArgs(BaseModel):
    query: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _validate_query(cls, data: object) -> object:
        if isinstance(data, dict):
            q = data.get("query")
            if isinstance(q, str) and not q.strip():
                raise ValueError("query is required")
        return data


class SysInfoArgs(BaseModel):
    filter_name: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    timezone: str | None = None


class CalcMathArgs(BaseModel):
    expr: str = Field(min_length=1, description="Mathematical expression to evaluate")


class ScheduleEventArgs(BaseModel):
    event_name: str = Field(min_length=1, description="Human-readable label, e.g. 'call mum'")
    iso_datetime: str = Field(min_length=1, description="ISO 8601 datetime with offset")
    message: str | None = Field(default=None, description="Optional note or reminder text")


class ArtifactVerifyArgs(BaseModel):
    path: str = Field(min_length=1, description="Relative path under workspace")


class ClipboardReadArgs(BaseModel):
    pass


class InboxHandoffArgs(BaseModel):
    filename: str = Field(min_length=1, description="Filename in inbox/ to import")


class ScreenshotCaptureArgs(BaseModel):
    """WO-24 Phase 1: screenshot_capture takes no parameters."""


# Unadvertised/internal tool argument schemas
class GetTaskStatusArgs(BaseModel):
    task_id: str = Field(min_length=1)


class ListTasksArgs(BaseModel):
    status: str | None = None


class CancelTaskArgs(BaseModel):
    task_id: str = Field(min_length=1)


TOOL_ARG_SCHEMAS: dict[str, type[BaseModel]] = {
    "read_file": ReadFileArgs,
    "write_file": WriteFileArgs,
    "search_web": SearchWebArgs,
    "fetch_url": FetchUrlArgs,
    "query_capabilities": QueryCapabilitiesArgs,
    "list_dir": ListDirArgs,
    "search_text": SearchTextArgs,
    "run_python": RunPythonArgs,
    "invoke_skill": InvokeSkillArgs,
    "memory_search": MemorySearchArgs,
    "memory_commit": MemoryCommitArgs,
    "note_write": NoteWriteArgs,
    "note_read": NoteReadArgs,
    "self_metrics": SelfMetricsArgs,
    "run_python_async": RunPythonArgs,
    "self_history_search": SelfHistorySearchArgs,
    "launch_app": LaunchAppArgs,
    "sys_info": SysInfoArgs,
    "calc_math": CalcMathArgs,
    "schedule_event": ScheduleEventArgs,
    "artifact_verify": ArtifactVerifyArgs,
    "clipboard_read": ClipboardReadArgs,
    "inbox_handoff": InboxHandoffArgs,
    "screenshot_capture": ScreenshotCaptureArgs,
}

EXTRA_TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "delete_file": DeleteFileArgs,
    "get_task_status": GetTaskStatusArgs,
    "list_tasks": ListTasksArgs,
    "cancel_task": CancelTaskArgs,
}

__all__ = [
    "ArtifactVerifyArgs",
    "CalcMathArgs",
    "CancelTaskArgs",
    "ClipboardReadArgs",
    "DeleteFileArgs",
    "EXTRA_TOOL_SCHEMAS",
    "FetchUrlArgs",
    "GetTaskStatusArgs",
    "InboxHandoffArgs",
    "InvokeSkillArgs",
    "LaunchAppArgs",
    "ListDirArgs",
    "ListTasksArgs",
    "MemoryCommitArgs",
    "MemorySearchArgs",
    "NoteReadArgs",
    "NoteWriteArgs",
    "QueryCapabilitiesArgs",
    "ReadFileArgs",
    "RunPythonArgs",
    "ScheduleEventArgs",
    "ScreenshotCaptureArgs",
    "SearchTextArgs",
    "SearchWebArgs",
    "SelfHistorySearchArgs",
    "SelfMetricsArgs",
    "SysInfoArgs",
    "TOOL_ARG_SCHEMAS",
    "WriteFileArgs",
]
