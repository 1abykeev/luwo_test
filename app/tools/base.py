"""The tool machinery: what a tool is, what it returns, and how errors become results."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agent.llm import ToolCall, ToolSpec
from app.domain.errors import DomainError, InvalidRequest
from app.domain.models import Actor
from app.services import Services

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Built by our code for each chat request. The model can't change any of it."""

    actor: Actor
    services: Services
    conversation_id: str
    # Tokens proposed during this request. A change can't be confirmed in the same request
    # that proposed it: the user has to answer first.
    proposals_this_turn: set[str] = field(default_factory=set)
    # Same rule for namesake overrides: a token issued in this request can't be used in it.
    override_tokens_this_turn: set[str] = field(default_factory=set)


@dataclass
class ToolOutcome:
    result: dict  # JSON the model reads
    blocks: list[dict] = field(default_factory=list)  # what the mobile app draws
    is_error: bool = False
    # For analytics: ok, pending_confirmation, confirmed, cancelled, out_of_scope,
    # permission_denied, not_found, conflict, invalid_request, error
    kind: str = "ok"


Handler = Callable[[ToolContext, dict], Awaitable[ToolOutcome]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    request_type: str  # what kind of request this tool answers: show, search, add, remove, ...
    handler: Handler

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.input_schema)


def banner(level: str, message: str, code: str | None = None) -> dict:
    return {"type": "banner", "level": level, "message": message, "code": code}


def error_outcome(error: DomainError) -> ToolOutcome:
    blocks = [banner("error", error.message, error.code)] if error.code == "permission_denied" else []
    return ToolOutcome(
        result={"error": error.code, "message": error.message, "details": error.details},
        blocks=blocks,
        is_error=True,
        kind=error.code,
    )


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}
        self.specs = [t.spec for t in tools]  # same order every time: keeps the prompt cache valid

    def request_type(self, tool_name: str) -> str:
        tool = self._tools.get(tool_name)
        return tool.request_type if tool else "other"

    async def execute(self, ctx: ToolContext, call: ToolCall) -> ToolOutcome:
        tool = self._tools.get(call.name)
        if tool is None:
            return error_outcome(InvalidRequest(f"There is no tool named '{call.name}'"))
        try:
            return await tool.handler(ctx, call.input)
        except DomainError as error:
            return error_outcome(error)
        except Exception:
            # A bug or a backend failure. The model must learn that the action did NOT happen.
            logger.exception("Tool %s failed", call.name)
            message = "The backend failed. The requested action was NOT performed."
            return ToolOutcome(
                result={"error": "internal_error", "message": message, "details": {}},
                blocks=[banner("error", message, "internal_error")],
                is_error=True,
                kind="error",
            )


# ---- small helpers for reading tool arguments ----

def str_arg(args: dict, key: str, required: bool = True) -> str | None:
    value = args.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise InvalidRequest(f"'{key}' is required")
        return None
    if not isinstance(value, str):
        raise InvalidRequest(f"'{key}' must be text")
    return value.strip()


def int_arg(args: dict, key: str) -> int:
    value = args.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise InvalidRequest(f"'{key}' must be a number")
    try:
        return int(value)
    except ValueError:
        raise InvalidRequest(f"'{key}' must be a number") from None


def bool_arg(args: dict, key: str) -> bool:
    return args.get(key) is True


def schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}
