"""The scripted model used by the load test: it must call real tools so the load reaches services and the DB."""

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
