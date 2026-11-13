"""Drop-in Python agent integrations: sync/async `@signed_tool` decorator and
`verify_chat_turn(messages)` for OpenAI, Anthropic, MCP, PydanticAI, and LangGraph loops.
"""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ParamSpec, TypeVar, overload

from epistemic_guard.provenance import DomainSigner
from epistemic_guard.schemas import SupervisionVerdict, ToolReceipt
from epistemic_guard.store import MerkleReceiptLog
from epistemic_guard.supervision import ReceiptSupervisor

P = ParamSpec("P")
R = TypeVar("R")


def _coerce_arg_scalar(val: object) -> str | int | float | bool:
    if isinstance(val, (str, int, float, bool)):
        return val
    try:
        return json.dumps(val, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return str(val)


def _extract_bound_args(
    fn: Callable[..., Any], args: tuple[object, ...], kwargs: dict[str, object]
) -> dict[str, str | int | float | bool]:
    try:
        sig = inspect.signature(fn)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return {
            k: _coerce_arg_scalar(v)
            for k, v in bound.arguments.items()
            if k not in ("self", "cls")
        }
    except Exception:
        return {k: _coerce_arg_scalar(v) for k, v in kwargs.items()}


class ReceiptRecorder:
    """Collects signed or unsigned `ToolReceipt` records across a single agent turn."""

    def __init__(
        self,
        *,
        signer: DomainSigner | None = None,
        merkle_log: MerkleReceiptLog | None = None,
    ) -> None:
        self._signer = signer
        self._merkle_log = merkle_log
        self._turn_receipts: list[ToolReceipt] = []

    @property
    def receipts(self) -> list[ToolReceipt]:
        return list(self._turn_receipts)

    def clear_turn(self) -> None:
        """Reset per-turn receipt list (while keeping `merkle_log` audit history intact)."""
        self._turn_receipts.clear()

    def record(
        self,
        tool: str,
        *,
        ok: bool,
        args: dict[str, str | int | float | bool],
        output: str,
    ) -> ToolReceipt:
        raw = ToolReceipt(tool=tool, ok=ok, args=args, output=output)
        final = self._signer.sign_receipt(raw) if self._signer is not None else raw
        self._turn_receipts.append(final)
        if self._merkle_log is not None:
            self._merkle_log.append(final)
        return final

    @overload
    def tool(self, fn: Callable[P, R], *, name: str | None = None) -> Callable[P, R]: ...

    @overload
    def tool(
        self, fn: None = None, *, name: str | None = None
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...

    def tool(
        self,
        fn: Callable[P, R] | None = None,
        *,
        name: str | None = None,
    ) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
        """Decorator recording an authentic `ToolReceipt` for sync or async tool functions."""
        return signed_tool(fn, recorder=self, name=name)


@overload
def signed_tool(  # noqa: UP047
    fn: Callable[P, R],
    *,
    recorder: ReceiptRecorder,
    name: str | None = None,
) -> Callable[P, R]: ...


@overload
def signed_tool(
    fn: None = None,
    *,
    recorder: ReceiptRecorder,
    name: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def signed_tool(  # noqa: UP047
    fn: Callable[P, R] | None = None,
    *,
    recorder: ReceiptRecorder,
    name: str | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Wrap a sync or async Python tool function so every execution emits a `ToolReceipt`.

    If the wrapped tool raises an exception, an explicit `ToolReceipt(ok=False, ...)` is
    recorded before re-raising so the LLM cannot claim a failed call succeeded.
    """

    def _decorator(func: Callable[P, R]) -> Callable[P, R]:
        tool_name = name or func.__name__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def _async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                arg_map = _extract_bound_args(func, args, kwargs)
                try:
                    res = await func(*args, **kwargs)
                except Exception as exc:
                    recorder.record(
                        tool_name,
                        ok=False,
                        args=arg_map,
                        output=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                recorder.record(tool_name, ok=True, args=arg_map, output=str(res))
                return res

            return _async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def _sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            arg_map = _extract_bound_args(func, args, kwargs)
            try:
                res = func(*args, **kwargs)
            except Exception as exc:
                recorder.record(
                    tool_name,
                    ok=False,
                    args=arg_map,
                    output=f"{type(exc).__name__}: {exc}",
                )
                raise
            recorder.record(tool_name, ok=True, args=arg_map, output=str(res))
            return res

        return _sync_wrapper

    if fn is not None:
        return _decorator(fn)
    return _decorator


def _extract_receipts_from_messages(messages: Sequence[Mapping[str, Any]]) -> list[ToolReceipt]:
    """Extract `ToolReceipt` items from OpenAI-style `tool_calls` + `role='tool'` message pairs."""
    call_meta: dict[str, tuple[str, dict[str, str | int | float | bool]]] = {}
    extracted: list[ToolReceipt] = []

    for msg in messages:
        role = str(msg.get("role", "")).lower()
        if role == "assistant":
            tcalls = msg.get("tool_calls")
            if isinstance(tcalls, list):
                for tc in tcalls:
                    if not isinstance(tc, Mapping):
                        continue
                    cid = str(tc.get("id", ""))
                    fn_obj = tc.get("function")
                    if isinstance(fn_obj, Mapping):
                        tname = str(fn_obj.get("name", ""))
                        raw_args = fn_obj.get("arguments", "{}")
                        parsed_args: dict[str, str | int | float | bool] = {}
                        if isinstance(raw_args, str):
                            try:
                                obj = json.loads(raw_args)
                                if isinstance(obj, Mapping):
                                    parsed_args = {
                                        str(k): _coerce_arg_scalar(v) for k, v in obj.items()
                                    }
                            except Exception:
                                parsed_args = {}
                        elif isinstance(raw_args, Mapping):
                            parsed_args = {
                                str(k): _coerce_arg_scalar(v) for k, v in raw_args.items()
                            }
                        if cid and tname:
                            call_meta[cid] = (tname, parsed_args)
        elif role == "tool":
            cid = str(msg.get("tool_call_id", ""))
            content = str(msg.get("content", ""))
            is_err = bool(msg.get("is_error", False)) or content.lower().startswith(
                ("error:", "traceback")
            )
            tname, parsed_args = call_meta.get(cid, (str(msg.get("name", "tool")), {}))
            extracted.append(
                ToolReceipt(
                    tool=tname,
                    ok=not is_err,
                    call_id=cid or "tool-msg",
                    args=parsed_args,
                    output=content,
                )
            )
    return extracted


def verify_chat_turn(
    messages: Sequence[Mapping[str, Any]],
    *,
    receipts: Sequence[ToolReceipt] | None = None,
    supervisor: ReceiptSupervisor | None = None,
    device: str | None = None,
    warn_on_missing: bool = True,
) -> SupervisionVerdict:
    """Verify the latest assistant message in an OpenAI/Anthropic history against `ToolReceipt`s."""
    sup = supervisor or ReceiptSupervisor(device=device, warn_on_missing=warn_on_missing)

    last_assistant = ""
    last_user = ""
    for msg in reversed(messages):
        role = str(msg.get("role", "")).lower()
        content = msg.get("content", "")
        text = content if isinstance(content, str) else json.dumps(content)
        if not last_assistant and role == "assistant" and text.strip():
            last_assistant = text
        elif last_assistant and role == "user" and text.strip():
            last_user = text
            break

    active_receipts = (
        list(receipts) if receipts is not None else _extract_receipts_from_messages(messages)
    )
    return sup.verify_narration(
        last_assistant,
        receipts=active_receipts,
        user_prompt=last_user,
    )
