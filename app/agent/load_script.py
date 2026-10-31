"""A scripted model for load tests (LLM_PROVIDER=fake).

It reads the last thing the user typed and calls a real tool, so the load reaches the tools, services and
database just like a real conversation. It never calls a change tool, so load tests do not alter data."""

import re

from .fake_client import text_response, tool_response
from .llm import LLMRequest, LLMResponse, Usage

# "4А", "3 б", "11Б": a class name inside a sentence. Only the parallels А-Г, so "2 и 3 вопроса" is not a class.
_CLASS = re.compile(r"\b(\d{1,2})\s?([А-Га-г])\b")
# The name stops at punctuation: "Найди Амир, пожалуйста" -> "Амир"; hyphens stay ("Анна-Мария")
_SEARCH = re.compile(r"(?:найди|найти|поиск|где)\s+([\w-]{2,})", re.IGNORECASE)

# A made-up, small token count per answer. The real numbers come from the run on Claude (the fake model has no cache,
# so cache_read stays 0 here)
_USAGE = Usage(input_tokens=500, output_tokens=60)


def load_test_script(request: LLMRequest) -> LLMResponse:
    last = request.messages[-1]
    if last.tool_results:  # a tool just ran: finish the turn with text
        return text_response("Вот что удалось найти по вашему запросу.", _USAGE)

    text = last.text
    match = _CLASS.search(text)
    if match and re.search(r"список|ученик|класс", text, re.IGNORECASE):
        return tool_response("list_class_students", {"class_name": (match[1] + match[2]).upper()})
    search = _SEARCH.search(text)
    if search:
        return tool_response("search_students", {"name": search[1]})
    if re.search(r"класс", text, re.IGNORECASE):
        return tool_response("list_classes", {})
    return text_response("Я помогаю только со списками учеников, учителей и классов.", _USAGE)
