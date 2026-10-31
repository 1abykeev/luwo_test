"""The LLM layer: our message types, the Claude conversions, and the fake client."""

import time
from types import SimpleNamespace

import pytest

from app.agent.claude_client import parse_response, to_api_messages, to_api_tools
from app.agent.fake_client import FakeLLMClient, text_response, tool_response
from app.agent.llm import LLMRequest, Message, ToolCall, ToolResult, ToolSpec, Usage

# ---- our own types ----

def test_a_message_survives_a_round_trip_through_json():
    message = Message(
        "assistant", "Looking it up",
        tool_calls=(ToolCall("c1", "search_students", {"name": "Алина"}),),
    )
    result = Message("user", tool_results=(ToolResult("c1", "[]", is_error=True),))
    assert Message.from_dict(message.to_dict()) == message
    assert Message.from_dict(result.to_dict()) == result


def test_usage_adds_up():
    total = Usage(10, 5, 100, 0) + Usage(20, 7, 0, 300)
    assert total == Usage(30, 12, 100, 300) and total.total_tokens == 442


# ---- conversion to the Claude format ----

def test_messages_are_converted_for_the_api():
    messages = [
        Message("user", "Найди Алину"),
        Message("assistant", "Ищу", tool_calls=(ToolCall("c1", "search_students", {"name": "Алина"}),)),
        Message("user", tool_results=(ToolResult("c1", "[...]"),)),
        Message("assistant", "Нашёл одну."),
    ]
    api = to_api_messages(messages)

    assert api[0] == {"role": "user", "content": "Найди Алину"}
    assert api[1]["content"] == [
        {"type": "text", "text": "Ищу"},
        {"type": "tool_use", "id": "c1", "name": "search_students", "input": {"name": "Алина"}},
    ]
    assert api[2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "[...]", "is_error": False}],
    }
    assert api[3]["content"] == [{"type": "text", "text": "Нашёл одну."}]


def test_tool_results_come_before_text_in_a_user_turn():
    api = to_api_messages([Message("user", "Да", tool_results=(ToolResult("c1", "ok"),))])
    assert [b["type"] for b in api[0]["content"]] == ["tool_result", "text"]


def test_an_empty_assistant_message_is_refused():
    with pytest.raises(ValueError):
        to_api_messages([Message("assistant")])


def test_tools_are_converted():
    spec = ToolSpec("t", "does t", {"type": "object", "properties": {}})
    assert to_api_tools([spec]) == [{"name": "t", "description": "does t", "input_schema": spec.input_schema}]


# ---- reading the API response (with a stand-in for the SDK object) ----

def api_response(content, stop_reason="end_turn", **usage):
    usage = {"input_tokens": 10, "output_tokens": 5, **usage}
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=SimpleNamespace(**usage))


def test_a_text_answer_is_parsed():
    response = parse_response(api_response([SimpleNamespace(type="text", text="Привет")]))
    assert (response.text, response.tool_calls, response.stop_reason) == ("Привет", (), "end_turn")
    assert response.usage == Usage(10, 5, 0, 0)


def test_a_tool_call_is_parsed_with_cache_usage():
    block = SimpleNamespace(type="tool_use", id="toolu_1", name="search_students", input={"name": "Алина"})
    response = parse_response(
        api_response([block], "tool_use", cache_read_input_tokens=800, cache_creation_input_tokens=50)
    )
    assert response.stop_reason == "tool_use"
    assert response.tool_calls == (ToolCall("toolu_1", "search_students", {"name": "Алина"}),)
    assert response.usage == Usage(10, 5, 800, 50)


def test_unknown_stop_reasons_become_other():
    assert parse_response(api_response([], "pause_turn")).stop_reason == "other"
    assert parse_response(api_response([], "refusal")).stop_reason == "refusal"


# ---- the fake client ----

REQUEST = LLMRequest("system", [Message("user", "hi")])


async def test_the_fake_answers_in_script_order_and_records_requests():
    fake = FakeLLMClient([tool_response("search_students", {"name": "А"}), text_response("Готово")])
    first = await fake.complete(REQUEST)
    second = await fake.complete(REQUEST)

    assert first.tool_calls[0].name == "search_students" and first.stop_reason == "tool_use"
    assert second.text == "Готово"
    assert len(fake.requests) == 2


async def test_the_fake_fails_loudly_when_the_script_runs_out():
    fake = FakeLLMClient([text_response("one")])
    await fake.complete(REQUEST)
    with pytest.raises(AssertionError):
        await fake.complete(REQUEST)


async def test_the_fake_can_decide_per_request():
    fake = FakeLLMClient(lambda request: text_response(request.messages[-1].text.upper()))
    assert (await fake.complete(LLMRequest("s", [Message("user", "abc")]))).text == "ABC"


async def test_the_fake_can_imitate_latency():
    fake = FakeLLMClient([text_response("slow")], delay=0.05)
    started = time.perf_counter()
    await fake.complete(REQUEST)
    assert time.perf_counter() - started >= 0.05


# ---- the real model: costs a fraction of a cent, so it only runs with  pytest -m live ----

@pytest.mark.live
async def test_claude_calls_a_tool_and_answers_from_the_result():
    from app.agent.factory import build_llm_client

    client = build_llm_client()
    tools = [ToolSpec("search_students", "Search students by name.",
                      {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]})]
    system = "You help teachers with student lists. Use tools to look things up."
    messages = [Message("user", "Find Alina in my list")]

    first = await client.complete(LLMRequest(system, messages, tools))
    assert first.tool_calls and first.tool_calls[0].name == "search_students"

    messages += [
        Message("assistant", first.text, tool_calls=first.tool_calls),
        Message("user", tool_results=(ToolResult(first.tool_calls[0].id, '[{"full_name": "Alina Smirnova", "class": "3A"}]'),)),
    ]
    second = await client.complete(LLMRequest(system, messages, tools))
    assert "3A" in second.text or "3А" in second.text
