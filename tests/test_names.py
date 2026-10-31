import pytest

from app.domain.errors import InvalidRequest
from app.services.names import class_name_candidates, clean_person_name, clean_search_text, normalize_school_name

CYR_A, CYR_B, CYR_V = "А", "Б", "В"  # А Б В


def test_latin_a_means_cyrillic_a():
    assert class_name_candidates("4A") == [f"4{CYR_A}"]
    assert class_name_candidates("4a") == [f"4{CYR_A}"]


def test_latin_b_tries_lookalike_first_then_by_sound():
    # "3B": the letter looks like В, but people usually mean the second parallel, Б
    assert class_name_candidates("3B") == [f"3{CYR_V}", f"3{CYR_B}"]


def test_spaces_and_hyphens_are_ignored():
    assert class_name_candidates("3 - b") == class_name_candidates("3B")
    assert class_name_candidates(f"4 {CYR_A.lower()}") == [f"4{CYR_A}"]


def test_empty_class_name_rejected():
    with pytest.raises(InvalidRequest):
        class_name_candidates("  - ")


@pytest.mark.parametrize("bad", ["", "A", "Alina2", "Алина; DROP TABLE", "x" * 101, None, 42])
def test_bad_person_names_rejected(bad):
    with pytest.raises(InvalidRequest):
        clean_person_name(bad)


def test_person_name_is_cleaned():
    assert clean_person_name("  Алина   Смирнова ") == "Алина Смирнова"
    assert clean_person_name("Анна-Мария О'Нил") == "Анна-Мария О'Нил"


def test_search_text_needs_two_characters():
    with pytest.raises(InvalidRequest):
        clean_search_text("а")
    assert clean_search_text(" Амир ") == "Амир"


def test_school_names_compare_loosely():
    assert normalize_school_name("Лицей №1") == normalize_school_name("лицей 1")


# ---- review finding: Latin letters that look like Cyrillic must not hide a namesake ----

LATIN_A_MIR = "\u0041" + "\u043c\u0438\u0440"  # Latin A, then Cyrillic м и р: looks exactly like Амир
CYRILLIC_AMIR = "\u0410\u043c\u0438\u0440"  # Амир, all Cyrillic
KASYMOV = "\u041a\u0430\u0441\u044b\u043c\u043e\u0432"  # Касымов, all Cyrillic
KASYMOV_LATIN_O = "\u041a\u0430\u0441\u044b\u043c" + "\u006f" + "\u0432"  # Касымов with a Latin o
ERA_CYRILLIC = "\u0415\u0440\u0430"  # Ера: every letter has a Latin lookalike
ERA_LATIN = "\u0045\u0070\u0061"  # E p a, all Latin: looks identical to the line above


def test_a_word_that_mixes_latin_and_cyrillic_letters_is_refused():
    for bad in (LATIN_A_MIR, f"{CYRILLIC_AMIR} {KASYMOV_LATIN_O}", f"{KASYMOV_LATIN_O}-{CYRILLIC_AMIR}"):
        with pytest.raises(InvalidRequest, match="Latin and Cyrillic") as error:
            clean_person_name(bad)
        assert "word" in error.value.details


def test_names_in_one_alphabet_are_fine():
    assert clean_person_name(f"{CYRILLIC_AMIR} {KASYMOV}") == f"{CYRILLIC_AMIR} {KASYMOV}"
    assert clean_person_name("Amir Kassymov") == "Amir Kassymov"  # an English-speaking user
    assert clean_person_name("Анна-Мария") == "Анна-Мария"
    assert clean_person_name("Amir Касымов") == "Amir Касымов"  # one word per alphabet is not a mixed word


def test_comparing_names_ignores_case_spacing_and_lookalike_letters():
    from app.services.names import name_key

    assert name_key(CYRILLIC_AMIR) == name_key(CYRILLIC_AMIR.upper()) == name_key(f"  {CYRILLIC_AMIR.lower()} ")
    assert name_key(LATIN_A_MIR) == name_key(CYRILLIC_AMIR)  # the sneaky one
    assert name_key(ERA_LATIN) == name_key(ERA_CYRILLIC)  # looks identical on screen, so it counts as the same name
    assert name_key("Amir") != name_key(CYRILLIC_AMIR)  # only A looks alike: genuinely a different string


def test_a_search_typed_with_a_lookalike_letter_is_corrected_to_one_alphabet():
    assert clean_search_text(LATIN_A_MIR) == CYRILLIC_AMIR
    assert clean_search_text(f"{LATIN_A_MIR} {KASYMOV}") == f"{CYRILLIC_AMIR} {KASYMOV}"
    assert clean_search_text("Amir") == "Amir"  # no Cyrillic in the word: left alone
    assert clean_search_text(f"Amir {KASYMOV}") == f"Amir {KASYMOV}"


def test_search_variants_cover_both_alphabets_for_a_fully_lookalike_name():
    from app.services.names import search_variants

    assert set(search_variants(ERA_LATIN)) == {ERA_LATIN, ERA_CYRILLIC}
    assert set(search_variants(ERA_CYRILLIC)) == {ERA_CYRILLIC, ERA_LATIN}
    assert search_variants(CYRILLIC_AMIR + " " + KASYMOV)[0] == CYRILLIC_AMIR + " " + KASYMOV  # as typed comes first
