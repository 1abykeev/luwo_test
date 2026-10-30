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
