"""The scripted model used by the load test: it must call real tools so the load reaches services and the DB."""

import pytest

from app.agent.llm import LLMRequest, Message, ToolCall, ToolResult
from app.agent.load_script import load_test_script


def ask(text: str) -> LLMRequest:
    return LLMRequest(system="", messages=[Message("user", text)])


def test_a_class_request_calls_the_roster_tool_with_the_class_name():
    answer = load_test_script(ask("Покажи список учеников 4А"))
    [call] = answer.tool_calls
    assert (call.name, call.input) == ("list_class_students", {"class_name": "4А"})


def test_a_search_request_calls_the_search_tool():
    [call] = load_test_script(ask("Найди Амир")).tool_calls
    assert (call.name, call.input) == ("search_students", {"name": "Амир"})


def test_a_class_overview_request_calls_list_classes():
    [call] = load_test_script(ask("Какие есть классы?")).tool_calls
    assert call.name == "list_classes"


def test_anything_else_gets_a_plain_text_answer_without_tools():
    answer = load_test_script(ask("Привет"))
    assert answer.tool_calls == () and answer.text


def test_after_a_tool_result_the_model_answers_in_text():
    call = ToolCall("c1", "list_classes", {})
    request = LLMRequest(
        system="",
        messages=[
            Message("user", "Какие есть классы?"),
            Message("assistant", "", tool_calls=(call,)),
            Message("user", "", tool_results=(ToolResult("c1", "{}"),)),
        ],
    )
    answer = load_test_script(request)
    assert answer.tool_calls == () and answer.text


# ---- review: edge cases of the regexes, and the factory that the memory numbers depend on ----


@pytest.mark.parametrize("typed, expected", [
    ("Найди Амир, пожалуйста", "Амир"),
    ("где Алина?", "Алина"),
    ("Найди Анна-Мария", "Анна-Мария"),
])
def test_the_search_name_does_not_include_punctuation(typed, expected):
    [call] = load_test_script(ask(typed)).tool_calls
    assert (call.name, call.input) == ("search_students", {"name": expected})


@pytest.mark.parametrize("typed, expected", [
    ("Покажи список учеников 3 б", "3Б"),
    ("покажи класс 11б", "11Б"),
    ("Список 4а", "4А"),
])
def test_class_names_are_found_in_lowercase_and_with_a_space(typed, expected):
    [call] = load_test_script(ask(typed)).tool_calls
    assert (call.name, call.input) == ("list_class_students", {"class_name": expected})


def test_numbers_in_a_sentence_are_not_mistaken_for_a_class():
    answer = load_test_script(ask("У меня 2 и 3 вопроса про учеников"))
    assert answer.tool_calls == ()


def test_a_class_name_without_a_list_word_is_not_a_roster_request():
    assert load_test_script(ask("Привет, 4А")).tool_calls == ()


def test_a_message_that_carries_tool_results_is_always_answered_with_text():
    call = ToolCall("c1", "list_classes", {})
    mixed = Message("user", "Покажи список учеников 4А", tool_results=(ToolResult("c1", "{}"),))
    answer = load_test_script(LLMRequest(system="", messages=[Message("assistant", "", tool_calls=(call,)), mixed]))
    assert answer.tool_calls == () and answer.text


async def test_the_fake_provider_does_not_keep_every_request(monkeypatch):
    from app.agent import factory
    from app.agent.fake_client import FakeLLMClient

    monkeypatch.setattr(factory.settings, "llm_provider", "fake")
    monkeypatch.setattr(factory.settings, "fake_llm_delay", 0.0)
    client = factory.build_llm_client()
    assert isinstance(client, FakeLLMClient)
    await client.complete(ask("Привет"))
    assert client.requests == []  # a long load test would otherwise grow this list forever


def test_the_fake_provider_uses_the_configured_delay(monkeypatch):
    from app.agent import factory

    monkeypatch.setattr(factory.settings, "llm_provider", "fake")
    monkeypatch.setattr(factory.settings, "fake_llm_delay", 0.25)
    assert factory.build_llm_client()._delay == 0.25
