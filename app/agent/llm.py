"""Our own types for talking to a language model.

The agent loop only uses these, never an SDK's objects. To use another provider, write one
new class with a `complete()` method (see claude_client.py); nothing else changes."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call. `input_schema` is a JSON Schema for its arguments."""

    name: str
    description: str
    input_schema: dict


@dataclass(frozen=True)
class ToolCall:
    """The model asking us to run a tool."""

    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class ToolResult:
    """What we send back after running a ToolCall."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Message:
    """One turn. role='user': text and/or tool results. role='assistant': text and/or tool calls."""

    role: str  # "user" or "assistant"
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()

    def to_dict(self) -> dict:
        """Plain JSON, so conversations can be saved in the database."""
        return {
            "role": self.role,
            "text": self.text,
            "tool_calls": [{"id": c.id, "name": c.name, "input": c.input} for c in self.tool_calls],
            "tool_results": [
                {"tool_call_id": r.tool_call_id, "content": r.content, "is_error": r.is_error}
                for r in self.tool_results
            ],
        }

    @staticmethod
    def from_dict(data: dict) -> "Message":
        return Message(
            role=data["role"],
            text=data.get("text", ""),
            tool_calls=tuple(ToolCall(c["id"], c["name"], c["input"]) for c in data.get("tool_calls", [])),
            tool_results=tuple(
                ToolResult(r["tool_call_id"], r["content"], r.get("is_error", False))
                for r in data.get("tool_results", [])
            ),
        )


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0  # not counting cached tokens
    output_tokens: int = 0
    cache_read_tokens: int = 0  # served from the prompt cache (much cheaper)
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True)
class LLMRequest:
    system: str
    messages: list[Message]
    tools: list[ToolSpec] = field(default_factory=list)
    max_tokens: int = 2000


@dataclass(frozen=True)
class LLMResponse:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = Usage()
    # "end_turn", "tool_use", "max_tokens", "refusal" or "other"
    stop_reason: str = "end_turn"


class LLMError(Exception):
    """The model could not be reached or refused the call. `kind` is one of:
    rate_limited, unavailable, timeout, auth, bad_request, error."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...


# A fake client's script: a list of responses, or a function that decides per request.
Script = list[LLMResponse] | Callable[[LLMRequest], LLMResponse]
