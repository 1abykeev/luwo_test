"""Cleaning and matching of names typed by users."""

import re

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

# For people's names, both cases: Latin A B C E H K M O P T X Y and a c e k o p x y look identical to a Cyrillic letter.
_NAME_LOOKALIKE = str.maketrans(
    "ABCEHKMOPTXY" "acekopxy",
    "\u0410\u0412\u0421\u0415\u041d\u041a\u041c\u041e\u0420\u0422\u0425\u0423"
    "\u0430\u0441\u0435\u043a\u043e\u0440\u0445\u0443",
)
_NAME_LOOKALIKE_BACK = str.maketrans(
    "\u0410\u0412\u0421\u0415\u041d\u041a\u041c\u041e\u0420\u0422\u0425\u0423"
    "\u0430\u0441\u0435\u043a\u043e\u0440\u0445\u0443",
    "ABCEHKMOPTXY" "acekopxy",
)
_CYRILLIC_LETTER = re.compile("[\u0410-\u044f\u0401\u0451\u04e8\u04e9\u04ae\u04af\u04a2\u04a3]")
_LATIN_LETTER = re.compile("[A-Za-z]")
_NAME_SEPARATORS = re.compile(r"[\s\-'.\u2019]+")


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
    # A word with letters from both alphabets is almost always a typing slip (or a trick to dodge the
    # namesake check): "Aмир" with a Latin A looks identical to "Амир". Refuse it with a clear message.
    for word in _NAME_SEPARATORS.split(name):
        if _LATIN_LETTER.search(word) and _CYRILLIC_LETTER.search(word):
            raise InvalidRequest(
                f"The word '{word}' mixes Latin and Cyrillic letters that look alike. "
                "Retype it using one alphabet.",
                details={"word": word},
            )
    return name


def name_key(name: str) -> str:
    """What to compare when asking 'is this the same name?': ignores case, extra spaces and Latin letters
    that look like Cyrillic ones, so a lookalike spelling cannot slip past the namesake check."""
    return " ".join(name.translate(_NAME_LOOKALIKE).casefold().split())


def search_variants(name: str) -> list[str]:
    """Spellings to look up in the database when checking for a namesake: as typed, with lookalike letters
    turned into Cyrillic, and into Latin. The database search is plain text, so "Epa" would never find a
    stored "Ера" otherwise. The caller still compares the hits with name_key."""
    return list(dict.fromkeys([name, name.translate(_NAME_LOOKALIKE), name.translate(_NAME_LOOKALIKE_BACK)]))


def clean_search_text(raw: object) -> str:
    if not isinstance(raw, str):
        raise InvalidRequest("The search text must be text")
    text = " ".join(raw.split())
    if len(text) < 2:
        raise InvalidRequest("Search text must be at least 2 characters")
    # A word that already contains Cyrillic letters gets its Latin lookalikes turned into Cyrillic, so
    # "Aмир" (Latin A) still finds "Амир". A word with no Cyrillic at all (a Latin name) is left alone.
    return " ".join(w.translate(_NAME_LOOKALIKE) if _CYRILLIC_LETTER.search(w) else w for w in text.split())


def normalize_school_name(raw: str) -> str:
    """'Лицей №1' and 'лицей 1' compare equal."""
    return "".join(ch for ch in raw.casefold() if ch.isalnum())
