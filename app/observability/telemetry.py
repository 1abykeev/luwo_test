"""The agent's window to the outside world: logs, metrics and the request log.

The agent calls an `Observer` at four moments (a conversation starts, a tool finishes, a model call
finishes, a request finishes) and knows nothing else about monitoring. `Telemetry` is the real observer;
`NullObserver` does nothing (tests and anyone who wants no monitoring)."""

import functools
import inspect
import json
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from . import metrics
from .request_log import RequestLogEntry, RequestLogStore

if TYPE_CHECKING:  # only for type hints: importing these at run time would be circular
    from app.agent.agent import ChatResult
    from app.domain.models import Actor
    from app.tools import ToolOutcome


class Observer(Protocol):
    def request_scope(self, conversation_id: str, user_id: int) -> AbstractContextManager[None]: ...
    def conversation_started(self, conversation_id: str) -> None: ...
    def tool_finished(self, actor: "Actor", tool: str, args: dict, outcome: "ToolOutcome", seconds: float) -> None: ...
    def llm_call_finished(self, seconds: float, usage: Any | None, status: str) -> None: ...
    async def request_finished(self, actor: "Actor", user_text: str | None, result: "ChatResult") -> None: ...


class NullObserver:
    def request_scope(self, conversation_id: str, user_id: int) -> AbstractContextManager[None]:
        return nullcontext()

    def conversation_started(self, conversation_id: str) -> None:
        pass

    def tool_finished(self, actor, tool, args, outcome, seconds) -> None:
        pass

    def llm_call_finished(self, seconds, usage, status) -> None:
        pass

    async def request_finished(self, actor, user_text, result) -> None:
        pass


def _redact(args: dict) -> dict:
    """Confirmation and override tokens are secrets of one person: never write them to a log."""
    return {k: ("[redacted]" if "token" in k.lower() else v) for k, v in args.items()}


def _short(value: object, limit: int = 300) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _never_raises(method):
    """Monitoring must never break the chat: a failure here is logged and swallowed."""

    if inspect.iscoroutinefunction(method):
        @functools.wraps(method)
        async def wrapper(self, *args, **kwargs):
            try:
                return await method(self, *args, **kwargs)
            except Exception:
                self._log.exception("telemetry_failed", where=method.__name__)
        return wrapper

    @functools.wraps(method)
    def sync_wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception:
            self._log.exception("telemetry_failed", where=method.__name__)
    return sync_wrapper


class Telemetry:
    def __init__(self, request_log: RequestLogStore | None = None, log_user_text: bool = False):
        self._request_log = request_log
        self._log_user_text = log_user_text
        self._log = structlog.get_logger("luwo.agent")

    @contextmanager
    def request_scope(self, conversation_id: str, user_id: int) -> Iterator[None]:
        """Everything logged inside this block carries the conversation id and the user id."""
        structlog.contextvars.bind_contextvars(conversation_id=conversation_id, user_id=user_id)
        try:
            yield
        finally:
            structlog.contextvars.unbind_contextvars("conversation_id", "user_id")

    @_never_raises
    def conversation_started(self, conversation_id: str) -> None:
        metrics.conversations_started_total.inc()
        self._log.info("conversation_started")

    @_never_raises
    def tool_finished(self, actor: "Actor", tool: str, args: dict, outcome: "ToolOutcome", seconds: float) -> None:
        metrics.tool_calls_total.labels(tool, outcome.kind).inc()
        metrics.tool_seconds.labels(tool).observe(seconds)
        fields: dict[str, Any] = {
            "tool": tool, "result": outcome.kind, "ok": not outcome.is_error, "duration_ms": round(seconds * 1000, 1),
        }
        if self._log_user_text:
            fields["args"] = _short(_redact(args))
        if outcome.is_error:
            fields["error"] = outcome.result.get("error")
            fields["message"] = outcome.result.get("message")
        if outcome.kind == "permission_denied":  # its own event name, so denials are easy to search for
            self._log.warning("permission_denied", role=actor.role.value, **fields)
        elif outcome.kind == "error":
            self._log.error("tool_error", **fields)
        else:
            self._log.info("tool_call", **fields)

    @_never_raises
    def llm_call_finished(self, seconds: float, usage: Any | None, status: str) -> None:
        metrics.llm_calls_total.labels(status).inc()
        metrics.llm_call_seconds.observe(seconds)
        if usage is not None:
            metrics.llm_tokens_total.labels("input").inc(usage.input_tokens)
            metrics.llm_tokens_total.labels("output").inc(usage.output_tokens)
            metrics.llm_tokens_total.labels("cache_read").inc(usage.cache_read_tokens)
            metrics.llm_tokens_total.labels("cache_write").inc(usage.cache_write_tokens)
        if status != "ok":
            self._log.warning("llm_call_failed", status=status, duration_ms=round(seconds * 1000, 1))

    @_never_raises
    async def request_finished(self, actor: "Actor", user_text: str | None, result: "ChatResult") -> None:
        usage = result.usage
        metrics.agent_requests_total.labels(result.request_type, result.outcome).inc()
        metrics.agent_request_seconds.labels(result.request_type).observe(result.duration_ms / 1000)
        metrics.request_tokens.observe(usage.total_tokens)

        fields: dict[str, Any] = {
            "request_type": result.request_type, "outcome": result.outcome, "role": actor.role.value,
            "tools": [r.name for r in result.tool_records], "llm_calls": result.llm_calls,
            "input_tokens": usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens,
            "output_tokens": usage.output_tokens, "cached_tokens": usage.cache_read_tokens,
            "duration_ms": result.duration_ms,
        }
        if self._log_user_text and user_text is not None:
            fields["user_text"] = user_text[:500]
        if result.outcome == "error":
            self._log.error("chat_request", **fields)
        elif result.outcome == "permission_denied":
            self._log.warning("chat_request", **fields)
        else:
            self._log.info("chat_request", **fields)

        if self._request_log is not None:
            await self._request_log.add(RequestLogEntry(
                conversation_id=result.conversation_id, user_id=actor.user_id,
                request_type=result.request_type, outcome=result.outcome,
                tools_called=[r.name for r in result.tool_records],
                input_tokens=fields["input_tokens"], output_tokens=usage.output_tokens,
                cached_tokens=usage.cache_read_tokens, llm_calls=result.llm_calls, latency_ms=result.duration_ms,
            ))
