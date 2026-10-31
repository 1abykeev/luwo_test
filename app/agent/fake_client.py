"""A scripted stand-in for the model: for tests and load tests, no network, no cost."""

import asyncio

from .llm import LLMRequest, LLMResponse, Script, ToolCall, Usage


def text_response(text: str, usage: Usage = Usage(input_tokens=100, output_tokens=20)) -> LLMResponse:
    return LLMResponse(text=text, usage=usage, stop_reason="end_turn")


def tool_response(name: str, input: dict, id: str = "call_1", text: str = "") -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_calls=(ToolCall(id=id, name=name, input=input),),
        usage=Usage(input_tokens=100, output_tokens=20),
        stop_reason="tool_use",
    )


class FakeLLMClient:
    """Answers from a script.

    script: a list (answers are used in order) or a function that looks at the request and
            decides (useful when many conversations run at once).
    delay:  seconds to wait before answering, to imitate real model latency.
    record: keep every request in `requests` for assertions. Switch it off for long load tests, where the
            list would grow without end and distort the memory numbers."""

    def __init__(self, script: Script, delay: float = 0.0, record: bool = True):
        self._script = script
        self._delay = delay
        self._record = record
        self._position = 0
        self.requests: list[LLMRequest] = []  # every request received, for assertions in tests

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self._record:
            self.requests.append(request)
        if self._delay:
            await asyncio.sleep(self._delay)
        if callable(self._script):
            return self._script(request)
        if self._position >= len(self._script):
            raise AssertionError("The fake model was asked for more answers than the script has")
        response = self._script[self._position]
        self._position += 1
        return response
