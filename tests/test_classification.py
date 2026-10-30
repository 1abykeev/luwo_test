import pytest

from app.observability.classification import ToolRecord, classify


def record(request_type, kind="ok", is_error=False):
    return ToolRecord("some_tool", request_type, kind, is_error)


@pytest.mark.parametrize("records, text, expected", [
    ([], "Здравствуйте!", ("other", "resolved")),
    ([], "В какой класс добавить?", ("other", "needs_clarification")),
    ([record("show")], "Вот список.", ("show", "resolved")),
    ([record("search")], "Какого из двух Амиров удалить?", ("search", "needs_clarification")),
    ([record("search"), record("add", "pending_confirmation")], "Подтвердите?", ("add", "resolved")),
    ([record("add", "conflict", True)], "Это тот же ребёнок?", ("add", "needs_clarification")),
    ([record("transfer", "permission_denied", True)], "Нельзя.", ("transfer", "permission_denied")),
    ([record("off_topic", "out_of_scope")], "Только списки.", ("off_topic", "out_of_scope")),
    ([record("show"), record("remove", "error", True)], "Не получилось.", ("remove", "error")),
    ([record("missing_student")], "Она в 4Б.", ("missing_student", "resolved")),
    ([record("duplicate")], "Нашла двух.", ("duplicate", "resolved")),
    ([record("confirm", "confirmed")], "Готово.", ("confirmation", "resolved")),
    ([record("confirm", "conflict", True)], "Время истекло.", ("confirmation", "needs_clarification")),
])
def test_requests_are_labelled_by_what_the_agent_did(records, text, expected):
    assert classify(records, text) == expected


def test_a_failed_model_call_is_an_error_whatever_else_happened():
    assert classify([record("show")], "…", llm_failed=True) == ("show", "error")


def test_the_most_specific_type_wins_when_several_tools_were_used():
    records = [record("show"), record("search"), record("transfer", "pending_confirmation")]
    assert classify(records, "ok")[0] == "transfer"


def test_a_permission_denial_beats_a_later_clarification():
    records = [record("show", "permission_denied", True), record("search", "invalid_request", True)]
    assert classify(records, "?")[1] == "permission_denied"
