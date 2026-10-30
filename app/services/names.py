"""Cleaning and matching of names typed by users."""

from app.domain.errors import InvalidRequest

# Latin letters that look exactly like a Cyrillic letter (A B C E H K M O P T X Y)
_LOOKALIKE = str.maketrans(
    "ABCEHKMOPTXY",
    "АВСЕНКМОРТХУ",  # АВСЕНКМОРТХУ
)
# Latin letters read by sound: A B V G D E -> А Б В Г Д Е ("3B" usually means 3Б, the second parallel)
_PHONETIC = str.maketrans(
    "ABVGDE",
    "АБВГДЕ",  # АБВГДЕ
)
_IGNORED_IN_CLASS_NAME = set("-–—.")  # hyphen, en dash, em dash, dot


def class_name_candidates(raw: str) -> list[str]:
    """Possible spellings of a class name, best guess first.

    "4a" -> ["4А"], "3 b" -> ["3В", "3Б"]. The caller tries them in order and takes the first
    one that exists, so a school with both 3В and 3Б still gets the lookalike reading first."""
    cleaned = "".join(ch for ch in raw.upper() if not ch.isspace() and ch not in _IGNORED_IN_CLASS_NAME)
    if not cleaned:
        raise InvalidRequest("Class name is empty")
    return list(dict.fromkeys([cleaned.translate(_LOOKALIKE), cleaned.translate(_PHONETIC)]))


def clean_person_name(raw: object) -> str:
    if not isinstance(raw, str):
        raise InvalidRequest("The name must be text")
    name = " ".join(raw.split())
    if not 2 <= len(name) <= 100:
        raise InvalidRequest("The name must be between 2 and 100 characters")
    if not any(ch.isalpha() for ch in name) or not all(ch.isalpha() or ch in " -'.’" for ch in name):
        raise InvalidRequest("A name may contain only letters, spaces, hyphens, apostrophes and dots")
    return name


def clean_search_text(raw: object) -> str:
    if not isinstance(raw, str):
        raise InvalidRequest("The search text must be text")
    text = " ".join(raw.split())
    if len(text) < 2:
        raise InvalidRequest("Search text must be at least 2 characters")
    return text


def normalize_school_name(raw: str) -> str:
    """'Лицей №1' and 'лицей 1' compare equal."""
    return "".join(ch for ch in raw.casefold() if ch.isalnum())
