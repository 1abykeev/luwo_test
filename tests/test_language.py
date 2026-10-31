import pytest

from app.agent.language import drop_foreign_preamble, has_cyrillic

RU = "Удалите Амира из моего класса"


def test_a_leading_english_paragraph_is_removed():
    reply = "There are two Amirs in 4А, so I need to ask which one.\n\nКакого Амира удалить: Жумаева или Касымова?"
    assert drop_foreign_preamble(reply, RU) == "Какого Амира удалить: Жумаева или Касымова?"


def test_several_english_paragraphs_in_front_are_removed():
    reply = "I will ask the user.\n\nThere are two matches here.\n\nКакого Амира удалить?"
    assert drop_foreign_preamble(reply, RU) == "Какого Амира удалить?"


def test_english_with_a_cyrillic_name_inside_is_still_english():
    reply = "There are two students named Амир in 4А, so I need to know which one you mean.\n\nКакого Амира удалить?"
    assert drop_foreign_preamble(reply, RU) == "Какого Амира удалить?"


def test_russian_with_a_few_english_words_is_still_russian():
    reply = "В классе 4А пять учеников, фильтр по status не нужен.\n\nМогу показать список."
    assert drop_foreign_preamble(reply, RU) == reply


def test_a_normal_russian_reply_is_untouched():
    reply = "В классе 4А пять учеников.\n\nКлассный руководитель: Айгуль Садыкова."
    assert drop_foreign_preamble(reply, RU) == reply


def test_a_reply_that_is_all_english_is_left_alone_not_emptied():
    reply = "Nothing has changed yet. Please confirm with the button on the card."
    assert drop_foreign_preamble(reply, RU) == reply


def test_an_english_paragraph_AFTER_the_russian_one_is_not_touched():
    reply = "Готово, ученик добавлен.\n\nAll done, the student was added to the class."
    assert drop_foreign_preamble(reply, RU) == reply


def test_names_and_class_names_in_latin_do_not_count_as_english():
    reply = "4A\n\nКакого Амира удалить?"  # a short Latin line (no 3-letter words)
    assert drop_foreign_preamble(reply, RU) == reply


@pytest.mark.parametrize("typed", ["Remove Amir from my class", "", None])
def test_english_users_get_english_replies_untouched(typed):
    reply = "There are two Amirs in 4A, so I need to ask which one.\n\nWhich Amir should I remove?"
    assert drop_foreign_preamble(reply, typed) == reply


def test_kyrgyz_letters_count_as_cyrillic():
    assert has_cyrillic("Мен окуучуну өчүрүүнү каалайм") and has_cyrillic("ң")
    assert not has_cyrillic("Hello 4A")
