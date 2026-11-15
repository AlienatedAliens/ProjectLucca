"""Drop-in Python agent integrations: sync/async `@signed_tool` decorator and
`verify_chat_turn(messages)` for OpenAI, Anthropic, MCP, PydanticAI, and LangGraph loops.
"""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
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
        executed: bool = True,
        error_code: str = "",
        call_id: str | None = None,
    ) -> ToolReceipt:
        kwargs: dict[str, Any] = {
            "tool": tool,
            "ok": ok,
            "executed": executed,
            "error_code": error_code,
            "args": args,
            "output": output,
        }
        if call_id is not None:
            kwargs["call_id"] = call_id
        raw = ToolReceipt(**kwargs)
        final = self._signer.sign_receipt(raw) if self._signer is not None else raw
        self._turn_receipts.append(final)
        if self._merkle_log is not None:
            self._merkle_log.append(final)
        return final

    def record_rejection(
        self,
        tool: str,
        *,
        args: Mapping[str, object] | None = None,
        reason: str,
        error_code: str = "invalid_tool_arguments",
        call_id: str | None = None,
    ) -> ToolReceipt:
        """Record an explicit `executed=False, ok=False` receipt on pre-dispatch rejection."""
        coerced_args = {
            str(k): _coerce_arg_scalar(v) for k, v in (args or {}).items()
        }
        return self.record(
            tool,
            ok=False,
            executed=False,
            error_code=error_code,
            args=coerced_args,
            output=reason,
            call_id=call_id,
        )

    def _parse_dispatch_kwargs(
        self,
        tool_name: str,
        raw_args: str | Mapping[str, object],
        *,
        call_id: str | None = None,
    ) -> dict[str, object]:
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args) if raw_args.strip() else {}
            except Exception as exc:
                self.record_rejection(
                    tool_name,
                    args={"_raw_arguments": raw_args},
                    reason=f"Malformed JSON tool arguments: {exc}",
                    error_code="invalid_json_arguments",
                    call_id=call_id,
                )
                raise ValueError(f"Malformed JSON arguments for '{tool_name}': {exc}") from exc
            if not isinstance(parsed, Mapping):
                self.record_rejection(
                    tool_name,
                    args={"_raw_arguments": raw_args},
                    reason="Tool arguments JSON must decode to an object.",
                    error_code="invalid_tool_arguments",
                    call_id=call_id,
                )
                raise TypeError(f"Tool arguments for '{tool_name}' must be a JSON object.")
            return {str(k): v for k, v in parsed.items()}
        return {str(k): v for k, v in raw_args.items()}

    def dispatch(
        self,
        fn: Callable[..., R],
        raw_args: str | Mapping[str, object],
        *,
        name: str | None = None,
        call_id: str | None = None,
    ) -> R:
        """Validate JSON/dict arguments against `fn` and record pre-dispatch rejections."""
        raw_fn: Callable[..., Any] = getattr(fn, "__wrapped__", fn)
        tool_name = name or raw_fn.__name__
        kwargs = self._parse_dispatch_kwargs(tool_name, raw_args, call_id=call_id)
        try:
            sig = inspect.signature(raw_fn)
            bound = sig.bind(**kwargs)
            bound.apply_defaults()
        except TypeError as exc:
            self.record_rejection(
                tool_name,
                args=kwargs,
                reason=str(exc),
                error_code="invalid_tool_arguments",
                call_id=call_id,
            )
            raise
        bound_args = {
            k: _coerce_arg_scalar(v) for k, v in bound.arguments.items() if k not in ("self", "cls")
        }
        try:
            res = raw_fn(**kwargs)
        except Exception as exc:
            self.record(
                tool_name,
                ok=False,
                executed=True,
                error_code=type(exc).__name__,
                args=bound_args,
                output=f"{type(exc).__name__}: {exc}",
                call_id=call_id,
            )
            raise
        self.record(
            tool_name,
            ok=True,
            executed=True,
            args=bound_args,
            output=str(res),
            call_id=call_id,
        )
        return res  # type: ignore[no-any-return]

    async def adispatch(
        self,
        fn: Callable[..., Awaitable[R]],
        raw_args: str | Mapping[str, object],
        *,
        name: str | None = None,
        call_id: str | None = None,
    ) -> R:
        """Async counterpart to `dispatch()` with pre-dispatch schema/JSON rejection receipts."""
        raw_fn: Callable[..., Awaitable[R]] = getattr(fn, "__wrapped__", fn)
        tool_name = name or raw_fn.__name__
        kwargs = self._parse_dispatch_kwargs(tool_name, raw_args, call_id=call_id)
        try:
            sig = inspect.signature(raw_fn)
            bound = sig.bind(**kwargs)
            bound.apply_defaults()
        except TypeError as exc:
            self.record_rejection(
                tool_name,
                args=kwargs,
                reason=str(exc),
                error_code="invalid_tool_arguments",
                call_id=call_id,
            )
            raise
        bound_args = {
            k: _coerce_arg_scalar(v) for k, v in bound.arguments.items() if k not in ("self", "cls")
        }
        try:
            res = await raw_fn(**kwargs)
        except Exception as exc:
            self.record(
                tool_name,
                ok=False,
                executed=True,
                error_code=type(exc).__name__,
                args=bound_args,
                output=f"{type(exc).__name__}: {exc}",
                call_id=call_id,
            )
            raise
        self.record(
            tool_name,
            ok=True,
            executed=True,
            args=bound_args,
            output=str(res),
            call_id=call_id,
        )
        return res

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
        sig = inspect.signature(func)

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def _async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                arg_map = _extract_bound_args(func, args, kwargs)
                try:
                    sig.bind(*args, **kwargs)
                except TypeError as exc:
                    recorder.record(
                        tool_name,
                        ok=False,
                        executed=False,
                        error_code="invalid_tool_arguments",
                        args=arg_map,
                        output=f"TypeError: {exc}",
                    )
                    raise
                try:
                    res = await func(*args, **kwargs)
                except Exception as exc:
                    recorder.record(
                        tool_name,
                        ok=False,
                        executed=True,
                        error_code=type(exc).__name__,
                        args=arg_map,
                        output=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                recorder.record(tool_name, ok=True, executed=True, args=arg_map, output=str(res))
                return res

            return _async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def _sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            arg_map = _extract_bound_args(func, args, kwargs)
            try:
                sig.bind(*args, **kwargs)
            except TypeError as exc:
                recorder.record(
                    tool_name,
                    ok=False,
                    executed=False,
                    error_code="invalid_tool_arguments",
                    args=arg_map,
                    output=f"TypeError: {exc}",
                )
                raise
            try:
                res = func(*args, **kwargs)
            except Exception as exc:
                recorder.record(
                    tool_name,
                    ok=False,
                    executed=True,
                    error_code=type(exc).__name__,
                    args=arg_map,
                    output=f"{type(exc).__name__}: {exc}",
                )
                raise
            recorder.record(tool_name, ok=True, executed=True, args=arg_map, output=str(res))
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
