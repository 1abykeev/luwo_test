"""The Claude implementation of LLMClient. The only file that imports the Anthropic SDK."""

import anthropic

from .llm import LLMError, LLMRequest, LLMResponse, Message, ToolCall, ToolSpec, Usage

_STOP_REASONS = {
    "end_turn": "end_turn",
    "stop_sequence": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "refusal": "refusal",
}


def to_api_messages(messages: list[Message]) -> list[dict]:
    api_messages = []
    for m in messages:
        if m.role == "assistant":
            blocks: list[dict] = []
            if m.text:
                blocks.append({"type": "text", "text": m.text})
            blocks += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in m.tool_calls
            ]
            if not blocks:
                raise ValueError("An assistant message needs text or tool calls")
            api_messages.append({"role": "assistant", "content": blocks})
        else:
            if not m.tool_results:
                api_messages.append({"role": "user", "content": m.text})
                continue
            # Tool results must come first in the user turn, any text after them.
            blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": r.tool_call_id,
                    "content": r.content,
                    "is_error": r.is_error,
                }
                for r in m.tool_results
            ]
            if m.text:
                blocks.append({"type": "text", "text": m.text})
            api_messages.append({"role": "user", "content": blocks})
    return api_messages


def to_api_tools(tools: list[ToolSpec]) -> list[dict]:
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]


def parse_response(response) -> LLMResponse:
    text = "".join(block.text for block in response.content if block.type == "text")
    tool_calls = tuple(
        ToolCall(id=block.id, name=block.name, input=dict(block.input))
        for block in response.content
        if block.type == "tool_use"
    )
    usage = response.usage
    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        usage=Usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        ),
        stop_reason=_STOP_REASONS.get(response.stop_reason, "other"),
    )


def _to_llm_error(error: anthropic.APIError) -> LLMError:
    if isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return LLMError("auth", "The model provider rejected our credentials")
    if isinstance(error, anthropic.RateLimitError):
        return LLMError("rate_limited", "The model provider is rate limiting us")
    if isinstance(error, anthropic.APITimeoutError):
        return LLMError("timeout", "The model took too long to answer")
    if isinstance(error, anthropic.APIConnectionError):
        return LLMError("unavailable", "Could not reach the model provider")
    if isinstance(error, anthropic.APIStatusError) and error.status_code >= 500:
        return LLMError("unavailable", "The model provider is having problems")
    if isinstance(error, anthropic.APIStatusError) and error.status_code < 500:
        return LLMError("bad_request", f"The model provider rejected the request ({error.status_code})")
    return LLMError("error", "Unexpected error from the model provider")


class ClaudeClient:
    def __init__(self, api_key: str, model: str, thinking: str = "disabled", timeout: float = 60.0):
        # The SDK already retries connection errors, 429 and 5xx twice with backoff.
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)
        self._model = model
        self._thinking = thinking

    async def complete(self, request: LLMRequest) -> LLMResponse:
        params: dict = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            # Prompt caching, two breakpoints:
            # 1. on the system prompt: tools + system never change for a user, so every conversation
            #    (not just every step of one) reads them from the cache at a fraction of the price;
            # 2. top-level: the growing conversation is cached from step to step.
            "system": [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            "messages": to_api_messages(request.messages),
            "cache_control": {"type": "ephemeral"},
        }
        if request.tools:
            params["tools"] = to_api_tools(request.tools)
        if self._thinking:
            params["thinking"] = {"type": self._thinking}
        try:
            response = await self._client.messages.create(**params)
        except anthropic.APIError as error:
            raise _to_llm_error(error) from error
        return parse_response(response)
